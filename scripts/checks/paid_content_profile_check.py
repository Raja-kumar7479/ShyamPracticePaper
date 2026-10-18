import re, sys, time
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
SID_FREE, SID_PAID = 'SELFTESTPCFREE', 'SELFTESTPCPAID'
SHOT = sys.argv[1] if len(sys.argv) > 1 else ''
v = dotenv_values(f'{ROOT}/user_app/.env')

def db(q, p=()):
    c = mysql.connector.connect(host=v['DATABASE_HOST'], user=v['DATABASE_USER'], password=v['DATABASE_PASSWORD'], database=v['DATABASE_NAME'], autocommit=True)
    cur = c.cursor(dictionary=True); cur.execute(q, p); out = cur.fetchall() if cur.with_rows else []; cur.close(); c.close(); return out
results = []
def check(name, ok, detail=''):
    results.append(bool(ok)); print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ''))

def clean():
    db("DELETE FROM purchase WHERE payment_id LIKE 'SELFTEST%'")
    db("DELETE FROM pcp_subscriptions WHERE razorpay_order_id LIKE 'SELFTEST%'")
    db("DELETE FROM notes_content WHERE title LIKE 'SELFTEST%'")
    db("DELETE FROM test_description WHERE subject_title LIKE 'SELFTEST%'")
    db("DELETE FROM course_content WHERE section_id IN (%s,%s)", (SID_FREE, SID_PAID))
    db("DELETE FROM premium_plans WHERE label LIKE 'SELFTEST%'")

clean()
student = selftest_student.setup(db)
CODE, U = student['code'], student['unique_code']
enr = {CODE: {'name': student['name'], 'unique_code': U}}
own_plans = db("SELECT id, label FROM premium_plans WHERE code=%s", (CODE,))
db("INSERT INTO course_content (code,name,stream,section,section_id,title,subtitle,label,price,discount,details,status)"
   " VALUES (%s,%s,'Self test','mock_test',%s,'SELFTEST free block','open to all','Free',0,0,'<p>free</p>','active')", (CODE, enr[CODE]['name'], SID_FREE))
db("INSERT INTO course_content (code,name,stream,section,section_id,title,subtitle,label,price,discount,details,status)"
   " VALUES (%s,%s,'Self test','mock_test',%s,'SELFTEST paid block','buy to open','Paid',500,20,'<p>paid</p>','active')", (CODE, enr[CODE]['name'], SID_PAID))

csrf = lambda h: (re.search(r'name="csrf-token"[^>]*content="([^"]+)"', h) or [None, ''])[1]
a = requests.Session(); t = csrf(a.get(ADMIN + '/admin_login').text)
a.post(ADMIN + '/admin_login', data={'email': ADMIN_EMAIL, '_csrf_token': t}); a.post(ADMIN + '/admin_login', data={'password': ADMIN_PASSWORD, '_csrf_token': t})
H = {'X-CSRFToken': csrf(a.get(ADMIN + '/manage-premium').text) or t}
when = lambda d: (datetime.now() + timedelta(days=d)).strftime('%Y-%m-%dT%H:%M')

