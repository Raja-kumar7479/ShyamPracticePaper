import re, sys
from datetime import datetime, timedelta
import mysql.connector, requests
from dotenv import dotenv_values

ADMIN, EMAIL, PASSWORD = 'http://127.0.0.1:5001', 'rajakumarvijeta7087@gmail.com', 'Raja@7479'
ROOT = '/Users/apple/Downloads/ShyamPracticePp'
sys.path.insert(0, f'{ROOT}/scripts/checks')
import selftest_student
v = dotenv_values('/Users/apple/Downloads/ShyamPracticePp/user_app/.env')
def db(q, p=()):
    c = mysql.connector.connect(host=v['DATABASE_HOST'], user=v['DATABASE_USER'], password=v['DATABASE_PASSWORD'], database=v['DATABASE_NAME'], autocommit=True)
    cur = c.cursor(dictionary=True); cur.execute(q, p); out = cur.fetchall() if cur.with_rows else []; cur.close(); c.close(); return out
results = []
def check(name, ok, detail=''):
    results.append(bool(ok)); print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ''))

codes = [r['code'] for r in db("SELECT code FROM courses")]
CODE = selftest_student.setup(db)['code']
def csrf(html):
    m = re.search(r'name="csrf-token"[^>]*content="([^"]+)"', html); return m.group(1) if m else ''
s = requests.Session(); tok = csrf(s.get(ADMIN + '/admin_login').text)
s.post(ADMIN + '/admin_login', data={'email': EMAIL, '_csrf_token': tok}); s.post(ADMIN + '/admin_login', data={'password': PASSWORD, '_csrf_token': tok})
page = s.get(ADMIN + '/manage-premium').text
assert 'Premium Catalog' in page, 'admin login failed'
H = {'X-CSRFToken': csrf(page) or tok}
full = {'label': 'SELFTEST Plan', 'price': '2000', 'discount': '0', 'discount_ends_at': '',
        'valid_until': (datetime.now() + timedelta(days=40)).strftime('%Y-%m-%dT%H:%M'), 'extra_days': '0'}
copy = {'headline': 'SELFTEST HEADLINE', 'details': 'SELFTEST<p>what you get</p>'}
plan_url = f'/api/premium-catalog/{CODE}/plans'
try:
    check('the plan editor and the required markers are on the page',
          'pcPlanList' in page and 'pcPlanTemplate' in page and page.count('required') >= 1)
    r = s.post(ADMIN + f'/api/premium-catalog/{CODE}/copy', json=copy, headers=H)
    check('page text is refused while a course has no plan', r.status_code == 400 and 'plan first' in r.text, r.text[:80])
    r = s.post(ADMIN + plan_url, json=full, headers=H)
    check('the first plan saves', r.status_code == 200, r.text[:70])
    if r.status_code == 200:
        full['id'] = r.json().get('id')
    r = s.post(ADMIN + f'/api/premium-catalog/{CODE}/copy', json=dict(copy, headline=''), headers=H)
    check('a headline is required', r.status_code == 400, r.text[:70])
    r = s.post(ADMIN + f'/api/premium-catalog/{CODE}/copy', json=dict(copy, details='<p>&nbsp;</p>'), headers=H)
    check('blank-looking What-you-get is refused', r.status_code == 400, r.text[:70])
    r = s.post(ADMIN + f'/api/premium-catalog/{CODE}/copy', json=copy, headers=H)
    check('with both filled the page text saves', r.status_code == 200, r.text[:70])
    for field, label in (('label', 'plan name'), ('price', 'amount')):
        r = s.post(ADMIN + plan_url, json={k: v for k, v in full.items() if k != field}, headers=H)
        check(f'a plan without a {label} is refused', r.status_code == 400, r.text[:70])
    r = s.post(ADMIN + plan_url, json=dict(full, valid_until=''), headers=H)
    check('a plan with no valid-until date is refused', r.status_code == 400, r.text[:70])
    r = s.post(ADMIN + plan_url, json=dict(full, label='SELFTEST Monthly', valid_until=(datetime.now() + timedelta(days=10)).strftime('%Y-%m-%dT%H:%M')), headers=H)
    check('a monthly name needs at least 30 days', r.status_code == 400 and '30 days' in r.text, r.text[:80])
    r = s.post(ADMIN + plan_url, json=dict(full, label='SELFTEST Yearly', valid_until=(datetime.now() + timedelta(days=100)).strftime('%Y-%m-%dT%H:%M')), headers=H)
    check('a yearly name needs at least 365 days', r.status_code == 400 and '365 days' in r.text, r.text[:80])
    r = s.post(ADMIN + plan_url, json=dict(full, extra_days='-5'), headers=H)
    check('negative extra days are refused', r.status_code == 400, r.text[:70])
    r = s.post(ADMIN + plan_url, json=dict(full, discount='50'), headers=H)
    check('a discount without its valid-until date is refused', r.status_code == 400 and 'valid until' in r.text.lower(), r.text[:80])
    until = (datetime.now() + timedelta(days=20)).strftime('%Y-%m-%dT%H:%M')
    r = s.post(ADMIN + plan_url, json=dict(full, discount='50', discount_ends_at=until, extra_days='15'), headers=H)
    ok = r.status_code == 200 and any(p['label'] == 'SELFTEST Plan' and p['payable'] == 1000 for p in r.json().get('plans', []))
    check('there is still exactly one SELFTEST Plan (a second save with the same name updates, not duplicates)',
          sum(1 for p in r.json().get('plans', []) if p['label'] == 'SELFTEST Plan') == 1)
    check('a complete plan saves with its discount applied', ok, r.text[:80])
    r = s.post(ADMIN + plan_url, json=dict(full, label='SELFTEST till GATE 2031', discount='0', discount_ends_at='',
                                           valid_until='2032-01-01T00:00'), headers=H)
    check('a dated plan must match the year in its name', r.status_code == 400 and '2031' in r.text, r.text[:80])
    r = s.post(ADMIN + plan_url, json=dict(full, label='SELFTEST till GATE 2031', discount='0', discount_ends_at='',
                                           valid_until='2031-06-01T00:00'), headers=H)
    check('it saves when the year matches', r.status_code == 200, r.text[:80])
finally:
    db("DELETE FROM premium_plans WHERE label LIKE 'SELFTEST%'")
    db("DELETE FROM premium_catalog WHERE headline LIKE 'SELFTEST%' OR details LIKE 'SELFTEST%'")
    selftest_student.remove(db)
left = (db("SELECT COUNT(*) n FROM premium_plans WHERE label LIKE 'SELFTEST%'")[0]['n']
        + db("SELECT COUNT(*) n FROM premium_catalog WHERE headline LIKE 'SELFTEST%'")[0]['n'])
print(f"\nSELFTEST rows left: {left}")
print(f"RESULT: {sum(1 for r in results if r)}/{len(results)} passed")
sys.exit(0 if all(results) and left == 0 else 1)
