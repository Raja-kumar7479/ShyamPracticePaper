import re, subprocess, sys, time
from datetime import datetime, timedelta
import mysql.connector, requests
from dotenv import dotenv_values
from playwright.sync_api import sync_playwright

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
USER, ADMIN = 'http://127.0.0.1:5002', 'http://127.0.0.1:5001'
ADMIN_EMAIL, ADMIN_PASSWORD = 'rajakumarvijeta7087@gmail.com', 'Raja@7479'
sys.path.insert(0, f'{ROOT}/scripts/checks')
import selftest_student
EMAIL, PASSWORD = selftest_student.EMAIL, selftest_student.PASSWORD
SID, K_FREE, K_PREM = 'SELFTESTSUITE', 'free_' + '1' * 20, 'prem_' + '1' * 20
FMT = '%d %b %Y, %I:%M %p'
v = dotenv_values(f'{ROOT}/user_app/.env')

def db(q, p=()):
    c = mysql.connector.connect(host=v['DATABASE_HOST'], user=v['DATABASE_USER'], password=v['DATABASE_PASSWORD'], database=v['DATABASE_NAME'], autocommit=True)
    cur = c.cursor(dictionary=True); cur.execute(q, p); out = cur.fetchall() if cur.with_rows else []; cur.close(); c.close(); return out
results = []
def check(name, ok, detail=''):
    results.append(bool(ok)); print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ''))
def sub(code, order, expires, amount=100000, starts=None, plan=None):
    plan = plan or MKEY
    db("INSERT INTO pcp_subscriptions (email,course_code,plan,plan_label,amount_paise,razorpay_order_id,razorpay_payment_id,status,starts_at,expires_at)"
       " VALUES (%s,%s,%s,%s,%s,%s,%s,'active',%s,%s)",
       (EMAIL, code, plan, plan.replace('-', ' ').title(), amount, order, order.replace('ORDER', 'PAY'), starts or datetime.now(), expires))
BARE, BARE_U = 'SLF2', 'SELFTEST-UNIQUE-CODE-2222222222222222222'
def bare_course(create):
    db("DELETE FROM premium_plans WHERE code=%s", (BARE,)); db("DELETE FROM premium_catalog WHERE code=%s", (BARE,))
    db("DELETE FROM enrollment WHERE code=%s AND payment_id='SELFTEST_ENROLL'", (BARE,)); db("DELETE FROM courses WHERE code=%s", (BARE,))
    db("DELETE FROM course_group_codes WHERE code=%s", (BARE,))
    if not create:
        return False
    if db("SELECT COUNT(*) n FROM enrollment WHERE email=%s", (EMAIL,))[0]['n'] >= 3:
        return False
    db("INSERT INTO course_group_codes (group_name, code, label, position) VALUES ('SELFTEST GROUP',%s,'SELFTEST COURSE 2',98)", (BARE,))
    db("INSERT INTO courses (code, name, subgroup, description, guest_access_code) VALUES (%s,'SELFTEST GROUP','SELFTEST','<p>SELFTEST</p>','selftest00000002')", (BARE,))
    db("INSERT INTO enrollment (email, name, code, unique_code, payment_id, enrollment_date) VALUES (%s,'SELFTEST GROUP',%s,%s,'SELFTEST_ENROLL',NOW())", (EMAIL, BARE, BARE_U))
    return True
def clean():
    db("DELETE FROM premium_plans WHERE label LIKE 'SELFTEST%'")
    db("DELETE FROM pcp_subscriptions WHERE plan LIKE 'selftest%' AND status='created'")
    bare_course(False)
    for t in ('test_attempt_details', 'test_result', 'user_test_log', 'test_feedback', 'test_questions', 'test_description'):
        db(f"DELETE FROM {t} WHERE test_key IN (%s,%s)", (K_FREE, K_PREM))
    db("DELETE FROM course_content WHERE section_id=%s", (SID,))
    db("DELETE FROM pcp_subscriptions WHERE razorpay_order_id LIKE 'SELFTEST%'")
    db("DELETE FROM premium_catalog WHERE headline LIKE 'SELFTEST%' OR details LIKE 'SELFTEST%'")

