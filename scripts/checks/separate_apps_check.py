import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import mysql.connector
import requests
from dotenv import dotenv_values
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ADMIN = 'http://127.0.0.1:5001'
USER = os.environ.get('SPP_USER_BASE', 'http://127.0.0.1:5002')
ADMIN_EMAIL, ADMIN_PASSWORD = 'rajakumarvijeta7087@gmail.com', 'Raja@7479'
v = dotenv_values(os.path.join(ROOT, 'user_app', '.env'))
APPS = ('user_app', 'admin_app')

results = []


def check(name, ok, detail=''):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ''), flush=True)


def db(q, p=()):
    c = mysql.connector.connect(host=v['DATABASE_HOST'], user=v['DATABASE_USER'], password=v['DATABASE_PASSWORD'],
                                database=v['DATABASE_NAME'], autocommit=True)
    cur = c.cursor(dictionary=True); cur.execute(q, p)
    out = cur.fetchall() if cur.with_rows else []
    cur.close(); c.close(); return out


def python_files(app):
    for folder, dirs, names in os.walk(os.path.join(ROOT, app)):
        dirs[:] = [d for d in dirs if d not in ('.venv', '__pycache__', 'logs', 'uploads', 'node_modules')]
        for name in names:
            if name.endswith('.py'):
                yield os.path.join(folder, name)


print('\n== nothing is shared outside the two app folders ==')
top = sorted(n for n in os.listdir(ROOT) if not n.startswith('.') and not n.endswith('.log') and n != '__pycache__')
check('the project folder holds only the two apps plus developer notes and test tools', set(top) <= {'user_app', 'admin_app', 'docs', 'scripts', 'README.md'}, str(top))
for gone in ('db_bootstrap.py', 'shared_uploads', 'deploy'):
    check(f'there is no top-level {gone} any more', not os.path.exists(os.path.join(ROOT, gone)))

for app in APPS:
    other = 'admin_app' if app == 'user_app' else 'user_app'
    root = os.path.realpath(os.path.join(ROOT, app))
    mentions, climbs = [], []
    for path in python_files(app):
        text = open(path, encoding='utf-8-sig').read()
        rel = os.path.relpath(path, ROOT)
        if other in text and os.path.basename(path) != 'db_bootstrap.py':
            mentions.append(rel)
        if re.search(r"sys\.path\.(append|insert)\([^)]*dirname\(os\.path\.dirname\(os\.path\.abspath\(__file__\)\)\)\)", text) and os.path.dirname(path) == root:
            climbs.append(rel)
        for match in re.finditer(r"os\.path\.join\(os\.path\.dirname\(os\.path\.abspath\(__file__\)\),\s*'\.\.'", text):
            if os.path.dirname(path) == root:
                climbs.append(rel)
    check(f'{app}: no Python file mentions {other}', not mentions, str(mentions[:5]))
    check(f'{app}: no file at its top level reaches into the parent folder', not climbs, str(climbs[:5]))
    for needed in ('db_bootstrap.py', 'deploy/nginx.conf', 'deploy/README.md', 'deploy/create_app_db_user.sql', 'requirements.txt', '.env.example'):
        check(f'{app} has its own {needed}', os.path.exists(os.path.join(ROOT, app, needed)))
    conf = open(os.path.join(ROOT, app, 'deploy', 'nginx.conf')).read()
    own, foreign = ('5002', '5001') if app == 'user_app' else ('5001', '5002')
    check(f'{app}: its nginx file serves only this app', own in conf and foreign not in conf and other not in conf)
    units = ' '.join(open(os.path.join(ROOT, app, 'deploy', f)).read() for f in os.listdir(os.path.join(ROOT, app, 'deploy')) if f.endswith('.service'))
    check(f'{app}: its service files use only its own folder', other not in units and f'/srv/{app}' in units)

print('\n== each app starts from a copy of its own folder alone ==')
PROBE = {
    'user_app': "import app as m\nc = m.app.test_client()\nr = c.get('/')\nimport db_bootstrap, config\nprint('PROBE', r.status_code, db_bootstrap.__file__, config.Config.UPLOAD_BASE)\n",
    'admin_app': "import app as m\nc = m.app.test_client()\nr = c.get('/admin_login')\nimport db_bootstrap, config\nprint('PROBE', r.status_code, db_bootstrap.__file__, config.Config.UPLOAD_BASE)\n",
}
for app in APPS:
    holder = tempfile.mkdtemp(prefix='selftest_alone_')
    try:
        target = os.path.join(holder, app)
        shutil.copytree(os.path.join(ROOT, app), target,
                        ignore=shutil.ignore_patterns('.venv', '__pycache__', 'logs', 'uploads', '*.pyc', 'flask_session', 'node_modules'))
        env = dict(os.environ, PENDING_GRADER_JOB='0', PYTHONDONTWRITEBYTECODE='1')
        env.pop('PYTHONPATH', None)
        out = subprocess.run([sys.executable, '-c', PROBE[app]], cwd=target, capture_output=True, text=True, timeout=180, env=env)
        got = (re.search(r'PROBE (\d+) (\S+) (\S+)', out.stdout) or [None, '', '', ''])
        real = os.path.realpath(target)
        check(f'{app} imports and answers a page with nothing beside it', got[1] in ('200', '302'), f'status={got[1]} {out.stderr.strip()[-160:] if not got[1] else ""}')
        check(f'{app}: the bootstrap it used is its own', bool(got[2]) and os.path.realpath(got[2]).startswith(real + os.sep), got[2][-60:])
        check(f'{app}: its uploads folder is inside the app', bool(got[3]) and os.path.realpath(got[3]).startswith(real + os.sep), got[3][-60:])
    finally:
        shutil.rmtree(holder, ignore_errors=True)

