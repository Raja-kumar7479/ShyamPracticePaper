import re, sys, time
import mysql.connector, requests
from dotenv import dotenv_values

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
ADMIN, USER = 'http://127.0.0.1:5001', 'http://127.0.0.1:5002'
ADMIN_EMAIL, ADMIN_PASSWORD = 'rajakumarvijeta7087@gmail.com', 'Raja@7479'
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


def csrf(html):
    m = re.search(r'name="csrf-token"[^>]*content="([^"]+)"', html)
    return m.group(1) if m else ''


BAD = ('Internal Server Error', 'Traceback (most recent call last)', 'jinja2.exceptions', 'UndefinedError', 'BuildError')

def sweep(session, base, paths, label, allow_redirect_to=None):
    for path in paths:
        try:
            r = session.get(base + path, timeout=60, allow_redirects=True)
        except requests.RequestException as e:
            check(f'{label} {path}', False, str(e)[:80]); continue
        body = r.text
        ok = r.status_code < 500 and not any(b in body for b in BAD)
        check(f'{label} {path} -> {r.status_code}', ok, next((b for b in BAD if b in body), '') or (body[:60] if r.status_code >= 500 else ''))


selftest_mocktest.remove(db)
fx = selftest_mocktest.setup(db)
CODE, STU = fx['code'], fx['student']
U = STU['unique_code']
try:
    print('\n== admin pages ==')
    s = requests.Session()
    tok = csrf(s.get(ADMIN + '/admin_login').text)
    s.post(ADMIN + '/admin_login', data={'email': ADMIN_EMAIL, '_csrf_token': tok})
    s.post(ADMIN + '/admin_login', data={'password': ADMIN_PASSWORD, '_csrf_token': tok})
    assert 'mtPicker' in s.get(ADMIN + '/manage-tests').text, 'admin login failed'
    sweep(s, ADMIN, ['/admin_dashboard', '/courses', '/manage-catalog', '/manage-premium', '/manage_course_content', '/manage-tests',
                     f'/manage-tests?group={STU["name"]}', '/manage-practice-coding', '/manage-practice-quiz', '/manage-practice-papers',
                     '/manage_feedback', '/manage_purchases', '/admin/practice_questions', '/api/content-for-tests',
                     f"/api/test-descriptions/{fx['mock_sid']}", f"/api/test-descriptions/{fx['tcs_sid']}", f"/api/test-descriptions/{fx['code_sid']}",
                     f"/api/test-descriptions/{fx['comm_sid']}", f"/api/coding-panel/{fx['coding_id']}", f"/api/comm-sections/{fx['comm_id']}",
                     '/api/practice-quiz/questions', '/api/practice-coding/questions', '/api/papers/codes', '/api/premium-catalog',
                     '/api/purchases/attention', '/api/purchases/live', '/api/feedback/courses', '/api/notes', '/api/questions_by_code?code=' + CODE], 'admin')

    print('\n== student pages ==')
    u = requests.Session()
    page = u.get(USER + '/user_login').text
    ctok = re.search(r'name="csrf_token" value="([^"]+)"', page)
    ctok = ctok.group(1) if ctok else ''
    u.post(USER + '/user_login', data={'email': STU['email'], 'csrf_token': ctok})
    u.post(USER + '/user_login', data={'password': STU['password'], 'csrf_token': ctok})
    dash = u.get(f'{USER}/courses/{CODE}/{U}')
    check('student login works', dash.status_code == 200 and 'SELFTEST' in dash.text, str(dash.status_code))
    sweep(u, USER, ['/', '/courses', f'/courses/{STU["name"]}', f'/courses/{CODE}/{U}', f'/courses/{CODE}/{U}/premium', f'/course_shop/{CODE}/{U}',
                    f'/purchase/{CODE}/{U}', '/profile', f'/open/mock_test/{fx["mock_sid"]}/{CODE}/{U}', f'/tcs/{CODE}/{U}/{fx["tcs_sid"]}',
                    f'/coding/{CODE}/{U}?section_id={fx["code_sid"]}', f'/Communication/assessments/{CODE}/{U}',
                    f'/questions/topic/{U}/{CODE}', f'/questions/subject/{U}/{CODE}', f'/questions/year/{U}/{CODE}',
                    f'/practice-coding/{CODE}/{U}' if False else '/practice-coding', '/sapm/about', '/privacy', '/terms',
                    f'/test-login/{fx["mock_sid"]}/{fx["mock_key"]}/{CODE}/{U}', f'/paper-instruction/{fx["mock_sid"]}/{fx["mock_key"]}/{CODE}/{U}',
                    f'/test-instruction/{fx["mock_sid"]}/{fx["mock_key"]}/{CODE}/{U}', f'/Communication/coming_soon/{CODE}/{U}'], 'student')
    r = u.get(f'{USER}/coding/{CODE}/{U}?section_id={fx["code_sid"]}')
    check('the coding list page renders the shared layout for an empty list', r.status_code == 200 and 'testGrid' in r.text and ('No tests available' in r.text or 'test-card' in r.text))
finally:
    selftest_mocktest.remove(db)

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
