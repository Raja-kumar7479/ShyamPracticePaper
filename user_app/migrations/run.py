import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
USER_APP = os.path.dirname(HERE)
sys.path.insert(0, USER_APP)
os.chdir(USER_APP)

from config import Config
import mysql.connector


def connect():
    return mysql.connector.connect(host=Config.DATABASE_HOST, user=Config.DATABASE_USER,
                                   password=Config.DATABASE_PASSWORD, database=Config.DATABASE_NAME)


def migration_files():
    return sorted(f for f in os.listdir(HERE) if re.match(r'^\d{3}_.*\.sql$', f))


def statements(path):
    text = open(path, encoding='utf-8').read()
    text = '\n'.join(ln for ln in text.splitlines() if not ln.strip().startswith('--'))
    out, buf = [], []
    quote = None
    for ch in text:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"', '`'):
            quote = ch
            buf.append(ch)
        elif ch == ';':
            stmt = ''.join(buf).strip()
            upper = stmt.upper()
            if ('CREATE TRIGGER' in upper or 'CREATE PROCEDURE' in upper or 'CREATE FUNCTION' in upper) and not re.search(r'\bEND\s*$', upper):
                buf.append(ch)
                continue
            if stmt:
                out.append(stmt)
            buf = []
        else:
            buf.append(ch)
    tail = ''.join(buf).strip()
    if tail:
        out.append(tail)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--baseline', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    cnx = connect()
    cur = cnx.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
        filename VARCHAR(255) PRIMARY KEY,
        applied_at DATETIME DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB""")
    cnx.commit()
    cur.execute("SELECT filename FROM schema_migrations")
    applied = {r[0] for r in cur.fetchall()}
    files = migration_files()
    pending = [f for f in files if f not in applied]

    if args.list:
        for f in files:
            print(('applied ' if f in applied else 'PENDING '), f)
        return

    if args.baseline:
        for f in pending:
            cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (f,))
            print('baselined', f)
        cnx.commit()
        print(f'{len(pending)} file(s) marked as applied (nothing executed).')
        return

    if not pending:
        print('Nothing to do — all migrations applied.')
        return

    for f in pending:
        path = os.path.join(HERE, f)
        stmts = statements(path)
        print(f'== {f} ({len(stmts)} statements)')
        if args.dry_run:
            continue
        try:
            for stmt in stmts:
                try:
                    cur.execute(stmt)
                except mysql.connector.Error as exc:
                    if exc.errno not in (1050, 1060, 1061, 1091, 1359, 1826):
                        raise
                    print(f'   already in place, skipped: {exc.msg}')
                    continue
                if cur.with_rows:
                    cur.fetchall()
                try:
                    while cur.nextset():
                        if cur.with_rows:
                            cur.fetchall()
                except mysql.connector.errors.InterfaceError:
                    pass
            cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (f,))
            cnx.commit()
            print('   applied.')
        except Exception as e:
            cnx.rollback()
            print(f'   FAILED: {e}')
            print('   Migration NOT recorded — fix the file and re-run.')
            sys.exit(1)

    cur.close()
    cnx.close()


if __name__ == '__main__':
    main()