try:
    print('\n== admin: premium on content needs a premium plan first ==')
    desc = lambda key, access: a.post(ADMIN + '/api/test-descriptions/add', json={
        'test_id': SID_FREE, 'test_key': key, 'subject_title': 'SELFTEST guard test', 'total_questions': 1,
        'total_marks': 1, 'total_duration_minutes': 5, 'access_label': access}, headers=H)
    r = desc('prem_' + 'b' * 20, 'paid')
    check('a Premium test description is refused while the course has no plan', r.status_code == 400 and 'Premium Catalog' in r.text, r.text[:90])
    r = desc('free_' + 'b' * 20, 'free')
    check('a Free test description is still fine', r.status_code in (200, 201), r.text[:90])
    note = lambda access: a.post(ADMIN + '/notes_upload', data={'test_id': SID_FREE, 'code': CODE, 'type': 'notes', 'heading_input': 'SELFTEST h',
                                                                'sub_heading_input': 'SELFTEST s', 'title': 'SELFTEST note', 'sub_title': 'x',
                                                                'file_url': 'https://example.com/selftest.pdf', 'access_label': access, '_csrf_token': H['X-CSRFToken']}, headers=H)
    r = note('paid')
    check('a Premium note is refused too', r.status_code == 400 and 'Premium Catalog' in r.text, r.text[:90])
    r = a.post(ADMIN + f'/api/premium-catalog/{CODE}/plans', json={'label': 'SELFTEST Monthly', 'price': '999', 'discount': '0', 'discount_ends_at': '',
                                                                    'valid_until': when(40), 'extra_days': '0'}, headers=H)
    check('admin sets a plan for the course', r.status_code == 200, r.text[:80])
    r = desc('prem_' + 'c' * 20, 'paid')
    check('now a Premium test description is accepted', r.status_code in (200, 201), r.text[:90])
    r = note('paid')
    check('and a Premium note is accepted', r.status_code in (200, 201), r.text[:90])

    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome', headless=True); ctx = b.new_context(viewport={'width': 1400, 'height': 1000}); ctx.set_default_timeout(15000)
        pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)[:120]))
        pg.goto(f'{USER}/user_login', wait_until='domcontentloaded'); time.sleep(0.8)
        pg.fill('#email', EMAIL); pg.locator('#email').press('Enter'); pg.wait_for_load_state('domcontentloaded'); time.sleep(1.2)
        pg.fill('#password', PASSWORD); pg.locator('#password').press('Enter'); pg.wait_for_load_state('domcontentloaded'); time.sleep(1.5)
        dash = lambda: (pg.goto(f'{USER}/courses/{CODE}/{U}', wait_until='domcontentloaded'), time.sleep(1.2))

        print('\n== dashboard: free above, paid below, different card ==')
        dash()
        paid = pg.locator('.resource-card--paid').filter(has_text='SELFTEST paid block')
        free = pg.locator('.resource-card:not(.resource-card--paid)').filter(has_text='SELFTEST free block')
        check('the paid item is on the dashboard now', paid.count() == 1)
        check('the free item is still there', free.count() == 1)
        check('free sits above paid', free.first.bounding_box()['y'] < paid.first.bounding_box()['y'])
        check('the paid card says Paid, shows the price after discount, and offers View & Buy',
              'Paid' in paid.inner_text() and '400' in paid.inner_text() and '500' in paid.inner_text() and '20% off' in paid.inner_text() and 'View & Buy' in paid.inner_text(), paid.inner_text().replace('\n', ' | ')[:120])
        check('the paid card looks different from the free card',
              pg.evaluate("[getComputedStyle(document.querySelector('.resource-card--paid')).borderColor, getComputedStyle(document.querySelector('.resource-card:not(.resource-card--paid)')).borderColor]")[0]
              != pg.evaluate("[getComputedStyle(document.querySelector('.resource-card--paid')).borderColor, getComputedStyle(document.querySelector('.resource-card:not(.resource-card--paid)')).borderColor]")[1])
        check('the paid section heading counts it', 'Paid content' in pg.locator('#view-paid').inner_text())
        if SHOT: pg.screenshot(path=SHOT.replace('.png', '_dash_before.png'), full_page=True)

        print('\n== after buying: Active on the dashboard, Paid on the purchases side ==')
        db("INSERT INTO purchase (email, username, phone, course_code, section_id, section, title, subtitle, price, original_price, discount_percent, final_price, payment_id, payment_mode, payment_date, status, purchase_code)"
           " VALUES (%s,'selftest','9876543210',%s,%s,'mock_test','SELFTEST paid block','buy to open',500,500,20,400,'SELFTEST_PAY_PC','razorpay',NOW(),'Paid','SELFTEST-PC')", (EMAIL, CODE, SID_PAID))
        db("INSERT INTO pcp_subscriptions (email,course_code,plan,plan_label,amount_paise,list_paise,discount_pct,razorpay_order_id,razorpay_payment_id,status,starts_at,expires_at)"
           " VALUES (%s,%s,'selftest-monthly','SELFTEST Monthly',99900,99900,0,'SELFTEST_ORDER_PC','SELFTEST_PAY_PC2','active',NOW(),%s)", (EMAIL, CODE, datetime.now() + timedelta(days=30)))
        dash()
        paid = pg.locator('.resource-card--paid').filter(has_text='SELFTEST paid block')
        check('the bought card now says Active and Open Resource, no price',
              'Active' in paid.inner_text() and 'Open Resource' in paid.inner_text() and 'View & Buy' not in paid.inner_text() and '400' not in paid.inner_text(), paid.inner_text().replace('\n', ' | ')[:120])
        check('it is styled as owned', 'is-owned' in (paid.first.get_attribute('class') or ''))
        paid.first.locator('a.card-action').click(); pg.wait_for_load_state('domcontentloaded'); time.sleep(0.8)
        check('Open leads to the item page and it is open', pg.url.endswith(f'/resource/{SID_PAID}') and 'SELFTEST paid block' in pg.locator('body').inner_text())
        if SHOT: dash(); pg.screenshot(path=SHOT.replace('.png', '_dash_after.png'), full_page=True)

        print('\n== profile: purchases tab lists the item and the premium subscription ==')
        pg.goto(f'{USER}/profile', wait_until='domcontentloaded'); time.sleep(1.0)
        pg.evaluate("switchTab('purchases')"); time.sleep(0.5)
        tab = pg.locator('#purchases')
        txt = tab.inner_text().lower().replace(',', '')
        item = tab.locator('.purchase-card').filter(has_text='SELFTEST paid block'); sub = tab.locator('.purchase-card--premium').filter(has_text='SELFTEST Monthly')
        check('the bought item is listed with its price and status Paid', item.count() == 1 and '400.00' in item.inner_text() and 'paid' in item.inner_text().lower(), item.inner_text().replace('\n', ' | ')[:120] if item.count() else 'missing')
        check('the premium subscription is listed as Active with its end date',
              sub.count() == 1 and 'active' in sub.inner_text().lower() and 'valid till' in sub.inner_text().lower() and '999.00' in sub.inner_text(), sub.inner_text().replace('\n', ' | ')[:120] if sub.count() else 'missing')
        n = int((re.search(r'total purchases\s*(\d+)', txt) or [0, 0])[1]); spent = float((re.search(r'total spent\s*₹?\s*([\d.]+)', txt) or [0, 0])[1])
        check('totals count the item and the subscription together', n >= 2 and spent >= 1399.0, f'purchases={n} spent={spent}')
        check('nothing on the tab is blank', 'Nothing bought yet' not in txt)
        if SHOT: pg.screenshot(path=SHOT.replace('.png', '_profile.png'), full_page=True)

        print('\n== profile: My Courses buttons are the same size and aligned ==')
        pg.evaluate("switchTab('courses')"); time.sleep(0.5)
        boxes = [pg.locator('#courses .dc-action').nth(i).bounding_box() for i in range(pg.locator('#courses .dc-action').count())]
        check('every Continue Learning button has the same height and width',
              len(boxes) >= 1 and len({round(bx['height']) for bx in boxes}) == 1 and len({round(bx['width']) for bx in boxes}) == 1, str([(round(bx['width']), round(bx['height'])) for bx in boxes]))
        cards = [pg.locator('#courses .dashboard-course-card').nth(i).bounding_box() for i in range(pg.locator('#courses .dashboard-course-card').count())]
        check('the course cards in one row share a height', len({round(c['height']) for c in cards if round(c['y']) == round(cards[0]['y'])}) == 1 if cards else False)

        print('\n== when the subscription and purchase are gone the dashboard goes back ==')
        db("DELETE FROM purchase WHERE payment_id LIKE 'SELFTEST%'"); db("DELETE FROM pcp_subscriptions WHERE razorpay_order_id LIKE 'SELFTEST%'")
        dash(); paid = pg.locator('.resource-card--paid').filter(has_text='SELFTEST paid block')
        check('the card is back to Paid / View & Buy', 'View & Buy' in paid.inner_text() and 'Active' not in paid.inner_text())
        db("UPDATE course_content SET status='inactive' WHERE section_id=%s", (SID_PAID,))
        dash()
        check('a hidden paid item disappears for someone who never bought it', pg.locator('.resource-card--paid').filter(has_text='SELFTEST paid block').count() == 0)
        check('console errors: none', not errs, '; '.join(errs)[:160])
        b.close()
finally:
    clean()
    selftest_student.remove(db)
    check('the admin\'s own plans on this course were not touched', db("SELECT id, label FROM premium_plans WHERE code=%s", (CODE,)) == own_plans)
left = db("SELECT COUNT(*) n FROM course_content WHERE section_id IN (%s,%s)", (SID_FREE, SID_PAID))[0]['n'] + db("SELECT COUNT(*) n FROM purchase WHERE payment_id LIKE 'SELFTEST%'")[0]['n']
print(f"\nSELFTEST rows left: {left}\nRESULT: {sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) and left == 0 else 1)
