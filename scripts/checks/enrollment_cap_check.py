import re, sys, threading
import mysql.connector, requests
from dotenv import dotenv_values

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
USER = 'http://127.0.0.1:5002'
sys.path.insert(0, '/Users/apple/Downloads/ShyamPracticePp/scripts/checks')
import selftest_student
EMAIL, PASSWORD = selftest_student.EMAIL, selftest_student.PASSWORD
CAP = 3
TAG = 'SELFTEST'
CODES = ['SELFTESTA', 'SELFTESTB', 'SELFTESTC']
v = dotenv_values(f'{ROOT}/user_app/.env')

def db(q, p=()):
    c = mysql.connector.connect(host=v['DATABASE_HOST'], user=v['DATABASE_USER'], password=v['DATABASE_PASSWORD'],
                                database=v['DATABASE_NAME'], autocommit=True)
    cur = c.cursor(dictionary=True); cur.execute(q, p)
    out = cur.fetchall() if cur.with_rows else []
    cur.close(); c.close(); return out

results = []
def check(name, ok, detail=''):
    results.append(bool(ok)); print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ''))

def count():
    return db("SELECT COUNT(*) n FROM enrollment WHERE email=%s", (EMAIL,))[0]['n']

def cleanup():
    db("DELETE FROM enrollment_payment WHERE course_code IN ('SELFTESTA','SELFTESTB','SELFTESTC')")
    db("DELETE FROM enrollment WHERE code IN ('SELFTESTA','SELFTESTB','SELFTESTC')")
    db("DELETE FROM courses WHERE code IN ('SELFTESTA','SELFTESTB','SELFTESTC')")
    db("DELETE FROM course_group_codes WHERE code IN ('SELFTESTA','SELFTESTB','SELFTESTC')")

cleanup()
selftest_student.setup(db)
before = count()
group = db("SELECT name FROM courses LIMIT 1")[0]['name']
for code in CODES:
    db("INSERT INTO course_group_codes (group_name, code, label, position) VALUES (%s,%s,%s,0)", (group, code, f'{TAG} probe'))
    db("INSERT INTO courses (code, name, subgroup, description) VALUES (%s,%s,%s,%s)", (code, group, f'{TAG} sub', f'{TAG} probe course'))

s = requests.Session()
page = s.get(f'{USER}/user_login').text
tok = (re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page) or re.search(r'name="csrf-token"[^>]*content="([^"]+)"', page))
tok = tok.group(1) if tok else ''
s.post(f'{USER}/user_login', data={'email': EMAIL, 'csrf_token': tok})
s.post(f'{USER}/user_login', data={'password': PASSWORD, 'csrf_token': tok})
home = s.get(f'{USER}/').text
m = re.search(r'name="csrf-token"[^>]*content="([^"]+)"', home) or re.search(r'csrf_token["\']?\s*[:=]\s*["\']([^"\']+)', home)
CSRF = m.group(1) if m else tok
assert 'logout' in home.lower() or 'dashboard' in home.lower(), 'login failed'

def enroll(code, wrong_captcha=False):
    cap = s.get(f'{USER}/api/enrollment/start').json().get('captcha', '')
    if wrong_captcha:
        cap = 'ZZZZZZ'
    return s.post(f'{USER}/api/enrollment/complete/pre-check',
                  headers={'X-CSRFToken': CSRF},
                  data={'course_code': code, 'course_name': group, 'captcha': cap})

print(f'\nstarting enrolments for the account: {before} (cap {CAP})')

print('\n== the fee is gone ==')
r = s.post(f'{USER}/api/enrollment/payment/create_order', headers={'X-CSRFToken': CSRF}, json={})
check('payment order endpoint removed', r.status_code == 404, str(r.status_code))
r = s.post(f'{USER}/api/enrollment/payment/success', headers={'X-CSRFToken': CSRF}, json={})
check('payment success endpoint removed', r.status_code == 404, str(r.status_code))
r = s.get(f'{USER}/api/enrollment/check?course_code={CODES[0]}').json()
check('the check endpoint never asks for payment', r.get('payment_required') is False and 'price' not in r, str(r))

print('\n== the cap holds ==')
for i, code in enumerate(CODES[:CAP - before]):
    r = enroll(code)
    ok = r.json().get('success') is True
    check(f'enrolment {before + i + 1} of {CAP} is allowed', ok and count() == before + i + 1, f"{r.status_code} {r.text[:70]}")
EXTRA = CODES[CAP - before]
r = enroll(EXTRA)
check(f'enrolment {CAP + 1} is refused', r.json().get('success') is False and str(CAP) in r.json().get('error', ''), r.text[:80])
check('and nothing was written', count() == CAP, f'count={count()}')
r = s.get(f'{USER}/api/enrollment/check?course_code={EXTRA}').json()
check('the check endpoint reports the limit', r.get('status') == 'limit_reached' and r.get('limit') == CAP, str(r))

print('\n== bypass attempts ==')
outcomes = []
def burst(code):
    try:
        outcomes.append(enroll(code).json().get('success'))
    except Exception as e:
        outcomes.append(f'err {e}')
threads = [threading.Thread(target=burst, args=(CODES[1 + (i % 2)],)) for i in range(8)]
for t in threads: t.start()
for t in threads: t.join()
check('8 parallel requests cannot slip past the cap', count() == CAP and not any(o is True for o in outcomes), f'count={count()} outcomes={outcomes}')
r = enroll(EXTRA, wrong_captcha=True)
check('a wrong captcha is still refused', r.json().get('success') is False, r.text[:60])
r = s.post(f'{USER}/api/enrollment/complete/pre-check', data={'course_code': EXTRA, 'course_name': group, 'captcha': 'ABC123'})
check('a request without the CSRF token is refused', r.status_code in (400, 403), str(r.status_code))
blocked = False
try:
    db("INSERT INTO enrollment (email, code, name, unique_code, payment_id) VALUES (%s,%s,%s,%s,%s)",
       (EMAIL, EXTRA, group, f'{TAG}direct', f'FREE_{TAG}'))
except Exception as e:
    blocked = 'Enrollment limit reached' in str(e)
check('even a direct database insert is blocked by the trigger', blocked and count() == CAP, f'count={count()}')

print('\n== nothing else was disturbed ==')
check('the account keeps its original courses', {r['code'] for r in db("SELECT code FROM enrollment WHERE email=%s", (EMAIL,))} >= {selftest_student.CODE})
check('no platform fee was ever charged', db("SELECT COUNT(*) n FROM enrollment_payment WHERE payment_status='Paid' AND amount_paid > 0")[0]['n'] == 0)

cleanup()
left = (db("SELECT COUNT(*) n FROM courses WHERE code LIKE 'SELFTEST%'")[0]['n']
        + db("SELECT COUNT(*) n FROM enrollment WHERE code LIKE 'SELFTEST%'")[0]['n']
        + db("SELECT COUNT(*) n FROM course_group_codes WHERE code LIKE 'SELFTEST%'")[0]['n'])
check('the account is back to where it started', count() == before, f'{count()} vs {before}')
selftest_student.remove(db)
print(f"\n{TAG} rows left: {left}")
print(f"RESULT: {sum(1 for r in results if r)}/{len(results)} passed")
sys.exit(0 if all(results) and left == 0 else 1)
