import hashlib
import importlib.util
import logging
import os
import re
import sys

import mysql.connector
from dotenv import dotenv_values

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
v = dotenv_values(os.path.join(ROOT, 'user_app', '.env'))
LIVE = v['DATABASE_NAME']
for key in ('DATABASE_HOST', 'DATABASE_USER', 'DATABASE_PASSWORD'):
    os.environ[key] = v[key]
os.environ['AUTO_MIGRATE'] = '1'
logging.disable(logging.CRITICAL)

results = []


def check(name, ok, detail=''):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ''))


conn = mysql.connector.connect(host=v['DATABASE_HOST'], user=v['DATABASE_USER'],
                               password=v['DATABASE_PASSWORD'], autocommit=True)
cur = conn.cursor()


def rows(sql, params=()):
    cur.execute(sql, params)
    return cur.fetchall()


def only_in(first, second, table, columns):
    picked = ', '.join(f'a.{c}' for c in columns)
    joined = ' AND '.join(f'b.{c} = a.{c}' for c in columns)
    schema = 'trigger_schema' if table == 'triggers' else 'table_schema'
    return rows(f"SELECT {picked} FROM information_schema.{table} a "
                f"LEFT JOIN information_schema.{table} b ON b.{schema} = %s AND {joined} "
                f"WHERE a.{schema} = %s AND b.{columns[-1]} IS NULL GROUP BY {picked}", (second, first))


def load(app):
    spec = importlib.util.spec_from_file_location(f'{app}_bootstrap', os.path.join(ROOT, app, 'db_bootstrap.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    with open(path, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def sql_files(folder):
    return {f: digest(os.path.join(folder, f)) for f in sorted(os.listdir(folder)) if re.match(r'^\d{3}_.*\.sql$', f)}


U, A = os.path.join(ROOT, 'user_app'), os.path.join(ROOT, 'admin_app')
pairs = [
    ('the core tables file', os.path.join(U, 'database', 'schema.sql'), os.path.join(A, 'database', 'student_schema.sql')),
    ('the coding tables file', os.path.join(U, 'routes', 'exam_platform', 'placement_exam_portal', 'coding_portal', 'schema.sql'),
     os.path.join(A, 'database', 'coding_schema.sql')),
    ('the admin tables file', os.path.join(U, 'database', 'admin_schema.sql'), os.path.join(A, 'database', 'schema.sql')),
]
for label, left, right in pairs:
    check(f'{label} is the same in both apps', os.path.exists(left) and os.path.exists(right) and digest(left) == digest(right),
          f'{os.path.relpath(left, ROOT)} vs {os.path.relpath(right, ROOT)}')
student = (sql_files(os.path.join(U, 'migrations')), sql_files(os.path.join(A, 'migrations', 'student')))
check('the student migrations are the same in both apps', student[0] == student[1] and len(student[0]) > 0,
      f'{len(student[0])} vs {len(student[1])}; differ: {sorted(set(student[0].items()) ^ set(student[1].items()))[:4]}')
admin = (sql_files(os.path.join(U, 'migrations', 'admin')), sql_files(os.path.join(A, 'migrations')))
check('the admin migrations are the same in both apps', admin[0] == admin[1] and len(admin[0]) > 0,
      f'{len(admin[0])} vs {len(admin[1])}; differ: {sorted(set(admin[0].items()) ^ set(admin[1].items()))[:4]}')

for app in ('user_app', 'admin_app'):
    scratch = f'selftest_fresh_{app}'
    os.environ['DATABASE_NAME'] = scratch
    cur.execute(f"DROP DATABASE IF EXISTS `{scratch}`")
    try:
        module = load(app)
        inside = all(os.path.realpath(path).startswith(os.path.realpath(os.path.join(ROOT, app)) + os.sep)
                     for _, path in list(module.BASE_SCHEMAS) + [(None, d) for _, d in module.MIGRATION_DIRS])
        check(f'{app}: its bootstrap reads only files inside its own folder', inside)
        ok = module.ensure_schema()
        check(f'{app} alone builds a brand-new database without an error', ok is True)
        files = len(module.migration_files())
        recorded = rows(f"SELECT COUNT(*) FROM `{scratch}`.schema_migrations WHERE filename NOT LIKE 'base:%%'")[0][0]
        check(f'{app}: every migration file is recorded as applied', recorded == files and files > 0, f'{recorded} of {files}')
        for label, table, columns in (('tables', 'tables', ['table_name']),
                                      ('columns', 'columns', ['table_name', 'column_name']),
                                      ('indexes', 'statistics', ['table_name', 'index_name']),
                                      ('triggers', 'triggers', ['trigger_name'])):
            missing = only_in(LIVE, scratch, table, columns)
            extra = only_in(scratch, LIVE, table, columns)
            check(f'{app}: {label} of the new database match the running one', not missing and not extra,
                  f'missing in new: {missing[:6]}  missing in running: {extra[:6]}')
        other = load('admin_app' if app == 'user_app' else 'user_app')
        before = rows(f"SELECT COUNT(*) FROM `{scratch}`.schema_migrations")[0][0]
        second = other.ensure_schema()
        after = rows(f"SELECT COUNT(*) FROM `{scratch}`.schema_migrations")[0][0]
        check(f'{app}: when the other app starts afterwards on the same database it finds nothing left to do',
              second is True and after == before and not only_in(LIVE, scratch, 'tables', ['table_name']), f'{before} -> {after}')
    finally:
        cur.execute(f"DROP DATABASE IF EXISTS `{scratch}`")

left = rows("SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name LIKE 'selftest\\_fresh\\_%%'")[0][0]
check('the scratch databases are removed', left == 0)
conn.close()

print(f"{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
