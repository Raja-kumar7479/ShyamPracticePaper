import json, os, re, sys, time
from datetime import datetime, timedelta
import mysql.connector, requests
from urllib3.util.retry import Retry
from dotenv import dotenv_values
from playwright.sync_api import sync_playwright

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
ADMIN = 'http://127.0.0.1:5001'
ADMIN_EMAIL, ADMIN_PASSWORD = 'rajakumarvijeta7087@gmail.com', 'Raja@7479'
sys.path.insert(0, f'{ROOT}/scripts/checks')
import selftest_student
v = dotenv_values(f'{ROOT}/user_app/.env')
NOBODY = 'selftest.nobody@example.com'


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


def snapshot():
    return json.dumps({
        'subs': db("SELECT id, email, course_code, plan, plan_label, amount_paise, status, expires_at FROM pcp_subscriptions "
                   "WHERE razorpay_order_id NOT LIKE 'order_SELFTEST%%' ORDER BY id"),
        'plans': db("SELECT id, code, plan_key, label, price, discount, valid_until, extra_days FROM premium_plans WHERE code <> %s ORDER BY id",
                    (selftest_student.CODE,)),
    }, default=str)


def cleanup():
    db("DELETE FROM pcp_subscriptions WHERE razorpay_order_id LIKE 'order_SELFTEST%'")
    selftest_student.remove(db)


before = snapshot()
cleanup()
student = selftest_student.setup(db)
CODE, EMAIL, UNIQUE = student['code'], student['email'], student['unique_code']
now = datetime.now()
today = now.replace(hour=0, minute=0, second=0, microsecond=0)
OLD_END = (today + timedelta(days=400)).replace(hour=23, minute=59)
NEW_END = (today + timedelta(days=500)).replace(hour=23, minute=59)
stamp = lambda d: d.strftime('%Y-%m-%dT%H:%M')

s = requests.Session()
s.mount('http://', requests.adapters.HTTPAdapter(max_retries=Retry(total=4, connect=4, read=4, backoff_factor=1.5, allowed_methods=False)))
PLAN_URL = f'{ADMIN}/api/premium-catalog/{CODE}/plans'
H = {}


def plan_body(**kw):
    body = {'label': 'SELFTEST Yearly', 'price': '2000', 'discount': '0', 'discount_ends_at': '',
            'valid_until': stamp(OLD_END), 'extra_days': '0'}
    body.update(kw)
    return body