print('\n== a file uploaded in the admin app reaches the student app through the database ==')
name = None
try:
    s = requests.Session()
    tok = re.search(r'name="csrf-token"[^>]*content="([^"]+)"', s.get(f'{ADMIN}/admin_login').text).group(1)
    s.post(f'{ADMIN}/admin_login', data={'email': ADMIN_EMAIL, '_csrf_token': tok})
    s.post(f'{ADMIN}/admin_login', data={'password': ADMIN_PASSWORD, '_csrf_token': tok})
    H = {'X-CSRFToken': re.search(r'name="csrf-token"[^>]*content="([^"]+)"', s.get(f'{ADMIN}/manage-tests').text).group(1)}
    buf = io.BytesIO(); Image.new('RGB', (40, 30), (153, 44, 37)).save(buf, 'PNG'); data = buf.getvalue()
    r = s.post(f'{ADMIN}/api/question-image/upload', headers=H, files={'image': ('SELFTEST_separate.png', data, 'image/png')}, timeout=60)
    url = r.json().get('url', '') if r.ok else ''
    check('the admin upload is accepted', r.ok and url.startswith('/static/uploads/images/'), f'{r.status_code} {r.text[:80]}')
    rel = url[len('/static/uploads/'):]
    name = rel
    in_admin = os.path.join(ROOT, 'admin_app', 'uploads', rel)
    in_user = os.path.join(ROOT, 'user_app', 'uploads', rel)
    check('the file is saved inside the admin app', os.path.isfile(in_admin) and not os.path.exists(in_user))
    row = db("SELECT size, sha256, chunks FROM shared_files WHERE path=%s", (rel,))
    check('and written to the database', bool(row) and row[0]['size'] == len(data) and row[0]['sha256'] == hashlib.sha256(data).hexdigest(), str(row))
    got = requests.get(USER + url, timeout=60)
    check('the student app serves it although the file was never on its disk', got.status_code == 200 and got.content == data, f'{got.status_code} {len(got.content)} bytes')
    check('and keeps a copy inside the student app for next time', os.path.isfile(in_user))
    big = os.urandom(3 * 1024 * 1024 + 123)
    big_rel = 'images/SELFTEST_separate_big.bin'
    with open(os.path.join(ROOT, 'admin_app', 'uploads', big_rel), 'wb') as fh:
        fh.write(big)
    code = ("import logging; logging.disable(logging.CRITICAL)\nimport sys\nsys.path.insert(0, '.')\nfrom admin import shared_files\n"
            "print('SENT', shared_files.publish(sys.argv[1]))\n")
    out = subprocess.run([sys.executable, '-c', code, os.path.join(ROOT, 'admin_app', 'uploads', big_rel)], cwd=os.path.join(ROOT, 'admin_app'),
                         capture_output=True, text=True, timeout=120)
    row = db("SELECT size, chunks FROM shared_files WHERE path=%s", (big_rel,))
    got = requests.get(f'{USER}/static/uploads/{big_rel}', timeout=120)
    check('a file of several megabytes travels in parts and arrives whole', 'SENT True' in out.stdout and bool(row) and row[0]['chunks'] == 4 and got.status_code == 200 and got.content == big,
          f"{out.stdout.strip()[-40:]} {row} {got.status_code} {len(got.content)}")
    code = ("import logging; logging.disable(logging.CRITICAL)\nimport sys\nsys.path.insert(0, '.')\nfrom admin import shared_files\n"
            "print('GONE', shared_files.remove(sys.argv[1]))\n")
    subprocess.run([sys.executable, '-c', code, os.path.join(ROOT, 'admin_app', 'uploads', big_rel)], cwd=os.path.join(ROOT, 'admin_app'), capture_output=True, text=True, timeout=120)
    check('removing a file in the admin app removes it from the database', not db("SELECT 1 FROM shared_files WHERE path=%s", (big_rel,)) and not db("SELECT 1 FROM shared_file_chunks WHERE path=%s", (big_rel,)))
    private = requests.get(f'{USER}/static/uploads/user_responses/SELFTEST/none.webm', timeout=30)
    check('student recordings are not reachable this way', private.status_code in (403, 404), str(private.status_code))
finally:
    for rel in [name, 'images/SELFTEST_separate_big.bin']:
        if not rel:
            continue
        db("DELETE FROM shared_file_chunks WHERE path=%s", (rel,))
        db("DELETE FROM shared_files WHERE path=%s", (rel,))
        for app in APPS:
            try:
                os.remove(os.path.join(ROOT, app, 'uploads', rel))
            except OSError:
                pass
    left = db("SELECT COUNT(*) n FROM shared_files WHERE path LIKE '%%SELFTEST%%'")[0]['n']
    check('the SELFTEST files are removed', left == 0, f'left={left}')

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
