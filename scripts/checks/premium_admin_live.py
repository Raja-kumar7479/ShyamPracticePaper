import re, sys, time
from datetime import datetime, timedelta
import mysql.connector
from dotenv import dotenv_values
from playwright.sync_api import sync_playwright

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
ADMIN, USER = 'http://127.0.0.1:5001', 'http://127.0.0.1:5002'
ADMIN_EMAIL, ADMIN_PASSWORD = 'rajakumarvijeta7087@gmail.com', 'Raja@7479'
sys.path.insert(0, f'{ROOT}/scripts/checks')
import selftest_student
EMAIL, PASSWORD = selftest_student.EMAIL, selftest_student.PASSWORD
SHOT = sys.argv[1] if len(sys.argv) > 1 else ''
v = dotenv_values(f'{ROOT}/user_app/.env')

def db(q, p=()):
    c = mysql.connector.connect(host=v['DATABASE_HOST'], user=v['DATABASE_USER'], password=v['DATABASE_PASSWORD'], database=v['DATABASE_NAME'], autocommit=True)
    cur = c.cursor(dictionary=True); cur.execute(q, p); out = cur.fetchall() if cur.with_rows else []; cur.close(); c.close(); return out
results = []
def check(name, ok, detail=''):
    results.append(bool(ok)); print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ''))

student = selftest_student.setup(db)
CODE, U = student['code'], student['unique_code']
db("DELETE FROM premium_plans WHERE label LIKE 'SELFTEST%'")
when = lambda d: (datetime.now() + timedelta(days=d)).strftime('%Y-%m-%dT%H:%M')

def login(pg):
    pg.goto(f'{ADMIN}/admin_login', wait_until='domcontentloaded')
    pg.fill('input[name="email"]', ADMIN_EMAIL); pg.keyboard.press('Enter'); time.sleep(1.2)
    pg.fill('input[name="password"]', ADMIN_PASSWORD); pg.keyboard.press('Enter'); time.sleep(1.5)

