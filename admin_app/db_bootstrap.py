import hashlib
import logging
import os
import re

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))

BASE_SCHEMAS = (
    ('user_app/database/schema.sql', os.path.join(HERE, 'database', 'student_schema.sql')),
    ('user_app/routes/exam_platform/placement_exam_portal/coding_portal/schema.sql',
     os.path.join(HERE, 'database', 'coding_schema.sql')),
    ('admin_app/database/schema.sql', os.path.join(HERE, 'database', 'schema.sql')),
)

MIGRATION_DIRS = (
    ('', os.path.join(HERE, 'migrations', 'student')),
    ('admin/', os.path.join(HERE, 'migrations')),
)

SEED_FILE = None
ENV_FILE = os.path.join(HERE, '.env')

LOCK_NAME = 'spp_schema_bootstrap'
LOCK_TIMEOUT_SECONDS = 120

_MIGRATION_RE = re.compile(r'^\d{3}_.*\.sql$')
_IDENTIFIER_RE = re.compile(r'^[A-Za-z0-9_$]+$')

_already_ran = False


def _truthy(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _settings():
    return {
        'host': os.environ.get('DATABASE_HOST', 'localhost'),
        'port': int(os.environ.get('DB_PORT', 3306)),
        'user': os.environ.get('DATABASE_USER', 'root'),
        'password': os.environ.get('DATABASE_PASSWORD'),
        'database': os.environ.get('DATABASE_NAME'),
    }


def _connect(database=None):
    import mysql.connector
    cfg = _settings()
    kwargs = {'host': cfg['host'], 'port': cfg['port'],
              'user': cfg['user'], 'password': cfg['password']}
    if database:
        kwargs['database'] = database
    return mysql.connector.connect(**kwargs)


_BEGIN_RE = re.compile(r'\bBEGIN\b', re.I)
_END_RE = re.compile(r'\bEND\b(?!\s+(?:IF|LOOP|WHILE|CASE|REPEAT)\b)', re.I)


def _compound_depth(buf):
    text = ''.join(buf)
    if 'BEGIN' not in text.upper():
        return 0
    return max(0, len(_BEGIN_RE.findall(text)) - len(_END_RE.findall(text)))


def statements(path):
    with open(path, encoding='utf-8') as fh:
        text = fh.read()
    text = '\n'.join(ln for ln in text.splitlines() if not ln.strip().startswith('--'))
    out, buf, quote = [], [], None
    for ch in text:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"', '`'):
            quote = ch
            buf.append(ch)
        elif ch == ';' and _compound_depth(buf) == 0:
            stmt = ''.join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
        else:
            buf.append(ch)
    tail = ''.join(buf).strip()
    if tail:
        out.append(tail)
    return out


ALREADY_DONE = {1050, 1060, 1061, 1091, 1359, 1826}


def _run_script(cur, path):
    import mysql.connector
    count = 0
    for stmt in statements(path):
        try:
            cur.execute(stmt)
        except mysql.connector.Error as exc:
            if exc.errno not in ALREADY_DONE:
                raise
            logger.info("SCHEMA: %s: already in place, skipped (%s)", os.path.basename(path), exc.msg)
            count += 1
            continue
        if cur.with_rows:
            cur.fetchall()
        try:
            while cur.nextset():
                if cur.with_rows:
                    cur.fetchall()
        except mysql.connector.errors.InterfaceError:
            pass
        count += 1
    return count


def _table_exists(cur, name):
    cur.execute("SELECT COUNT(*) FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s", (name,))
    return cur.fetchone()[0] > 0


def migration_files():
    found = []
    for prefix, directory in MIGRATION_DIRS:
        if not os.path.isdir(directory):
            continue
        for name in sorted(f for f in os.listdir(directory) if _MIGRATION_RE.match(f)):
            found.append((prefix + name, os.path.join(directory, name)))
    return found


def _schema_key(label, path):
    with open(path, 'rb') as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()[:12]
    return 'base:{}@{}'.format(label, digest)


def _ensure_database(name, log):
    conn = _connect(None)
    try:
        cur = conn.cursor()
        cur.execute("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA "
                    "WHERE SCHEMA_NAME = %s", (name,))
        exists = cur.fetchone() is not None
        if not exists:
            cur.execute("CREATE DATABASE `{}` CHARACTER SET utf8mb4 "
                        "COLLATE utf8mb4_unicode_ci".format(name))
            log.warning("SCHEMA: database `%s` did not exist and was created.", name)
        cur.close()
    finally:
        conn.close()


def _apply(conn, cur, log, mode='apply'):
    tracked = _table_exists(cur, 'schema_migrations')
    fresh = not _table_exists(cur, 'auth')

    cur.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
        filename VARCHAR(255) PRIMARY KEY,
        applied_at DATETIME DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB""")
    conn.commit()
    cur.execute("SELECT filename FROM schema_migrations")
    applied = {row[0] for row in cur.fetchall()}

    for label, path in BASE_SCHEMAS:
        if not os.path.exists(path):
            log.warning("SCHEMA: %s is missing; skipped.", path)
            continue
        key = _schema_key(label, path)
        if key in applied:
            continue
        rel = os.path.relpath(path, HERE)
        if mode in ('list', 'dry-run'):
            log.info("SCHEMA: would load %s.", rel)
            continue
        count = _run_script(cur, path)
        cur.execute("INSERT IGNORE INTO schema_migrations (filename) VALUES (%s)", (key,))
        conn.commit()
        log.info("SCHEMA: loaded %s (%d statements).", rel, count)

    files = migration_files()
    pending = [(name, path) for name, path in files if name not in applied]

    if mode == 'list':
        for name, _ in files:
            log.info("  %s %s", 'applied' if name in applied else 'PENDING', name)
        return
    if not pending:
        log.info("SCHEMA: up to date (%d migration(s) applied).", len(files))
        return
    if mode == 'dry-run':
        for name, path in pending:
            log.info("SCHEMA: would apply %s (%d statements).",
                     name, len(statements(path)))
        return

    if mode == 'baseline' or (not fresh and not tracked):
        for name, _ in pending:
            cur.execute("INSERT IGNORE INTO schema_migrations (filename) VALUES (%s)", (name,))
        conn.commit()
        if mode == 'baseline':
            log.info("SCHEMA: baselined %d migration(s); nothing was executed.", len(pending))
        else:
            log.warning(
                "SCHEMA: this database already has tables but no schema_migrations "
                "table, so %d migration(s) were recorded as applied WITHOUT running "
                "them. Some of them delete rows and cannot be replayed safely. If any "
                "were genuinely never applied, apply those files by hand.", len(pending))
        return

    for name, path in pending:
        try:
            count = _run_script(cur, path)
            cur.execute("INSERT IGNORE INTO schema_migrations (filename) VALUES (%s)", (name,))
            conn.commit()
            log.info("SCHEMA: applied %s (%d statements).", name, count)
        except Exception:
            conn.rollback()
            log.exception("SCHEMA: %s FAILED and was not recorded; "
                          "later migrations were skipped.", name)
            raise


def ensure_schema(log=None, mode='apply'):
    global _already_ran
    log = log or logger

    if _already_ran and mode == 'apply':
        return True
    if mode == 'apply' and not _truthy(os.environ.get('AUTO_MIGRATE'), default=True):
        log.info("SCHEMA: AUTO_MIGRATE is off; skipping schema bootstrap.")
        _already_ran = True
        return False

    cfg = _settings()
    name = cfg['database']
    if not name:
        log.warning("SCHEMA: DATABASE_NAME is not set; skipping schema bootstrap.")
        _already_ran = True
        return False
    if not _IDENTIFIER_RE.match(name):
        log.error("SCHEMA: DATABASE_NAME %r is not a plain identifier; "
                  "skipping schema bootstrap.", name)
        _already_ran = True
        return False

    _already_ran = True
    try:
        _ensure_database(name, log)
        conn = _connect(name)
        try:
            cur = conn.cursor()
            cur.execute("SELECT GET_LOCK(%s, %s)", (LOCK_NAME, LOCK_TIMEOUT_SECONDS))
            if (cur.fetchone() or [0])[0] != 1:
                log.warning("SCHEMA: another process is running the bootstrap; skipping.")
                return False
            try:
                _apply(conn, cur, log, mode='apply' if mode == 'seed' else mode)
                if mode == 'seed':
                    if not SEED_FILE or not os.path.exists(SEED_FILE):
                        log.error("SCHEMA: this app has no sample data file.")
                        return False
                    count = _run_script(cur, SEED_FILE)
                    conn.commit()
                    log.info("SCHEMA: loaded sample data from %s (%d statements).",
                             os.path.relpath(SEED_FILE, HERE), count)
            finally:
                cur.execute("SELECT RELEASE_LOCK(%s)", (LOCK_NAME,))
                cur.fetchall()
                cur.close()
        finally:
            conn.close()
        return True
    except Exception:
        log.exception("SCHEMA: bootstrap failed. The app will still start, but "
                      "database queries may fail until this is fixed.")
        if _truthy(os.environ.get('AUTO_MIGRATE_STRICT')):
            raise
        return False


def _cli():
    import argparse
    from dotenv import load_dotenv

    if os.path.exists(ENV_FILE):
        load_dotenv(ENV_FILE)

    parser = argparse.ArgumentParser(description='Create or update the database tables this app needs.')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--list', action='store_true', help='show applied / pending')
    group.add_argument('--dry-run', action='store_true', help='print what would run')
    group.add_argument('--baseline', action='store_true',
                       help='record all pending as applied WITHOUT running them')
    group.add_argument('--seed', action='store_true',
                       help='bring the schema up to date, then load the sample data')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(message)s')
    mode = ('list' if args.list else 'dry-run' if args.dry_run
            else 'baseline' if args.baseline else 'seed' if args.seed else 'apply')
    ok = ensure_schema(mode=mode)
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    _cli()