student = selftest_student.setup(db)
CODE = student['code']
_other = db("SELECT code, name FROM courses WHERE code <> %s ORDER BY code LIMIT 1", (CODE,))[0]
db("INSERT INTO enrollment (email, name, code, unique_code, payment_id, enrollment_date) VALUES (%s,%s,%s,'SELFTEST-OTHER-CODE-000000000000000000','SELFTEST_ENROLL',NOW())",
   (EMAIL, _other['name'], _other['code']))
enr = {CODE: {'name': student['name'], 'unique_code': student['unique_code']},
       _other['code']: {'name': _other['name'], 'unique_code': 'SELFTEST-OTHER-CODE-000000000000000000'}}
MKEY, YKEY = 'selftest-monthly', 'selftest-yearly'
DKEY = 'selftest-till-gate-2029'
OTHER = next(c for c in enr if c != CODE)
U, OU = enr[CODE]['unique_code'], enr[OTHER]['unique_code']
clean()
db("INSERT INTO course_content (code,name,stream,section,section_id,title,subtitle,label,price,discount,details,status)"
   " VALUES (%s,%s,'Self test','mock_test',%s,'SELFTEST suite block','s','Free',0,0,'<p>x</p>[[PREMIUM]]','active')", (CODE, enr[CODE]['name'], SID))
for key, title, access in ((K_FREE, 'SELFTEST free', 'free'), (K_PREM, 'SELFTEST premium', 'paid')):
    db("INSERT INTO test_description (test_id,test_key,subject_title,subject_subtitle,total_questions,total_marks,total_duration_minutes,show_calculator,access_label)"
       " VALUES (%s,%s,%s,'x',1,1,5,1,%s)", (SID, key, title, access))
    d = db("SELECT id FROM test_description WHERE test_key=%s", (key,))[0]['id']
    db("INSERT INTO test_questions (test_id,test_key,test_description_id,section_id,section_name,question_type,question_number,question_text,"
       "option_a,option_b,option_c,option_d,correct_option,correct_marks,negative_marks,question_level) VALUES (%s,%s,%s,'1','A','MCQ',1,'2+2','3','4','5','6','B',1,0,'Easy')", (SID, key, d))