try:
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome', headless=True); ctx = b.new_context(viewport={'width': 1400, 'height': 1000}); ctx.set_default_timeout(15000)
        pg = ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)[:120]))
        def approve():
            time.sleep(0.6)
            if pg.evaluate("(() => { const d = document.querySelector('.acf'); return !!d && !d.hidden; })()"):
                pg.click('.acf [data-acf="confirm"]')
        login(pg)
        pg.goto(f'{ADMIN}/manage-premium', wait_until='domcontentloaded'); time.sleep(1.5)
        pg.click(f'.pc-course[data-code="{CODE}"]'); time.sleep(1.0)
        pg.click('#pcAddPlan'); time.sleep(0.4)
        row = pg.locator('.pc-plan-row[data-plan-id=""]').last
        toast = lambda: pg.locator('.admin-toast').last.inner_text() if pg.locator('.admin-toast').count() else ''
        print('\n== the plan editor ==')
        check('no Days input, no Order field, no On-sale switch',
              row.locator('[data-f="duration_days"], [data-f="position"], [data-f="status"], input[type="checkbox"]').count() == 0)
        check('Days is read-only and starts empty', row.locator('[data-days]').get_attribute('readonly') is not None and row.locator('[data-days]').input_value() == '-')
        row.locator('[data-f="label"]').fill('SELFTEST Monthly'); row.locator('[data-f="price"]').fill('1500')
        row.locator('[data-f="valid_until"]').fill(when(40)); time.sleep(0.3)
        check('Days fills itself from the date (40 days)', row.locator('[data-days]').input_value() in ('39', '40'), row.locator('[data-days]').input_value())
        row.locator('[data-f="extra_days"]').fill('10'); time.sleep(0.3)
        check('extra days update Days automatically (50)', row.locator('[data-days]').input_value() in ('49', '50'), row.locator('[data-days]').input_value())

        print('\n== the rules on a live save ==')
        row.locator('[data-f="valid_until"]').fill(when(20)); row.locator('[data-f="extra_days"]').fill('0'); time.sleep(0.2)
        row.locator('[data-act="save"]').click(); approve(); time.sleep(1.2)
        msg = toast()
        check('"Monthly" 20 days away is refused with the 30-day rule', '30 days' in msg and not db("SELECT 1 FROM premium_plans WHERE label='SELFTEST Monthly'"), msg[:90])
        row.locator('[data-f="valid_until"]').fill(when(45)); time.sleep(0.2); row.locator('[data-act="save"]').click(); approve(); time.sleep(1.5)
        saved = db("SELECT id, valid_until, extra_days FROM premium_plans WHERE label='SELFTEST Monthly'")
        check('"Monthly" 45 days away saves (more is allowed)', bool(saved), str(saved)[:80])
        row = pg.locator(f'.pc-plan-row[data-plan-id="{saved[0]["id"]}"]') if saved else row
        note = row.locator('[data-note]').inner_text()
        check('the row note shows the computed days and end date', 'from today' in note and ' days' in note and 'access until' in note, note[:100])
        check('Days after save comes from the server', row.locator('[data-days]').input_value() in ('44', '45'), row.locator('[data-days]').input_value())
        row.locator('[data-f="label"]').fill('SELFTEST Yearly'); row.locator('[data-act="save"]').click(); approve(); time.sleep(1.2)
        msg = toast()
        check('renaming it "Yearly" with only 45 days is refused with the 365-day rule', '365 days' in msg and db("SELECT label FROM premium_plans WHERE id=%s", (saved[0]['id'],))[0]['label'] == 'SELFTEST Monthly', msg[:90])

        print('\n== page text needs a plan; removing a plan ==')
        pg.goto(f'{ADMIN}/manage-premium', wait_until='domcontentloaded'); time.sleep(1.5)
        bare = pg.locator('.pc-course').filter(has_text='No plan set').first
        if bare.count():
            bare.click(); time.sleep(0.8)
            check('a course with no plan has its page text locked', pg.locator('#pcHeadline').is_disabled() and pg.locator('#pcCopyLocked').is_visible())
        pg.click(f'.pc-course[data-code="{CODE}"]'); time.sleep(1.0)
        check('a course with a plan has its page text open', not pg.locator('#pcHeadline').is_disabled() and not pg.locator('#pcCopyLocked').is_visible())
        row = pg.locator(f'.pc-plan-row[data-plan-id="{saved[0]["id"]}"]')
        others = db("SELECT id, label, price, discount, valid_until FROM premium_plans WHERE code=%s AND label NOT LIKE 'SELFTEST%%'", (CODE,))
        check('no Hide button on plans - hide belongs to course content', pg.locator('[data-act="hide"]').count() == 0)
        if SHOT: pg.screenshot(path=SHOT, full_page=True)
        row.locator('[data-act="delete"]').click(); approve(); time.sleep(1.2)
        check('Delete removes the plan', not db("SELECT 1 FROM premium_plans WHERE label='SELFTEST Monthly'") and toast().startswith('Plan "SELFTEST Monthly" removed'), toast()[:80])
        check('the admin\'s own plans on this course were not touched', db("SELECT id, label, price, discount, valid_until FROM premium_plans WHERE code=%s AND label NOT LIKE 'SELFTEST%%'", (CODE,)) == others)
        if not others:
            check('with nothing left the page text locks again', pg.locator('#pcHeadline').is_disabled() and pg.locator('#pcCopyLocked').is_visible())
        pg.click('#pcAddPlan'); time.sleep(0.3); row = pg.locator('.pc-plan-row[data-plan-id=""]').last
        row.locator('[data-f="label"]').fill('SELFTEST Monthly'); row.locator('[data-f="price"]').fill('1500'); row.locator('[data-f="valid_until"]').fill(when(45))
        row.locator('[data-act="save"]').click(); approve(); time.sleep(1.2)
        visible_others = db("SELECT 1 FROM premium_plans WHERE code=%s AND label NOT LIKE 'SELFTEST%%' AND valid_until > NOW()", (CODE,))

        print('\n== the premium link button follows the label ==')
        pg.goto(f'{ADMIN}/manage_course_content', wait_until='domcontentloaded'); time.sleep(1.5)
        pg.select_option('#addCourseCode', CODE); time.sleep(1.0)
        crown = pg.locator('#ccEditorToolbar .ql-cc-premium')
        check('add form: the crown button is live while the label is Free', crown.is_visible() and not crown.is_disabled())
        pg.select_option('#label', 'Paid'); time.sleep(0.4)
        check('add form: it switches off for Paid, with the reason on it',
              crown.is_disabled() and 'Free' in (crown.get_attribute('title') or ''), crown.get_attribute('title'))
        pg.select_option('#label', 'Free'); time.sleep(0.4)
        check('add form: back on when the label returns to Free', not crown.is_disabled())

        print('\n== student side ==')
        pg.goto(f'{USER}/user_login', wait_until='domcontentloaded'); time.sleep(0.8)
        pg.fill('input[name="email"]', EMAIL); pg.keyboard.press('Enter'); time.sleep(1.2)
        pg.fill('input[name="password"]', PASSWORD); pg.keyboard.press('Enter'); time.sleep(1.5)
        pg.goto(f'{USER}/courses/{CODE}/{U}/premium', wait_until='domcontentloaded'); time.sleep(1.5)
        body = pg.locator('body').inner_text()
        check('the student sees the plan with its end date and days left', 'SELFTEST Monthly' in body and 'access until' in body.lower() and 'days left' in body.lower())
        db("DELETE FROM premium_plans WHERE label='SELFTEST Monthly'")
        pg.reload(wait_until='domcontentloaded'); time.sleep(1.5); body = pg.locator('body').inner_text()
        check('no plan = only "coming soon", no default Monthly/Yearly, no What you get', visible_others or ('coming soon' in body.lower() and pg.locator('.pm-plan').count() == 0 and 'Yearly' not in body and 'What you get' not in body))
        check('console errors: none', not errs, '; '.join(errs)[:200])
        b.close()
finally:
    db("DELETE FROM premium_plans WHERE label LIKE 'SELFTEST%'")
    selftest_student.remove(db)
    db("DELETE FROM pcp_subscriptions WHERE plan LIKE 'selftest%' AND status='created'")
print(f"\nRESULT: {sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
