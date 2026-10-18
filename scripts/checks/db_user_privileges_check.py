import os
import secrets
import sys

import mysql.connector

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SQL_FILE = os.path.join(ROOT, 'user_app', 'deploy', 'create_app_db_user.sql')
APP_USER = 'selftest_spp_app'
SBX_USER = 'selftest_spp_sbx'
SBX_DB = 'sbx_q999999991'
OTHER_DB = 'selftest_other_db'
FRESH_DB = 'selftest_fresh_limited'
TABLE = 'selftest_priv_check'
TRIGGER = 'selftest_priv_trigger'

results = []


def check(name, ok, detail=''):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ''))


def read_env():
    env = {}
    with open(os.path.join(ROOT, 'user_app', '.env'), encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def attempt(cur, sql, params=None):
    try:
        cur.execute(sql, params or ())
        if cur.with_rows:
            cur.fetchall()
        return True, ''
    except mysql.connector.Error as exc:
        return False, f"{exc.errno} {exc.msg}"


def main():
    env = read_env()
    host = env.get('DATABASE_HOST', 'localhost')
    database = env['DATABASE_NAME']
    password = 'Selftest-' + secrets.token_hex(12)
    sbx_password = 'Selftest-' + secrets.token_hex(12)

    admin = mysql.connector.connect(host=host, user=env['DATABASE_USER'],
                                    password=env['DATABASE_PASSWORD'], autocommit=True)
    acur = admin.cursor()

    def cleanup():
        attempt(acur, f"DROP TRIGGER IF EXISTS `{database}`.`{TRIGGER}`")
        attempt(acur, f"DROP TABLE IF EXISTS `{database}`.`{TABLE}`")
        attempt(acur, f"DROP DATABASE IF EXISTS `{SBX_DB}`")
        attempt(acur, f"DROP DATABASE IF EXISTS `{OTHER_DB}`")
        attempt(acur, f"DROP DATABASE IF EXISTS `{FRESH_DB}`")
        attempt(acur, f"DROP USER IF EXISTS '{APP_USER}'@'%'")
        attempt(acur, f"DROP USER IF EXISTS '{SBX_USER}'@'%'")
        attempt(acur, f"DROP USER IF EXISTS '{SBX_USER}'@'%%'")

    cleanup()
    acur.execute("SELECT @@GLOBAL.log_bin, @@GLOBAL.log_bin_trust_function_creators")
    log_bin, trusted = acur.fetchone()
    settings = open(os.path.join(ROOT, 'user_app', 'deploy', 'mysql-scale.cnf'), encoding='utf-8').read()
    check('the MySQL settings file allows the app user to create triggers',
          'log_bin_trust_function_creators = 1' in settings)
    if log_bin and not trusted:
        acur.execute("SET GLOBAL log_bin_trust_function_creators = 1")
    try:
        script = open(SQL_FILE, encoding='utf-8').read()
        script = (script.replace("'spp_app'", f"'{APP_USER}'")
                  .replace('CHANGE_THIS_PASSWORD', password)
                  .replace('YOUR_DATABASE_NAME', database))
        failures = []
        for statement in [s.strip() for s in script.split(';') if s.strip()]:
            ok, detail = attempt(acur, statement)
            if not ok:
                failures.append(detail)
        check('the limited-user script runs without an error', not failures, '; '.join(failures))

        app = mysql.connector.connect(host=host, user=APP_USER, password=password,
                                      database=database, autocommit=True)
        cur = app.cursor()

        ok, detail = attempt(cur, "SELECT COUNT(*) FROM auth")
        check('limited user reads the application tables', ok, detail)
        ok, detail = attempt(cur, f"CREATE TABLE `{TABLE}` (id INT PRIMARY KEY, label VARCHAR(40))")
        check('limited user creates a table (bootstrap and migrations)', ok, detail)
        ok, detail = attempt(cur, f"ALTER TABLE `{TABLE}` ADD COLUMN extra INT NULL, ADD INDEX idx_label (label)")
        check('limited user alters a table and adds an index', ok, detail)
        ok, detail = attempt(cur, f"INSERT INTO `{TABLE}` (id, label) VALUES (1, 'SELFTEST')")
        ok2, detail2 = attempt(cur, f"UPDATE `{TABLE}` SET label='SELFTEST2' WHERE id=1")
        ok3, detail3 = attempt(cur, f"DELETE FROM `{TABLE}` WHERE id=1")
        check('limited user inserts, updates and deletes rows', ok and ok2 and ok3, detail or detail2 or detail3)
        ok, detail = attempt(cur, f"CREATE TRIGGER `{TRIGGER}` BEFORE INSERT ON `{TABLE}` "
                                  f"FOR EACH ROW SET NEW.label = UPPER(NEW.label)")
        check('limited user creates a trigger (enrolment cap, placement-only rules)', ok, detail)
        ok, detail = attempt(cur, f"DROP TRIGGER IF EXISTS `{TRIGGER}`")
        check('limited user drops a trigger', ok, detail)
        ok, detail = attempt(cur, "SELECT GET_LOCK('selftest_priv_lock', 0)")
        attempt(cur, "SELECT RELEASE_LOCK('selftest_priv_lock')")
        check('limited user takes a named lock (background grader)', ok, detail)
        ok, detail = attempt(cur, f"DROP TABLE `{TABLE}`")
        check('limited user drops a table', ok, detail)

        ok, detail = attempt(cur, f"CREATE DATABASE `{SBX_DB}` CHARACTER SET utf8mb4")
        check('limited user creates a SQL-question sandbox database', ok, detail)
        ok, detail = attempt(cur, f"CREATE TABLE `{SBX_DB}`.emp (id INT PRIMARY KEY, name VARCHAR(30))")
        ok2, detail2 = attempt(cur, f"INSERT INTO `{SBX_DB}`.emp VALUES (1, 'SELFTEST')")
        check('limited user seeds the sandbox database', ok and ok2, detail or detail2)
        ok, detail = attempt(cur, "CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s", (SBX_USER, '%', sbx_password))
        check('limited user creates the read-only sandbox account', ok, detail)
        ok, detail = attempt(cur, "ALTER USER %s@%s IDENTIFIED BY %s", (SBX_USER, '%', sbx_password))
        check('limited user resets the sandbox account password', ok, detail)
        ok, detail = attempt(cur, f"GRANT SELECT ON `sbx\\_q%`.* TO '{SBX_USER}'@'%'")
        check('limited user grants read access on the sandbox databases', ok, detail)

        try:
            sbx = mysql.connector.connect(host=host, user=SBX_USER, password=sbx_password,
                                          database=SBX_DB, autocommit=True)
            scur = sbx.cursor()
            ok, detail = attempt(scur, "SELECT name FROM emp")
            check('sandbox account reads the sandbox database', ok, detail)
            ok, detail = attempt(scur, f"SELECT COUNT(*) FROM `{database}`.auth")
            check('sandbox account cannot read the application database', not ok, detail)
            ok, detail = attempt(scur, "INSERT INTO emp VALUES (2, 'X')")
            check('sandbox account cannot write', not ok, detail)
            sbx.close()
        except mysql.connector.Error as exc:
            check('sandbox account can sign in', False, str(exc))

        ok, detail = attempt(cur, f"DROP DATABASE `{SBX_DB}`")
        check('limited user drops the sandbox database', ok, detail)

        grant = [st.strip() for st in script.split(';') if f'`{database}`' in st][0]
        attempt(acur, grant.replace(f'`{database}`', f'`{FRESH_DB}`'))
        saved = {k: os.environ.get(k) for k in ('DATABASE_HOST', 'DATABASE_USER', 'DATABASE_PASSWORD', 'DATABASE_NAME', 'AUTO_MIGRATE')}
        os.environ.update({'DATABASE_HOST': host, 'DATABASE_USER': APP_USER, 'DATABASE_PASSWORD': password,
                           'DATABASE_NAME': FRESH_DB, 'AUTO_MIGRATE': '1'})
        import logging
        logging.disable(logging.CRITICAL)
        sys.path.insert(0, os.path.join(ROOT, 'user_app'))
        import db_bootstrap
        try:
            built = db_bootstrap.ensure_schema()
        except Exception as exc:
            built = f'{type(exc).__name__}: {exc}'
        for k, val in saved.items():
            if val is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = val
        acur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s", (FRESH_DB,))
        tables = acur.fetchone()[0]
        acur.execute("SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema = %s", (FRESH_DB,))
        triggers = acur.fetchone()[0]
        acur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s", (database,))
        live_tables = acur.fetchone()[0]
        check('limited user builds a complete new database (all tables, migrations and triggers)',
              built is True and tables == live_tables and triggers >= 3, f'result={built} tables={tables}/{live_tables} triggers={triggers}')

        ok, detail = attempt(cur, "SELECT COUNT(*) FROM mysql.user")
        check('limited user cannot read the MySQL account table', not ok, detail)
        ok, detail = attempt(cur, f"CREATE DATABASE `{OTHER_DB}`")
        check('limited user cannot create a database outside the sandbox prefix', not ok, detail)
        ok, detail = attempt(cur, "SET GLOBAL max_connections = 100")
        check('limited user cannot change server settings', not ok, detail)
        ok, detail = attempt(cur, "SHUTDOWN")
        check('limited user cannot shut the server down', not ok, detail)
        app.close()
    finally:
        cleanup()
        if log_bin and not trusted:
            acur.execute("SET GLOBAL log_bin_trust_function_creators = 0")
        acur.execute("SELECT COUNT(*) FROM mysql.user WHERE user IN (%s, %s)", (APP_USER, SBX_USER))
        left = acur.fetchone()[0]
        check('test accounts and databases are removed', left == 0, f"left={left}")
        admin.close()

    print(f"{sum(results)}/{len(results)} checks passed")
    sys.exit(0 if all(results) else 1)


if __name__ == '__main__':
    main()
