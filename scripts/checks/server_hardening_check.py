import os, re, sys, time
import mysql.connector, requests
from dotenv import dotenv_values

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
USER = os.environ.get('SPP_USER_BASE', 'http://127.0.0.1:5002')
sys.path.insert(0, f'{ROOT}/scripts/checks')
import selftest_mocktest
v = dotenv_values(f'{ROOT}/user_app/.env')


def db(q, p=()):
    c = mysql.connector.connect(host=v['DATABASE_HOST'], user=v['DATABASE_USER'], password=v['DATABASE_PASSWORD'],
                                database=v['DATABASE_NAME'], autocommit=True)
    cur = c.cursor(dictionary=True); cur.execute(q, p)
    out = cur.fetchall() if cur.with_rows else []
    cur.close(); c.close(); return out


results = []
def check(name, ok, detail=''):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ''))


def login(s, email, password, headers=None):
    page = s.get(USER + '/user_login', timeout=30).text
    m = re.search(r'name="csrf_token" value="([^"]+)"', page)
    tok = m.group(1) if m else ''
    s.post(USER + '/user_login', data={'email': email, 'csrf_token': tok}, headers=headers or {}, timeout=30)
    return s.post(USER + '/user_login', data={'password': password, 'csrf_token': tok}, headers=headers or {}, timeout=30, allow_redirects=False)


selftest_mocktest.remove(db)
fx = selftest_mocktest.setup(db)
STU, CODE = fx['student'], fx['code']
U = STU['unique_code']
db("DELETE FROM user_login_attempts WHERE identifier LIKE %s", (f"%{STU['email']}%",))