try:
    tok = re.search(r'name="csrf-token"[^>]*content="([^"]+)"', s.get(f'{ADMIN}/admin_login').text).group(1)
    s.post(f'{ADMIN}/admin_login', data={'email': ADMIN_EMAIL, '_csrf_token': tok})
    s.post(f'{ADMIN}/admin_login', data={'password': ADMIN_PASSWORD, '_csrf_token': tok})
    H.update({'X-CSRFToken': re.search(r'name="csrf-token"[^>]*content="([^"]+)"', s.get(f'{ADMIN}/manage-premium').text).group(1),
              'Accept': 'application/json'})
    print('== a plan that students already bought ==')
    r = s.post(PLAN_URL, json=plan_body(), headers=H)
    plan = next(p for p in r.json()['plans'] if p['label'] == 'SELFTEST Yearly')
    PID, KEY = plan['id'], plan['plan_key']
    db("INSERT INTO pcp_subscriptions (email, course_code, plan, plan_label, amount_paise, list_paise, discount_pct, razorpay_order_id, "
       "razorpay_payment_id, status, starts_at, expires_at, plan_ends_at, created_at) VALUES (%s,%s,%s,'SELFTEST Yearly',200000,200000,0,"
       "'order_SELFTEST_ACTIVE','pay_SELFTEST_ACTIVE','active',%s,%s,%s,%s)", (EMAIL, CODE, KEY, now - timedelta(days=10), OLD_END, OLD_END, now - timedelta(days=10)))
    db("INSERT INTO pcp_subscriptions (email, course_code, plan, plan_label, amount_paise, list_paise, discount_pct, razorpay_order_id, "
       "status, plan_ends_at, created_at) VALUES (%s,%s,%s,'SELFTEST Yearly',200000,200000,0,'order_SELFTEST_PENDING','created',%s,%s)",
       (EMAIL, CODE, KEY, OLD_END, now - timedelta(minutes=5)))
    bought = lambda: db("SELECT amount_paise, expires_at, plan_label, plan, status FROM pcp_subscriptions WHERE razorpay_order_id='order_SELFTEST_ACTIVE'")[0]
    original = bought()

    lst = s.get(f'{ADMIN}/api/premium-catalog', headers=H).json()
    mine = next(p for c in lst['courses'] if c['code'] == CODE for p in c['plans'] if p['id'] == PID)
    check('the editor is told today\'s date by the server', lst.get('today') == now.strftime('%Y-%m-%d') and now.strftime('%d %b %Y') in lst.get('today_label', ''), lst.get('today_label'))
    check('days are counted by calendar date from today (400)', mine['days'] == 400, str(mine['days']))
    check('the length is also given in years/months/days', mine.get('span', '').startswith('1 year 1 month'), mine.get('span'))
    h = s.get(f'{PLAN_URL}/{PID}/holders', headers=H).json()
    check('the editor can see 1 buyer and 1 payment in progress', h.get('holders') == {'active': 1, 'pending': 1}, str(h))

    print('\n== changing it asks first and touches only new buyers ==')
    r = s.post(PLAN_URL, json=plan_body(id=PID, price='3000', valid_until=stamp(NEW_END)), headers=H)
    check('a change without approval is refused (409, needs approval)', r.status_code == 409 and r.json().get('needs_approval'), f'{r.status_code} {r.text[:90]}')
    check('...and nothing was saved', float(db("SELECT price FROM premium_plans WHERE id=%s", (PID,))[0]['price']) == 2000)
    r = s.post(PLAN_URL, json=plan_body(id=PID, price='3000', valid_until=stamp(NEW_END), approved_holders=1), headers=H)
    check('approval for the wrong number of buyers is refused', r.status_code == 409, str(r.status_code))
    r = s.post(PLAN_URL, json=plan_body(id=PID, price='3000', valid_until=stamp(NEW_END), approved_holders=2), headers=H)
    check('approved for the right number, it saves', r.status_code == 200 and 'keep their own amount and end date' in r.json().get('message', ''), r.text[:140])
    check('the student who bought keeps the amount paid, end date and plan name', bought() == original, str(bought()))
    r = s.post(PLAN_URL, json=plan_body(id=PID, label='SELFTEST Yearly Plus', price='3000', valid_until=stamp(NEW_END), approved_holders=2), headers=H)
    after = db("SELECT plan_key, label FROM premium_plans WHERE id=%s", (PID,))[0]
    check('renaming keeps the plan tied to its buyers (key unchanged)', r.status_code == 200 and after['plan_key'] == KEY and after['label'] == 'SELFTEST Yearly Plus', str(after))
    check('buyers still counted after the rename', s.get(f'{PLAN_URL}/{PID}/holders', headers=H).json().get('holders') == {'active': 1, 'pending': 1})
    r = s.post(PLAN_URL, json=plan_body(label='SELFTEST Yearly Plus'), headers=H)
    check('a second plan with the same name is still refused', r.status_code == 409, str(r.status_code))

    os.chdir(f'{ROOT}/user_app'); sys.path.insert(0, f'{ROOT}/user_app')
    from app import app
    from routes.exam_platform.placement_exam_portal.practice_coding import routes_billing
    starts, ends = routes_billing._period(NOBODY, CODE, KEY, OLD_END)
    check('a payment confirmed after the change still gets the end date shown at checkout', ends == OLD_END, str(ends))
    starts, ends = routes_billing._period(NOBODY, CODE, KEY)
    check('a checkout started after the change gets the new end date', ends == NEW_END, str(ends))

    print('\n== the student who already bought ==')
    created = []
    class FakeOrders:
        def create(self, body):
            created.append(body); return {'id': f'order_SELFTEST_NEW{len(created)}'}
    class FakeClient:
        order = FakeOrders()
    routes_billing._razorpay_client = lambda: FakeClient()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_email'] = EMAIL; sess['user_username'] = 'SELFTEST'; sess['_csrf_token'] = 'selftest-csrf'
    CH = {'X-CSRFToken': 'selftest-csrf'}
    buy = lambda: client.post('/api/premium/order', json={'course_code': CODE, 'plan': KEY, 'phone': '9876543210'}, headers=CH)
    page = lambda: client.get(f'/courses/{CODE}/{UNIQUE}/premium').get_data(as_text=True)

    r = buy()
    check('buying again while premium is active is refused, with the end date', r.status_code == 409 and 'after it ends' in r.get_data(as_text=True)
          and OLD_END.strftime('%d %b %Y') in r.get_data(as_text=True), r.get_data(as_text=True)[:120])
    check('no payment order was opened at the gateway', not created)
    html = page()
    check('premium page shows the member panel with the expiry date', 'You are a Premium member' in html and OLD_END.strftime('%d %b %Y') in html and 'Already purchased' in html)
    check('premium page shows no plan cards, prices or buy buttons', 'pm-subscribe' not in html and 'pm-price' not in html and '3000' not in html)
    db("UPDATE pcp_subscriptions SET expires_at=%s WHERE razorpay_order_id='order_SELFTEST_ACTIVE'", (now + timedelta(days=3),))
    r = buy(); html = page()
    check('3 days before the end it is still refused (no early re-buy)', r.status_code == 409 and not created, str(r.status_code))
    check('...and the page still shows only the member panel', 'You are a Premium member' in html and 'pm-subscribe' not in html and 'Renew' not in html)
    pr = client.get(f'/purchase/{CODE}/{UNIQUE}')
    purchases_html = pr.get_data(as_text=True)
    check('Purchases page says it expires soon, with no Renew button', pr.status_code == 200 and 'Expires in' in purchases_html
          and 'prem__btn--renew' not in purchases_html, str(pr.status_code))
    db("UPDATE pcp_subscriptions SET expires_at=%s WHERE razorpay_order_id='order_SELFTEST_ACTIVE'", (now - timedelta(minutes=1),))
    db("DELETE FROM pcp_subscriptions WHERE razorpay_order_id='order_SELFTEST_PENDING'")
    html = page()
    check('after it ends the plans and prices show again', 'pm-subscribe' in html and '3000' in html)
    r = buy()
    check('after it ends a new purchase can start', r.status_code == 200 and r.get_json().get('order_id') == 'order_SELFTEST_NEW1', r.get_data(as_text=True)[:100])
    r2 = buy()
    check('a second click or tab reuses the same open order (no double payment)', r2.status_code == 200 and r2.get_json().get('order_id') == 'order_SELFTEST_NEW1' and len(created) == 1,
          f'{r2.get_json()} / {len(created)} gateway order(s)')
    db("UPDATE pcp_subscriptions SET expires_at=%s WHERE razorpay_order_id='order_SELFTEST_ACTIVE'", (OLD_END,))
    db("INSERT INTO pcp_subscriptions (email, course_code, plan, plan_label, amount_paise, list_paise, discount_pct, razorpay_order_id, "
       "status, plan_ends_at, created_at) VALUES (%s,%s,%s,'SELFTEST Yearly',200000,200000,0,'order_SELFTEST_PENDING','created',%s,%s)",
       (EMAIL, CODE, KEY, OLD_END, now - timedelta(minutes=5)))
    db("DELETE FROM pcp_subscriptions WHERE razorpay_order_id='order_SELFTEST_NEW1'")

    print('\n== the Premium Catalog page ==')
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome', headless=True)
        ctx = b.new_context(viewport={'width': 1400, 'height': 1000}); ctx.set_default_timeout(15000)
        pg = ctx.new_page(); errs = []; natives = []
        pg.on('pageerror', lambda e: errs.append(str(e)[:160]))
        pg.on('dialog', lambda d: (natives.append(d.message), d.dismiss()))
        pg.goto(f'{ADMIN}/admin_login', wait_until='domcontentloaded')
        pg.fill('input[name="email"]', ADMIN_EMAIL); pg.keyboard.press('Enter'); time.sleep(1.2)
        pg.fill('input[name="password"]', ADMIN_PASSWORD); pg.keyboard.press('Enter'); time.sleep(1.5)
        pg.goto(f'{ADMIN}/manage-premium', wait_until='domcontentloaded'); time.sleep(1.5)
        pg.click(f'.pc-course[data-code="{CODE}"]'); time.sleep(1.0)
        dialog_open = lambda: pg.evaluate("(() => { const d = document.querySelector('.acf'); return !!d && !d.hidden; })()")
        dialog_text = lambda: pg.locator('.acf-box').inner_text() if dialog_open() else ''
        toast = lambda: pg.locator('.admin-toast').last.inner_text() if pg.locator('.admin-toast').count() else ''
        banner = pg.locator('#pcToday').inner_text()
        check('today\'s date is shown above the plans', now.strftime('%d %b %Y') in banner, banner)
        row = pg.locator(f'.pc-plan-row[data-plan-id="{PID}"]')
        check('Days shows the calendar count (500)', row.locator('[data-days]').input_value() == '500', row.locator('[data-days]').input_value())
        check('the months/years line shows under Days', '1 year 4 months' in row.locator('[data-span]').inner_text(), row.locator('[data-span]').inner_text())
        row.locator('[data-f="valid_until"]').fill(stamp(today + timedelta(days=30))); time.sleep(0.3)
        check('a date 30 days away reads exactly 30 days = 1 month', row.locator('[data-days]').input_value() == '30' and '1 month' in row.locator('[data-span]').inner_text(),
              row.locator('[data-days]').input_value() + ' / ' + row.locator('[data-span]').inner_text())
        row.locator('[data-f="valid_until"]').fill(stamp(NEW_END)); time.sleep(0.2)
        row.locator('[data-act="save"]').click(); time.sleep(0.8)
        check('saving with nothing changed says so and asks nothing', not dialog_open() and 'No changes' in toast(), toast())
        row.locator('[data-f="price"]').fill('3500')
        row.locator('[data-act="save"]').click(); time.sleep(1.0)
        text = dialog_text()
        check('Save asks for approval and says how many already bought', dialog_open() and '1 student already has this plan' in text and '1 student is paying' in text, text.replace('\n', ' | ')[:200])
        check('it says their amount and end date do not change', 'keep the amount they paid and their own end date' in text)
        check('it lists the change and what new buyers get', '3,000' in text and '3,500' in text and 'New buyers get' in text, text.replace('\n', ' | ')[:220])
        check('it shows today\'s date', now.strftime('%d %b %Y') in text)
        pg.click('.acf [data-acf="cancel"]'); time.sleep(0.4)
        check('Cancel saves nothing', float(db("SELECT price FROM premium_plans WHERE id=%s", (PID,))[0]['price']) == 3000)
        row.locator('[data-act="save"]').click(); time.sleep(1.0)
        pg.click('.acf [data-acf="confirm"]'); time.sleep(1.5)
        check('approving saves the new amount for new buyers', float(db("SELECT price FROM premium_plans WHERE id=%s", (PID,))[0]['price']) == 3500)
        check('the result message confirms existing buyers keep their terms', 'keep their own amount' in toast(), toast()[:160])
        check('the student who bought is still untouched', bought() == original, str(bought()))
        pg.click('#pcAddPlan'); time.sleep(0.3)
        new = pg.locator('.pc-plan-row[data-plan-id=""]').last
        new.locator('[data-f="label"]').fill('SELFTEST Monthly'); new.locator('[data-f="price"]').fill('500')
        new.locator('[data-f="valid_until"]').fill(stamp(today + timedelta(days=45)))
        new.locator('[data-act="save"]').click(); time.sleep(0.8)
        text = dialog_text()
        check('a new plan also asks for approval, showing days from today', 'Put the plan' in text and '45 days' in text, text.replace('\n', ' | ')[:160])
        pg.click('.acf [data-acf="confirm"]'); time.sleep(1.5)
        check('...and saves', bool(db("SELECT 1 FROM premium_plans WHERE code=%s AND label='SELFTEST Monthly'", (CODE,))))
        row = pg.locator(f'.pc-plan-row[data-plan-id="{PID}"]')
        row.locator('[data-act="delete"]').click(); time.sleep(1.0)
        text = dialog_text()
        check('Delete asks first and says buyers keep their access', '2 students' in text and 'keep their access' in text, text.replace('\n', ' | ')[:160])
        pg.click('.acf [data-acf="confirm"]'); time.sleep(1.5)
        check('the plan is removed', not db("SELECT 1 FROM premium_plans WHERE id=%s", (PID,)))
        check('the student who bought keeps premium after the plan is removed', bought() == original)
        check('no native browser pop-ups', not natives, str(natives)[:80])
        check('no script errors', not errs, '; '.join(errs)[:160])
        b.close()
finally:
    cleanup()
    left = db("SELECT COUNT(*) n FROM pcp_subscriptions WHERE razorpay_order_id LIKE 'order_SELFTEST%'")[0]['n'] \
        + db("SELECT COUNT(*) n FROM premium_plans WHERE code=%s", (selftest_student.CODE,))[0]['n']
    check('SELFTEST rows removed', left == 0, f'{left} left')
    check('your own plans and subscriptions are untouched', snapshot() == before)

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