def csrf(html):
    m = re.search(r'name="csrf-token"[^>]*content="([^"]+)"', html); return m.group(1) if m else ''
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
s = requests.Session()
s.mount('http://', HTTPAdapter(max_retries=Retry(total=5, backoff_factor=0.8, allowed_methods=False, status_forcelist=[])))
tok = csrf(s.get(ADMIN + '/admin_login').text)
s.post(ADMIN + '/admin_login', data={'email': ADMIN_EMAIL, '_csrf_token': tok}); s.post(ADMIN + '/admin_login', data={'password': ADMIN_PASSWORD, '_csrf_token': tok})
H = {'X-CSRFToken': csrf(s.get(ADMIN + '/manage-premium').text) or tok}
when = lambda days: (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%dT%H:%M')
COPY = {'headline': 'SELFTEST HEADLINE', 'details': 'SELFTEST<p>SELFTEST WHAT YOU GET</p>'}
PLAN = {'label': 'SELFTEST Monthly', 'price': '2000', 'discount': '50', 'discount_ends_at': when(20),
        'valid_until': when(30), 'extra_days': '15'}
YEAR_PLAN = {'label': 'SELFTEST Yearly', 'price': '12000', 'discount': '25', 'discount_ends_at': when(300),
             'valid_until': when(366), 'extra_days': '0'}
plan_ids = {}

def save_copy(**kw):
    return s.post(ADMIN + f'/api/premium-catalog/{CODE}/copy', json=dict(COPY, **kw), headers=H)

approvals = []

def save_plan(base=None, **kw):
    body = dict(base or PLAN, **kw)
    key = body['label']
    if key in plan_ids:
        body['id'] = plan_ids[key]
    r = s.post(ADMIN + f'/api/premium-catalog/{CODE}/plans', json=body, headers=H)
    if r.status_code == 409 and r.json().get('needs_approval'):
        held = r.json()['holders']
        approvals.append(held)
        r = s.post(ADMIN + f'/api/premium-catalog/{CODE}/plans', json=dict(body, approved_holders=held['active'] + held['pending']), headers=H)
    if r.status_code == 200:
        for pl in r.json().get('plans', []):
            plan_ids[pl['label']] = pl['id']
    return r

save = save_plan
run_job = lambda: subprocess.run([sys.executable, '-m', 'admin.manage_modules.cleanup_script'], cwd=f'{ROOT}/admin_app', capture_output=True, text=True, timeout=120)

try:
    print('\n== plan rules ==')
    if bare_course(True):
        r = s.post(ADMIN + f'/api/premium-catalog/{BARE}/copy', json=COPY, headers=H)
        check('page text is refused while a course has no plan', r.status_code == 400 and 'plan first' in r.text, r.text[:80])
    else:
        print('  [SKIP] page text refused with no plan - the student already has 3 enrolments, no room for a SELFTEST course')
    r = save(discount_ends_at=when(-1)); check('a discount end already in the past is refused', r.status_code == 400 and 'past' in r.text)
    r = save(discount_ends_at=''); check('a discount with no end date is refused', r.status_code == 400 and 'valid until' in r.text.lower(), r.text[:80])
    r = save(extra_days='x'); check('extra days must be a whole number', r.status_code == 400)
    r = save(); check('a plan saves; days are counted by the server (30 + 15 extra)', r.status_code == 200
                      and any(pl['label'] == PLAN['label'] and pl['payable'] == 1000 and pl['days'] in (44, 45) for pl in r.json()['plans']), r.text[:80])
    r = save(YEAR_PLAN); check('a second plan saves alongside it', r.status_code == 200 and len(r.json()['plans']) >= 2)
    r = save_copy(); check('with a plan in place the page text saves', r.status_code == 200, r.text[:70])
    r = save_copy(headline=''); check('a headline is required', r.status_code == 400)
    r = save(label='SELFTEST till GATE 2029', price='4999', discount='0', discount_ends_at='', valid_until='2030-01-01T00:00')
    check('a dated plan must match the year in its name', r.status_code == 400 and '2029' in r.text, r.text[:90])
    r = save(label='SELFTEST till GATE 2029', price='4999', discount='0', discount_ends_at='', valid_until='2029-03-01T00:00')
    check('the dated plan saves when the year matches', r.status_code == 200, r.text[:80])
    r = save(label='SELFTEST Monthly', valid_until=when(20))
    check('a monthly plan cannot end sooner than 30 days from today', r.status_code == 400 and '30 days' in r.text, r.text[:90])
    r = save(label='SELFTEST Yearly', valid_until=when(200), discount='0', discount_ends_at='', price='12000', extra_days='0')
    check('a yearly plan cannot end sooner than 365 days from today', r.status_code == 400 and '365 days' in r.text, r.text[:90])
    r = save(YEAR_PLAN)
    r = save(label='SELFTEST no date', price='500', discount='0', discount_ends_at='', valid_until='')
    check('a plan without a date is refused', r.status_code == 400 and 'required' in r.text.lower())

    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome', headless=True); ctx = b.new_context(viewport={'width': 1400, 'height': 1000}); ctx.set_default_timeout(15000)
        pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)[:120]))
        pg.goto(f'{USER}/user_login', wait_until='domcontentloaded'); time.sleep(0.8)
        pg.fill('#email', EMAIL); pg.locator('#email').press('Enter'); pg.wait_for_load_state('domcontentloaded'); time.sleep(1.2)
        pg.fill('#password', PASSWORD); pg.locator('#password').press('Enter'); pg.wait_for_load_state('domcontentloaded'); time.sleep(2)
        tokp = lambda: pg.evaluate("(document.querySelector('meta[name=csrf-token]')||{}).content")
        order = lambda plan: pg.request.post(USER + '/api/premium/order', data='{"plan":"%s","phone":"9876543210","course_code":"%s"}' % (plan, CODE),
                                             headers={'Content-Type': 'application/json', 'X-CSRFToken': tokp()})
        premium = lambda: (pg.goto(f'{USER}/courses/{CODE}/{U}/premium', wait_until='domcontentloaded'), time.sleep(1.8))
        card = lambda k: pg.locator(f'[data-plan-card="{k}"]').inner_text().lower().replace(',', '')
        cards = lambda: pg.locator('.pm-plan').count()

        print('\n== premium page from the catalog ==')
        premium(); body = pg.locator('body').inner_text()
        check('headline and What-you-get come from the catalog', 'SELFTEST HEADLINE' in body and 'SELFTEST WHAT YOU GET' in body)
        check('a discount shows an ON SALE ribbon with % off and its own offer end',
              '50% off' in card(MKEY) and 'ends' in card(MKEY) and 'ends' in card(YKEY))
        db("UPDATE premium_plans SET discount_ends_at=%s WHERE code=%s AND plan_key=%s", (datetime.now() - timedelta(minutes=1), CODE, MKEY))
        premium(); check('a discount past its own end stops applying on that plan only',
                         pg.locator(f'[data-plan-card="{MKEY}"] .pm-plan__sale').count() == 0 and '2000' in card(MKEY)
                         and pg.locator(f'[data-plan-card="{YKEY}"] .pm-plan__sale').count() == 1
                         and pg.evaluate(f"window.PCP_BILLING.plans['{MKEY}'].paise") == 200000)
        save(); premium()
        check('list price cut through, payable shown, end date and days shown',
              '2000' in card(MKEY) and '1000' in card(MKEY) and 'access until' in card(MKEY) and 'days left' in card(MKEY))
        check('extra days push the end date out', ('45 days' in card(MKEY)) or ('44 days' in card(MKEY)), card(MKEY)[:90])
        check('the GATE 2029 plan shows its own end date', 'access until' in card(DKEY) and '2029' in card(DKEY), card(DKEY)[:70])
        check('no sale-expiry wording anywhere on the premium page', 'on sale until' not in body.lower() and 'sale ended' not in body.lower() and 'not on sale' not in body.lower())
        cfg = pg.evaluate("window.PCP_BILLING.plans"); check('checkout amounts are the discounted paise', cfg[MKEY]['paise'] == 100000 and cfg[YKEY]['paise'] == 900000)

        print('\n== lock / unlock per course ==')
        pg.goto(f'{USER}/open/mock_test/{SID}/{CODE}/{U}', wait_until='domcontentloaded'); time.sleep(1.0)
        href = pg.locator('a.btn-unlock-custom').first.get_attribute('href') or ''
        check('premium test is locked and Unlock leads to this course premium page', href.startswith(f'/courses/{CODE}/{U}/premium'))
        check('its questions are refused', pg.request.get(USER + f'/fetch-questions/{SID}/{K_PREM}/{CODE}/{U}', max_redirects=0).status == 403)
        pg.goto(f'{USER}/courses/{CODE}/{U}/resource/{SID}', wait_until='domcontentloaded'); time.sleep(0.8)
        check('the [[PREMIUM]] link in details points here', (pg.locator('a.cd-premium-link').first.get_attribute('href') or '').startswith(f'/courses/{CODE}/{U}/premium'))

        print('\n== the premium link belongs to Free content only ==')
        cid = db("SELECT id FROM course_content WHERE section_id=%s", (SID,))[0]['id']
        marked = '<p>x</p>[[PREMIUM]]'
        stored = lambda: db("SELECT details, label FROM course_content WHERE id=%s", (cid,))[0]
        field = lambda f, v: s.post(ADMIN + f'/update_content_field/{cid}', json={'field': f, 'value': v}, headers=H)
        field('price', '100')
        r = field('label', 'Paid')
        check('switching a Free item to Paid drops the premium link from its details',
              r.status_code == 200 and '[[PREMIUM]]' not in (stored()['details'] or ''), r.text[:80])
        r = field('details', marked)
        check('the marker cannot be typed back in while the item is Paid',
              r.status_code == 200 and '[[PREMIUM]]' not in (stored()['details'] or ''), r.text[:80])
        pg.goto(f'{USER}/courses/{CODE}/{U}/resource/{SID}', wait_until='domcontentloaded'); time.sleep(0.8)
        body = pg.locator('body').inner_text()
        check('a Paid item shows no premium link and never the raw marker',
              pg.locator('a.cd-premium-link').count() == 0 and '[[PREMIUM]]' not in body)
        db("UPDATE course_content SET details=%s WHERE id=%s", (marked, cid))
        pg.reload(wait_until='domcontentloaded'); time.sleep(0.8)
        check('even a marker left in an older Paid row renders as nothing, not as text',
              pg.locator('a.cd-premium-link').count() == 0 and '[[PREMIUM]]' not in pg.locator('body').inner_text())
        edit = lambda **kw: s.post(ADMIN + f'/update_content/{cid}', json=dict(
            {'title': 'SELFTEST suite block', 'subtitle': 's', 'stream': 'Self test', 'status': 'active',
             'price': 0, 'discount': 0, 'max_test_descriptions': '', 'syllabus_position': 'below',
             'syllabus_label': '', 'remove_syllabus': False, 'details': marked}, **kw), headers=H)
        r = edit(label='Paid', price=100)
        check('the edit dialog also refuses to store it on Paid content',
              r.status_code == 200 and '[[PREMIUM]]' not in (stored()['details'] or ''), r.text[:80])
        r = edit(label='Free', price=0)
        check('and keeps it once the item is Free again',
              r.status_code == 200 and '[[PREMIUM]]' in (stored()['details'] or ''), r.text[:80])
        pg.goto(f'{USER}/courses/{CODE}/{U}/resource/{SID}', wait_until='domcontentloaded'); time.sleep(0.8)
        check('the link is back on the Free item', pg.locator('a.cd-premium-link').count() == 1)

        sub(OTHER, 'SELFTEST_ORDER_OTHER', datetime.now() + timedelta(days=20))
        check('premium bought for the other course does not unlock this one', pg.request.get(USER + f'/fetch-questions/{SID}/{K_PREM}/{CODE}/{U}', max_redirects=0).status == 403)
        db("DELETE FROM pcp_subscriptions WHERE razorpay_order_id='SELFTEST_ORDER_OTHER'")
        exp = datetime.now().replace(second=0, microsecond=0) + timedelta(days=20)
        sub(CODE, 'SELFTEST_ORDER_A', exp, plan=MKEY)
        check('premium bought for this course unlocks it', pg.request.get(USER + f'/fetch-questions/{SID}/{K_PREM}/{CODE}/{U}', max_redirects=0).status == 200)
        pg.goto(f'{USER}/open/mock_test/{SID}/{CODE}/{U}', wait_until='domcontentloaded'); time.sleep(1.0)
        check('no Unlock button any more', pg.locator('a.btn-unlock-custom').count() == 0)

        print('\n== member state, exact dates, frozen price ==')
        premium(); body = pg.locator('body').inner_text()
        check('premium page: member panel names the plan and the exact end date', pg.locator('#pmMember').count() == 1 and 'You are a Premium member' in body
              and 'Selftest Monthly' in body and exp.strftime(FMT) in body and 'days left' in body)
        check('a member sees no plan cards, no prices, no checkout, no Subscribe', cards() == 0 and '\u20b9' not in body and pg.locator('#pmModal').count() == 0 and 'Subscribe' not in body)
        check('What you get and the FAQ stay on the page for them', 'What you get' in body and 'SELFTEST WHAT YOU GET' in body and pg.locator('.pm-faq').count() == 1)
        r = order(MKEY); check('buying again with 20 days left is refused', r.status == 409)
        r = pg.request.post(USER + '/api/premium/order', data='{"plan":"%s","phone":"9876543210","course_code":"ZZZQ"}' % MKEY,
                            headers={'Content-Type': 'application/json', 'X-CSRFToken': tokp()})
        check('an order for a course the student is not enrolled in is refused', r.status == 403, f'{r.status} {r.text()[:60]}')
        r = pg.request.post(USER + '/api/premium/verify', data='{"razorpay_order_id":"order_fake","razorpay_payment_id":"pay_fake","razorpay_signature":"bad"}',
                            headers={'Content-Type': 'application/json', 'X-CSRFToken': tokp()})
        check('a forged payment confirmation is refused', r.status in (400, 404), f'{r.status} {r.text()[:60]}')
        r = pg.request.post(USER + '/api/premium/order', data='{"plan":"%s","phone":"9876543210","course_code":"%s"}' % (MKEY, CODE),
                            headers={'Content-Type': 'application/json'})
        check('an order without the CSRF token is refused', r.status == 403, f'{r.status} {r.text()[:60]}')
        pg.goto(f'{USER}/courses/{CODE}/{U}', wait_until='domcontentloaded'); time.sleep(1.0)
        check('dashboard: the nav badge names the plan and there is no "Premium is active" strip',
              'Premium' in pg.locator('.plan-badge--premium, .topbar-plan__text').first.inner_text() and pg.locator('.pm-strip').count() == 0)
        asked = len(approvals)
        r = save(price='3000', discount='0', discount_ends_at=''); check('admin raises the monthly price', r.status_code == 200, r.text[:70])
        check('...only after approving it for the student who already holds the plan', len(approvals) == asked + 1 and approvals[-1]['active'] >= 1, str(approvals[-1:]))
        db("UPDATE pcp_subscriptions SET expires_at=DATE_SUB(NOW(), INTERVAL 1 MINUTE) WHERE razorpay_order_id='SELFTEST_ORDER_A'")
        premium(); check('new buyers see the new price, and the ribbon follows the discount',
                         '3000' in card(MKEY) and pg.locator(f'[data-plan-card="{MKEY}"] .pm-plan__sale').count() == 0
                         and pg.locator(f'[data-plan-card="{YKEY}"] .pm-plan__sale').count() == 1)
        db("UPDATE pcp_subscriptions SET expires_at=%s WHERE razorpay_order_id='SELFTEST_ORDER_A'", (exp,))
        row = db("SELECT amount_paise FROM pcp_subscriptions WHERE razorpay_order_id='SELFTEST_ORDER_A'")[0]
        pg.goto(f'{USER}/purchase/{CODE}/{U}', wait_until='domcontentloaded'); time.sleep(1.0); pb = pg.locator('body').inner_text()
        check('the existing purchase keeps what it paid', row['amount_paise'] == 100000 and '1000.00' in pb.replace(',', ''))
        check('purchases page shows the exact date and time', exp.strftime(FMT) in pb and CODE in pb)
        save()

        print('\n== remove a plan / nothing set ==')
        def remove(label):
            return s.delete(ADMIN + f'/api/premium-catalog/{CODE}/plans/{plan_ids.pop(label)}', headers=H)
        r = remove(PLAN['label']); check('admin removes the monthly plan while a student holds it', r.status_code == 200 and 'keep their access' in r.text, r.text[:100])
        premium()
        check('the holder still sees the member panel with the removed plan\'s name', pg.locator('#pmMember').count() == 1 and 'Selftest Monthly' in pg.locator('body').inner_text())
        check('the student who already bought it keeps access', pg.request.get(USER + f'/fetch-questions/{SID}/{K_PREM}/{CODE}/{U}', max_redirects=0).status == 200)
        pg.goto(f'{USER}/courses/{CODE}/{U}', wait_until='domcontentloaded'); time.sleep(0.8)
        check('dashboard still shows their plan in the nav, no offer strip', 'Premium' in pg.locator('.plan-badge--premium, .topbar-plan__text').first.inner_text() and pg.locator('.pm-strip--offer').count() == 0)
        pg.goto(f'{USER}/purchase/{CODE}/{U}', wait_until='domcontentloaded'); time.sleep(0.8)
        check('their purchase page still shows the plan they bought', 'Selftest Monthly' in pg.locator('body').inner_text())
        db("DELETE FROM pcp_subscriptions WHERE razorpay_order_id='SELFTEST_ORDER_A'")
        premium()
        check('the removed plan is gone for new students, the others stay', pg.locator(f'[data-plan-card="{MKEY}"]').count() == 0 and pg.locator(f'[data-plan-card="{YKEY}"]').count() == 1)
        r = order(MKEY); check('a new order for the removed plan is refused', r.status in (400, 404, 409), f'{r.status} {r.text()[:60]}')
        if db("SELECT 1 FROM enrollment WHERE code=%s AND payment_id='SELFTEST_ENROLL'", (BARE,)):
            pg.goto(f'{USER}/courses/{BARE}/{BARE_U}/premium', wait_until='domcontentloaded'); time.sleep(1.5); body = pg.locator('body').inner_text()
            check('a course with no plan shows only "coming soon" - no prices, no What you get, no FAQ, no default Monthly/Yearly',
                  'coming soon' in body.lower() and cards() == 0 and 'What you get' not in body and pg.locator('.pm-faq').count() == 0
                  and 'Monthly' not in body and 'Yearly' not in body and pg.locator('.pm-soon').count() == 1, body[:120].replace('\n', ' '))
            check('the coming-soon page still has a way back to the course', pg.locator('.pm-soon__back').count() == 1)
            pg.goto(f'{USER}/courses/{BARE}/{BARE_U}', wait_until='domcontentloaded'); time.sleep(0.8)
            check('its dashboard shows no premium strip', pg.locator('.pm-strip').count() == 0)
            r = s.post(ADMIN + f'/api/premium-catalog/{BARE}/plans', json=dict(PLAN, label='SELFTEST Bare plan'), headers=H)
            check('the admin sets a plan for it', r.status_code == 200, r.text[:80])
            r = s.post(ADMIN + f'/api/premium-catalog/{BARE}/copy', json=COPY, headers=H)
            check('now the page text is accepted', r.status_code == 200, r.text[:80])
            pg.goto(f'{USER}/courses/{BARE}/{BARE_U}/premium', wait_until='domcontentloaded'); time.sleep(1.5); body = pg.locator('body').inner_text()
            check('and the student page comes alive with the plan and What you get', cards() == 1 and 'SELFTEST Bare plan' in body and 'What you get' in body)
        else:
            print('  [SKIP] coming-soon page - no room for a SELFTEST course')
        save()
        sub(CODE, 'SELFTEST_ORDER_A', exp, plan=MKEY)

        db("DELETE FROM pcp_subscriptions WHERE razorpay_order_id='SELFTEST_ORDER_A'")
        premium()
        r = order(MKEY); check('with no subscription the order passes the gate (only the gateway config stops it here)', r.status in (200, 503), f'{r.status} {r.text()[:60]}')

        print('\n== renewal and auto-lock ==')
        soon = datetime.now().replace(second=0, microsecond=0) + timedelta(days=2, hours=1)
        sub(CODE, 'SELFTEST_ORDER_SOON', soon, starts=datetime.now() - timedelta(days=28), plan=MKEY)
        pg.goto(f'{USER}/courses/{CODE}/{U}', wait_until='domcontentloaded'); time.sleep(1.0); st = pg.locator('.pm-strip--active').inner_text()
        check('dashboard: only near the end a strip appears - "ends in 2 days", no Renew', 'ends in 2 days' in st and 'Renew' not in st
              and 'again once it ends' in st and 'Premium is active' not in st)
        premium(); body = pg.locator('body').inner_text()
        check('premium page near the end: still only the member panel with the exact end date, no prices or buy buttons',
              pg.locator('#pmMember').count() == 1 and soon.strftime(FMT) in body and 'Renew' not in body
              and pg.locator('button.pm-subscribe[data-plan]').count() == 0 and cards() == 0)
        r = order(MKEY); check('no early re-buy: an order 2 days before the end is refused', r.status == 409, f'{r.status} {r.text()[:60]}')
        r = order(DKEY); check('...for every plan', r.status == 409, f'{r.status} {r.text()[:60]}')
        pg.goto(f'{USER}/purchase/{CODE}/{U}', wait_until='domcontentloaded'); time.sleep(1.0); pb = pg.locator('body').inner_text()
        check('purchases: "Expires in 2 days", exact time, no Renew', 'Expires in 2 days' in pb and soon.strftime(FMT) in pb and 'Renew' not in pb)
        db("UPDATE pcp_subscriptions SET expires_at=%s WHERE razorpay_order_id='SELFTEST_ORDER_SOON'", (datetime.now() - timedelta(minutes=5),))
        check('the moment it expires, the test is locked again', pg.request.get(USER + f'/fetch-questions/{SID}/{K_PREM}/{CODE}/{U}', max_redirects=0).status == 403)
        pg.goto(f'{USER}/courses/{CODE}/{U}', wait_until='domcontentloaded'); time.sleep(0.8)
        check('dashboard goes back to Go Premium', pg.locator('.pm-strip--offer').count() == 1)
        pg.goto(f'{USER}/purchase/{CODE}/{U}', wait_until='domcontentloaded'); time.sleep(0.8)
        check('purchases history marks it Expired with the exact time', 'Expired' in pg.locator('body').inner_text() and ':' in pg.locator('body').inner_text().split('Expired', 1)[1][:40])
        print('  console errors:', errs or 'none')
        b.close()
finally:
    clean()
    selftest_student.remove(db)
left = (db("SELECT COUNT(*) n FROM premium_catalog WHERE headline LIKE 'SELFTEST%'")[0]['n'] + db("SELECT COUNT(*) n FROM pcp_subscriptions WHERE razorpay_order_id LIKE 'SELFTEST%'")[0]['n']
        + db("SELECT COUNT(*) n FROM course_content WHERE section_id=%s", (SID,))[0]['n']
        + db("SELECT COUNT(*) n FROM premium_plans WHERE label LIKE 'SELFTEST%'")[0]['n'])
print(f"\nSELFTEST rows left: {left}\nRESULT: {sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) and left == 0 else 1)