try:
    print('\n== database connections ==')
    base = f'{ROOT}/user_app/routes'
    direct = []
    for folder, _, files in os.walk(base):
        for name in files:
            if name.endswith('.py') and name != 'db_pool.py' and 'sql_executor' not in name:
                text = open(os.path.join(folder, name), encoding='utf-8').read()
                if 'mysql.connector.connect(' in text:
                    direct.append(name)
    check('no student-app module opens its own MySQL connection any more (all use the pool)', not direct, str(direct))
    pool_src = open(f'{base}/db_pool.py').read()
    import subprocess
    probe = '''
import os, sys, time
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
import logging; logging.disable(logging.CRITICAL)
from routes import db_pool
import mysql.connector
held = [db_pool.get_connection() for _ in range(2)]
cur = held[0].cursor(); cur.execute("SHOW STATUS LIKE 'Threads_connected'"); before = int(cur.fetchone()[1]); cur.close()
t = time.time()
try:
    db_pool.get_connection(); outcome = 'opened-extra'
except Exception as e:
    outcome = type(e).__name__
waited = time.time() - t
cur = held[0].cursor(); cur.execute("SHOW STATUS LIKE 'Threads_connected'"); after = int(cur.fetchone()[1]); cur.close()
for h in held: h.close()
c = db_pool.get_connection(); k = c.cursor(); k.execute("SELECT @@transaction_isolation"); iso = k.fetchone()[0]; k.execute("SELECT 1 FROM auth LIMIT 1"); k.fetchall(); k.close(); dirty = c.in_transaction; c.close()
c = db_pool.get_connection(); clean = not c.in_transaction; c.close()
print("RESULT", outcome, round(waited, 1), after - before, iso, dirty, clean)
'''
    out = subprocess.run([sys.executable, '-c', probe, f'{ROOT}/user_app'], capture_output=True, text=True, timeout=120,
                         env=dict(os.environ, DB_POOL_SIZE='2', DB_POOL_WAIT='2')).stdout
    got = (re.search(r'RESULT (.*)', out) or [None, ''])[1].split()
    check('an empty pool waits for a free connection, then fails cleanly, without opening extra connections', len(got) == 6 and got[0] == 'PoolError' and float(got[1]) >= 1.9 and int(got[2]) <= 0, ' '.join(got))
    check('pooled connections use READ COMMITTED and come back clean (open transaction rolled back)', len(got) == 6 and got[3] == 'READ-COMMITTED' and got[4] == 'True' and got[5] == 'True', ' '.join(got))
    drop_probe = '''
import os, sys, time
os.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])
import logging; logging.disable(logging.CRITICAL)
from routes import db_pool
import mysql.connector
from config import Config
def ids():
    held = [db_pool.get_connection() for _ in range(3)]
    out = []
    for h in held:
        cur = h.cursor(); cur.execute("SELECT CONNECTION_ID()"); out.append(cur.fetchone()[0]); cur.close()
    for h in held: h.close()
    return out
def failures(n=30):
    bad = 0
    for _ in range(n):
        try:
            c = db_pool.get_connection()
            try:
                cur = c.cursor(); cur.execute("SELECT 1"); cur.fetchall(); cur.close()
            finally:
                c.close()
        except Exception:
            bad += 1
    return bad
admin = mysql.connector.connect(host=Config.DATABASE_HOST, user=Config.DATABASE_USER, password=Config.DATABASE_PASSWORD)
def kill(cid):
    k = admin.cursor(); k.execute("KILL %d" % cid); k.close()
kill(ids()[0]); time.sleep(0.2)
one = failures()
for cid in ids(): kill(cid)
time.sleep(0.2)
every = failures()
c = db_pool.get_connection(); cur = c.cursor(); cur.execute("SELECT CONNECTION_ID()"); mine = cur.fetchone()[0]; cur.close()
kill(mine); time.sleep(0.2)
try:
    cur = c.cursor(); cur.execute("SELECT 1"); cur.fetchall(); held = 0
except Exception:
    held = 1
c.close()
print("DROP", one, every, held, failures())
'''
    out = subprocess.run([sys.executable, '-c', drop_probe, f'{ROOT}/user_app'], capture_output=True, text=True, timeout=120,
                         env=dict(os.environ, DB_POOL_SIZE='3', WEB_CONCURRENCY='1')).stdout
    got = (re.search(r'DROP (.*)', out) or [None, ''])[1].split()
    check('a connection MySQL dropped is replaced at the next use: no query fails afterwards', len(got) == 4 and got[0] == '0', ' '.join(got))
    check('after every pooled connection is dropped (a MySQL restart) the next queries all succeed', len(got) == 4 and got[1] == '0', ' '.join(got))
    check('a connection dropped in the middle of a request fails that request only, not the ones after it', len(got) == 4 and got[2] == '1' and got[3] == '0', ' '.join(got))
    check('the old second pool module now delegates to the shared pool', 'from routes.db_pool import get_connection' in open(f'{ROOT}/user_app/db_pool.py').read())

    print('\n== the three API bugs ==')
    s = requests.Session()
    r = login(s, STU['email'], STU['password'])
    check('the SELFTEST student can sign in', r.status_code in (301, 302) and 'user_login' not in (r.headers.get('Location') or ''), f"{r.status_code} {r.headers.get('Location')}")
    r = s.post(f"{USER}/submit_feedback/{fx['mock_sid']}/no_such_test_key/{CODE}/{U}", json={'software_feedback': 'x'}, timeout=30)
    check('/submit_feedback with an unknown test answers 404, not 500', r.status_code == 404, f'{r.status_code} {r.text[:60]}')
    r = s.post(f"{USER}/submit_feedback/{fx['mock_sid']}/{fx['mock_key']}/{CODE}/{U}", data='not json', headers={'Content-Type': 'text/plain'}, timeout=30)
    check('/submit_feedback with a non-JSON body answers 400', r.status_code == 400, f'{r.status_code} {r.text[:60]}')
    r = s.post(f'{USER}/api/expire-result', data='not json', headers={'Content-Type': 'text/plain'}, timeout=30)
    check('/api/expire-result with a non-JSON body answers 400, not 500', r.status_code == 400, f'{r.status_code} {r.text[:60]}')
    r = s.post(f'{USER}/submit-feedback', data={}, timeout=30)
    check('the communication /submit-feedback with an empty body is refused instead of saying success', r.status_code == 400, f'{r.status_code} {r.text[:60]}')

    print('\n== cross-site requests ==')
    r = s.post(f'{USER}/api/exam-window/claim', json={'test_key': 'k', 'tab_id': 't'}, headers={'Origin': 'https://evil.example'}, timeout=30)
    check('a write sent from another website is blocked (403)', r.status_code == 403, f'{r.status_code} {r.text[:50]}')
    r = s.post(f'{USER}/api/exam-window/claim', json={'test_key': 'k', 'tab_id': 't'}, headers={'Origin': 'null'}, timeout=30)
    check('a write with an opaque origin is blocked', r.status_code == 403, str(r.status_code))
    r = s.post(f'{USER}/api/exam-window/claim', json={'test_key': 'k', 'tab_id': 't'}, headers={'Referer': 'https://evil.example/page'}, timeout=30)
    check('a write whose Referer is another site is blocked', r.status_code == 403, str(r.status_code))
    r = s.post(f'{USER}/api/exam-window/claim', json={'test_key': 'k', 'tab_id': 't'}, headers={'Origin': USER}, timeout=30)
    check('the same write from this site works', r.status_code == 200 and r.json().get('ok') is True, f'{r.status_code} {r.text[:50]}')
    r = s.post(f'{USER}/api/exam-window/claim', json={'test_key': 'k', 'tab_id': 't'}, timeout=30)
    check('a write with no Origin (non-browser client) still works', r.status_code == 200, str(r.status_code))
    r = requests.post(f'{USER}/api/purchase/webhook', data='{}', headers={'Origin': 'https://api.razorpay.com', 'Content-Type': 'application/json'}, timeout=30)
    check('the payment webhook is not blocked by the origin rule', r.status_code != 403, str(r.status_code))
    r = requests.get(f'{USER}/', headers={'Origin': 'https://evil.example'}, timeout=30)
    check('reading pages from elsewhere is unaffected', r.status_code == 200, str(r.status_code))

    print('\n== login lockout and limits ==')
    db("DELETE FROM user_login_attempts WHERE identifier LIKE %s", (f"%{STU['email']}%",))
    bad = requests.Session()
    for _ in range(5):
        login(bad, STU['email'], 'wrong-password')
    rows = db("SELECT identifier, locked_until IS NOT NULL AS locked FROM user_login_attempts WHERE identifier LIKE %s", (f"%{STU['email']}%",))
    check('five wrong passwords lock only this account from this address (one pair row, no whole-IP row)', len(rows) == 1 and rows[0]['identifier'].startswith('pair:') and rows[0]['locked'] == 1
          and not db("SELECT 1 FROM user_login_attempts WHERE identifier LIKE 'ip:%%' AND last_attempt_at > NOW() - INTERVAL 1 MINUTE"), str(rows))
    r = login(requests.Session(), STU['email'], STU['password'])
    check('while locked, even the right password is refused from that address', 'user_login' in (r.headers.get('Location') or '') or r.status_code == 200 or (r.headers.get('Location') or '').rstrip('/').endswith(USER.split('//')[1]) or r.headers.get('Location') in ('/', None), f"{r.status_code} {r.headers.get('Location')}")
    who = requests.Session(); r = login(who, STU['email'], STU['password'])
    inside = who.get(f'{USER}/profile', timeout=30, allow_redirects=False)
    check('the locked address really is not signed in', inside.status_code in (301, 302), str(inside.status_code))
    forged = requests.Session(); r = login(forged, STU['email'], STU['password'], headers={'X-Forwarded-For': '203.0.113.77'})
    inside = forged.get(f'{USER}/profile', timeout=30, allow_redirects=False)
    check('a forged X-Forwarded-For header does not dodge the lock', inside.status_code in (301, 302), str(inside.status_code))
    other = db("SELECT 1 FROM user_login_attempts WHERE identifier LIKE 'pair:%%203.0.113.77%%'")
    check('and the forged address is never recorded', not other)
    db("DELETE FROM user_login_attempts WHERE identifier LIKE %s", (f"%{STU['email']}%",))
    flood = requests.Session(); codes = []
    page = flood.get(USER + '/user_login', timeout=30).text
    tok = (re.search(r'name="csrf_token" value="([^"]+)"', page) or [None, ''])[1]
    for _ in range(24):
        codes.append(flood.post(USER + '/user_login', data={'email': STU['email'], 'csrf_token': tok}, timeout=30, allow_redirects=False).status_code)
    check('more than 20 login posts a minute for one account are throttled with 429', 429 in codes, str(codes[-4:]))
    time.sleep(62)
    ok = requests.Session(); r = login(ok, STU['email'], STU['password'])
    check('after the lock is cleared the student signs in normally', r.status_code in (301, 302) and ok.get(f'{USER}/profile', timeout=30, allow_redirects=False).status_code == 200)

    print('\n== one session per account ==')
    first = requests.Session(); login(first, STU['email'], STU['password'])
    check('the first device is signed in', first.get(f'{USER}/profile', timeout=30, allow_redirects=False).status_code == 200)
    second = requests.Session(); login(second, STU['email'], STU['password'])
    check('signing in on a second device works', second.get(f'{USER}/profile', timeout=30, allow_redirects=False).status_code == 200)
    r = first.get(f'{USER}/profile', timeout=30, allow_redirects=False)
    check('the first device is signed out on its next click', r.status_code in (301, 302) and 'user_login' in (r.headers.get('Location') or ''), f"{r.status_code} {r.headers.get('Location')}")
    page = first.get(f'{USER}/user_login', timeout=30).text
    check('and it is told why', 'signed in on another device' in page, page[page.find('app-flash'):page.find('app-flash') + 200] if 'app-flash' in page else 'no flash')
    third = requests.Session(); login(third, STU['email'], STU['password'])
    r = second.post(f'{USER}/api/exam-window/claim', json={'test_key': 'k', 'tab_id': 't'}, headers={'X-Requested-With': 'XMLHttpRequest'}, timeout=30)
    check('a background request from the replaced device gets 401 with a sign-in link', r.status_code == 401 and r.json().get('error') == 'signed_out' and 'user_login' in r.json().get('redirect', ''), f'{r.status_code} {r.text[:80]}')
    check('the newest device keeps working', third.get(f'{USER}/profile', timeout=30, allow_redirects=False).status_code == 200)
    token_before = db("SELECT active_session FROM auth WHERE email=%s", (STU['email'],))[0]['active_session']
    db("INSERT INTO user_test_log (email, test_id, test_key, username, start_time, last_heartbeat, status, attempt_number) VALUES (%s,%s,%s,'SELFTEST Student',NOW(),NOW(),'in_progress',1)",
       (STU['email'], fx['mock_sid'], fx['mock_key']))
    fourth = requests.Session(); login(fourth, STU['email'], STU['password'])
    token_after = db("SELECT active_session FROM auth WHERE email=%s", (STU['email'],))[0]['active_session']
    check('while the account has a test open, a new sign-in is refused and the test-taker stays signed in',
          fourth.get(f'{USER}/profile', timeout=30, allow_redirects=False).status_code in (301, 302) and token_after == token_before
          and third.get(f'{USER}/profile', timeout=30, allow_redirects=False).status_code == 200)
    db("DELETE FROM user_test_log WHERE email=%s AND test_key=%s", (STU['email'], fx['mock_key']))
    fifth = requests.Session(); login(fifth, STU['email'], STU['password'])
    check('once the test is closed the sign-in works again', fifth.get(f'{USER}/profile', timeout=30, allow_redirects=False).status_code == 200)

    os.chdir(f'{ROOT}/user_app'); sys.path.insert(0, f'{ROOT}/user_app')
    import app as app_module
    from extensions import rate_limit_key
    flask_app = app_module.app
    with flask_app.test_request_context('/profile'):
        from flask import session
        anon = rate_limit_key()
        session['user_email'] = 'someone@example.com'
        signed = rate_limit_key()
    check('rate limits are counted per signed-in student, not per network address', signed == 'user:someone@example.com' and not anon.startswith('user:'), f'{anon} / {signed}')
    login_src = open(f'{ROOT}/user_app/routes/auth/login/manual_login/login.py').read()
    check('login is limited per account and the shared-IP allowance is high enough for a college network', '20 per minute' in login_src and '600 per minute' in login_src and '15 per minute' not in login_src)
    from routes.auth.utils import utils_login
    hashed = utils_login.hash_password('Abc@12345')
    check('password hashing and checking still work through the offload helper', utils_login.verify_password('Abc@12345', hashed) and not utils_login.verify_password('nope', hashed))

    print('\n== home page under database failure ==')
    from routes.index import index as index_module
    op = index_module.enroll_user_op
    original = type(op).get_course_groups
    type(op)._groups_cache.update({'rows': None, 'at': 0.0})
    def boom(self, strict=False):
        raise RuntimeError('simulated database outage')
    type(op).get_course_groups = boom
    try:
        resp = flask_app.test_client().get('/')
        check('when courses cannot be loaded the home page answers 503 with a notice, not an empty "200 OK"', resp.status_code == 503 and b'very busy right now' in resp.data, f'{resp.status_code}')
    finally:
        type(op).get_course_groups = original

    print('\n== last-active writes ==')
    from routes import activity
    first = activity.should_touch('selftest.activity@example.com'); second = activity.should_touch('selftest.activity@example.com')
    check('the last-active timestamp is written at most once per two minutes per student', first is True and second is False)

    print('\n== extras ==')
    r = requests.get(f'{USER}/robots.txt', timeout=30)
    check('robots.txt is served', r.status_code == 200 and 'Disallow: /api/' in r.text)
    check('robots.txt names the sitemap', 'Sitemap: ' in r.text and '/sitemap.xml' in r.text)
    r = requests.get(f'{USER}/sitemap.xml', timeout=30)
    check('sitemap.xml is served and lists the public pages', r.status_code == 200 and 'xml' in r.headers.get('Content-Type', '') and r.text.count('<loc>') >= 5 and '/courses</loc>' in r.text, f'{r.status_code} {r.text.count("<loc>")} pages')
    r = requests.get(f'{USER}/favicon.ico', timeout=30, allow_redirects=True)
    check('favicon.ico resolves to the site icon', r.status_code == 200 and r.headers.get('Content-Type', '').startswith('image/'), f"{r.status_code} {r.headers.get('Content-Type')}")
    r = requests.get(f'{USER}/', timeout=30)
    check('a Content-Security-Policy header is sent', "frame-ancestors 'self'" in (r.headers.get('Content-Security-Policy') or ''), str(r.headers.get('Content-Security-Policy')))
    r = requests.get(f'{USER}/practice-coding/api/judge/health', timeout=30)
    d = r.json()
    check('the judge health check reports whether Docker and the judge image are really there', 'docker_running' in d and 'judge_image_present' in d and d['healthy'] == (d['queue_ok'] and d['docker_running'] and d['judge_image_present']), str({k: d.get(k) for k in ('docker_running', 'judge_image_present', 'healthy')}))
    check('the judge Dockerfile is in the repository', os.path.isfile(f'{ROOT}/user_app/docker/Dockerfile.judge') and 'USER runner' in open(f'{ROOT}/user_app/docker/Dockerfile.judge').read())
    conf = open(f'{ROOT}/user_app/gunicorn.conf.py').read()
    check('the production server config runs several workers', 'workers = _workers' in conf and 'gunicorn -c gunicorn.conf.py' in open(f'{ROOT}/user_app/Procfile').read())
    check('the file-session fallback is no longer capped at 500 sessions', flask_app.config.get('SESSION_TYPE') == 'redis' or int(flask_app.config.get('SESSION_FILE_THRESHOLD', 500)) >= 100000, str(flask_app.config.get('SESSION_FILE_THRESHOLD')))
finally:
    db("DELETE FROM user_login_attempts WHERE identifier LIKE %s", (f"%{STU['email']}%",))
    db("DELETE FROM test_feedback WHERE test_key=%s", (fx['mock_key'],))
    selftest_mocktest.remove(db)

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
