import json, re, sys, time
from pathlib import Path
import mysql.connector, requests
from dotenv import dotenv_values
from playwright.sync_api import sync_playwright

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
ADMIN = 'http://127.0.0.1:5001'
ADMIN_EMAIL, ADMIN_PASSWORD = 'rajakumarvijeta7087@gmail.com', 'Raja@7479'
sys.path.insert(0, f'{ROOT}/scripts/checks')
import selftest_student
SHOT = sys.argv[1] if len(sys.argv) > 1 else ''
v = dotenv_values(f'{ROOT}/user_app/.env')

GROUP = selftest_student.NAME
USED = selftest_student.CODE
FREE, SPARE = 'SLFTB', 'SLFTC'
EMPTY_GROUP = 'SELFTEST EMPTY'


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


def cleanup():
    for code in (FREE, SPARE):
        db("DELETE FROM premium_plans WHERE code=%s", (code,))
        db("DELETE FROM premium_catalog WHERE code=%s", (code,))
        db("DELETE FROM courses WHERE code=%s", (code,))
        db("DELETE FROM course_group_codes WHERE code=%s", (code,))
    selftest_student.remove(db)
    db("DELETE FROM course_groups WHERE group_name=%s", (EMPTY_GROUP,))


def snapshot():
    return json.dumps({
        'courses': db("SELECT code, name, subgroup, description FROM courses WHERE code NOT LIKE 'SLFT%' ORDER BY code"),
        'groups': db("SELECT group_name, label FROM course_groups WHERE group_name NOT LIKE 'SELFTEST%' ORDER BY group_name"),
        'codes': db("SELECT group_name, code FROM course_group_codes WHERE code NOT LIKE 'SLFT%' ORDER BY code"),
        'plans': db("SELECT id, code, label FROM premium_plans WHERE code NOT LIKE 'SLFT%' ORDER BY id"),
        'catalog': db("SELECT id, code FROM premium_catalog WHERE code NOT LIKE 'SLFT%' ORDER BY id"),
    }, default=str)


print('== static guard ==')
gates = []
for f in Path(f'{ROOT}/admin_app/static/js/admin').rglob('*.js'):
    text = f.read_text(encoding='utf-8', errors='ignore')
    if re.search(r"adminRole|admin_role|===\s*['\"]owner['\"]|==\s*['\"]owner['\"]", text):
        gates.append(f.name)
check('no admin script decides button access by the owner role (the server rule is owner OR admin)', not gates, ', '.join(gates))
base = Path(f'{ROOT}/admin_app/templates/admin/manage_course/base.html').read_text()
check('course page takes its permission from the server can_manage flag', 'data-can-manage="{{ 1 if can_manage else 0 }}"' in base)

before = snapshot()
cleanup()
selftest_student.setup(db)
db("INSERT INTO course_group_codes (group_name, code, label, position) VALUES (%s,%s,'SELFTEST FREE',99)", (GROUP, FREE))
db("INSERT INTO courses (code, name, subgroup, description, guest_access_code) VALUES (%s,%s,'SELFTEST','<p>SELFTEST free course</p>','selftest00000003')",
   (FREE, GROUP))
db("INSERT INTO premium_plans (code, plan_key, label, price, discount, valid_until, extra_days) "
   "VALUES (%s,'selftest','SELFTEST plan',100,0,DATE_ADD(NOW(), INTERVAL 60 DAY),0)", (FREE,))
db("INSERT INTO premium_catalog (code, headline, details) VALUES (%s,'SELFTEST headline','SELFTEST details')", (FREE,))
db("INSERT INTO course_groups (group_name, label, position, is_active) VALUES (%s,%s,99,1)", (EMPTY_GROUP, EMPTY_GROUP))


def login(pg):
    pg.goto(f'{ADMIN}/admin_login', wait_until='domcontentloaded')
    pg.fill('input[name="email"]', ADMIN_EMAIL); pg.keyboard.press('Enter'); time.sleep(1.2)
    pg.fill('input[name="password"]', ADMIN_PASSWORD); pg.keyboard.press('Enter'); time.sleep(1.5)


try:
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome', headless=True)
        ctx = b.new_context(viewport={'width': 1400, 'height': 1000}); ctx.set_default_timeout(15000)
        pg = ctx.new_page(); errs = []; natives = []
        pg.on('pageerror', lambda e: errs.append(str(e)[:160]))
        pg.on('dialog', lambda d: (natives.append(d.message), d.dismiss()))
        login(pg)
        role = db("SELECT role FROM auth_admin WHERE email=%s", (ADMIN_EMAIL,))
        print(f"signed in as {ADMIN_EMAIL} (role: {role[0]['role'] if role else '?'})")

        def open_list():
            pg.goto(f'{ADMIN}/courses#panel-list', wait_until='domcontentloaded'); pg.reload(wait_until='domcontentloaded'); time.sleep(1.2)

        def dialog_open():
            return pg.evaluate("(() => { const d = document.querySelector('.acf'); return !!d && !d.hidden; })()")

        def dialog_text():
            return pg.locator('.acf-box').inner_text() if dialog_open() else ''

        def last_toast():
            return pg.locator('.admin-toast').last.inner_text() if pg.locator('.admin-toast').count() else ''

        def row(code):
            return pg.locator(f'#courses-tbody tr[data-code="{code}"]')

        print('\n== the page ==')
        open_list()
        check('page reports can-manage for this account', pg.evaluate("document.body.dataset.canManage") == '1')
        check('every course row shows Edit and Delete',
              pg.locator('#courses-tbody tr').count() == pg.locator('#courses-tbody tr .mc-btn-edit').count() == pg.locator('#courses-tbody tr .mc-btn-danger').count() > 0)
        check('descriptions show as text, not raw <p> tags', '<p>' not in row(FREE).locator('td[data-field="description"]').inner_text(),
              row(FREE).locator('td[data-field="description"]').inner_text())

        print('\n== add a code and a course ==')
        pg.evaluate("document.querySelector('.as-view[data-panel=\"panel-groups\"]').click()"); time.sleep(0.5)
        pg.select_option('#code-group', GROUP); pg.fill('#code-value', SPARE)
        pg.click('#code-form [type="submit"]'); time.sleep(2.0)
        check('adding a code saves it', bool(db("SELECT 1 FROM course_group_codes WHERE code=%s", (SPARE,))))
        check('its success message survives the page refresh', f'Code "{SPARE}" added' in last_toast(), last_toast())
        pg.evaluate("document.querySelector('.as-view[data-panel=\"panel-add\"]').click()"); time.sleep(0.5)
        pg.select_option('#add-name', GROUP); time.sleep(0.2)
        pg.select_option('#add-code', SPARE)
        pg.locator('#addDescEditor .ql-editor').click(); pg.keyboard.type('SELFTEST added course')
        pg.click('#add-submit'); time.sleep(0.5)
        text = dialog_text()
        check('Add course asks for approval first, listing group and code', 'Add the course' in text and GROUP in text and SPARE in text, text.replace('\n', ' | ')[:120])
        pg.click('.acf [data-acf="cancel"]'); time.sleep(0.4)
        check('Cancel adds nothing', not db("SELECT 1 FROM courses WHERE code=%s", (SPARE,)))
        pg.click('#add-submit'); time.sleep(0.4)
        pg.click('.acf [data-acf="confirm"]'); time.sleep(1.2)
        check('approving adds the course', bool(db("SELECT 1 FROM courses WHERE code=%s", (SPARE,))))
        check('a success message shows after the add', f"'{SPARE}' added" in last_toast(), last_toast())
        check('the new row appears with Edit and Delete', row(SPARE).locator('.mc-btn-edit').count() == 1 and row(SPARE).locator('.mc-btn-danger').count() == 1)
        open_list()

        print('\n== edit a course ==')
        row(USED).locator('.mc-btn-edit').click(); time.sleep(0.5)
        check('Edit opens the edit window', pg.evaluate("document.getElementById('editModal').classList.contains('open')"))
        check('group is shown and locked (a code belongs to one group)',
              pg.locator('#editName').is_disabled() and pg.locator('#editName').input_value() == GROUP, pg.locator('#editName').input_value())
        pg.click('#editSave'); time.sleep(0.6)
        check('saving with nothing changed says so and asks nothing', not dialog_open() and 'No changes' in last_toast(), last_toast())
        pg.fill('#editSubgroup', 'SELFTEST edited'); pg.click('#editSave'); time.sleep(0.5)
        text = dialog_text()
        check('Save asks for approval first, listing the change', dialog_open() and 'Subgroup' in text and 'SELFTEST edited' in text, text.replace('\n', ' | ')[:120])
        pg.click('.acf [data-acf="cancel"]'); time.sleep(0.5)
        check('Cancel changes nothing in the database',
              db("SELECT subgroup FROM courses WHERE code=%s", (USED,))[0]['subgroup'] == 'SELFTEST')
        check('Cancel keeps the edit window open with the typed value',
              pg.evaluate("document.getElementById('editModal').classList.contains('open')") and pg.locator('#editSubgroup').input_value() == 'SELFTEST edited')
        pg.click('#editSave'); time.sleep(0.4)
        pg.keyboard.press('Escape'); time.sleep(0.4)
        check('Escape on the approval box cancels only the box',
              not dialog_open() and pg.evaluate("document.getElementById('editModal').classList.contains('open')")
              and db("SELECT subgroup FROM courses WHERE code=%s", (USED,))[0]['subgroup'] == 'SELFTEST')
        pg.click('#editSave'); time.sleep(0.4)
        pg.click('.acf [data-acf="confirm"]'); time.sleep(1.2)
        saved = db("SELECT subgroup FROM courses WHERE code=%s", (USED,))[0]['subgroup']
        check('approving saves the change', saved == 'SELFTEST edited', saved)
        check('a success message shows after the save', f"'{USED}' updated" in last_toast(), last_toast())
        check('the row updates and the edit window closes',
              'SELFTEST edited' in row(USED).locator('td[data-field="subgroup"]').inner_text()
              and not pg.evaluate("document.getElementById('editModal').classList.contains('open')"))
        row(USED).locator('.mc-btn-edit').click(); time.sleep(0.5)
        pg.locator('#editDescEditor .ql-editor').click(); pg.keyboard.press('End'); pg.keyboard.type(' plus notes'); time.sleep(0.2)
        pg.click('#editSave'); time.sleep(0.4)
        text = dialog_text()
        check('a description edit is listed in the approval box', 'Description' in text and 'plus notes' in text, text.replace('\n', ' | ')[:120])
        pg.click('.acf [data-acf="confirm"]'); time.sleep(1.2)
        desc = db("SELECT description FROM courses WHERE code=%s", (USED,))[0]['description']
        check('the new description is stored', 'plus notes' in desc, desc[:80])

        print('\n== delete a course ==')
        row(USED).locator('.mc-btn-danger').click(); time.sleep(0.8)
        text = dialog_text()
        check('a course with an enrolled student explains why it cannot be deleted',
              dialog_open() and "can't be deleted" in text and '1 enrolled student' in text, text.replace('\n', ' | ')[:140])
        check('that box offers no delete button', not pg.locator('.acf [data-acf="confirm"]').is_visible())
        pg.click('.acf [data-acf="cancel"]'); time.sleep(0.3)
        check('the course is still there', bool(db("SELECT 1 FROM courses WHERE code=%s", (USED,))))
        row(FREE).locator('.mc-btn-danger').click(); time.sleep(0.8)
        text = dialog_text()
        check('an unused course asks for approval and lists its premium setup going with it',
              'Delete the course' in text and '1 premium plan' in text and 'Premium page text' in text, text.replace('\n', ' | ')[:160])
        pg.click('.acf [data-acf="cancel"]'); time.sleep(0.4)
        check('Cancel deletes nothing', bool(db("SELECT 1 FROM courses WHERE code=%s", (FREE,))) and row(FREE).count() == 1)
        row(FREE).locator('.mc-btn-danger').click(); time.sleep(0.8)
        pg.click('.acf [data-acf="confirm"]'); time.sleep(1.3)
        check('approving deletes the course', not db("SELECT 1 FROM courses WHERE code=%s", (FREE,)))
        check('its premium plans and page text go with it (nothing orphaned)',
              not db("SELECT 1 FROM premium_plans WHERE code=%s", (FREE,)) and not db("SELECT 1 FROM premium_catalog WHERE code=%s", (FREE,)))
        check('a success message shows after the delete', f"'{FREE}' deleted" in last_toast() and 'premium plan' in last_toast(), last_toast())
        check('the row leaves the table', row(FREE).count() == 0)
        check('the code count updates without a reload',
              pg.locator(f'#codes-table tr[data-code="{FREE}"] .mc-del-code').get_attribute('data-used') == '0')

        print('\n== delete codes and groups ==')
        pg.evaluate("document.querySelector('.as-view[data-panel=\"panel-groups\"]').click()"); time.sleep(0.6)
        pg.locator(f'#codes-table tr[data-code="{FREE}"] .mc-del-code').click(); time.sleep(0.5)
        text = dialog_text()
        check('code delete asks for approval', 'Delete the code' in text and FREE in text, text.replace('\n', ' | ')[:100])
        pg.click('.acf [data-acf="confirm"]'); time.sleep(2.0)
        check('approving deletes the code', not db("SELECT 1 FROM course_group_codes WHERE code=%s", (FREE,)))
        check('the success message survives the page refresh', f'Deleted the code "{FREE}"' in last_toast(), last_toast())
        pg.locator(f'#groups-table tr[data-group="{GROUP}"] .mc-del-group').click(); time.sleep(0.5)
        text = dialog_text()
        check('a group with courses and codes explains why it cannot be deleted',
              "can't be deleted" in text and 'course(s)' in text and 'code(s)' in text, text.replace('\n', ' | ')[:140])
        pg.click('.acf [data-acf="cancel"]'); time.sleep(0.3)
        pg.locator(f'#groups-table tr[data-group="{EMPTY_GROUP}"] .mc-del-group').click(); time.sleep(0.5)
        pg.click('.acf [data-acf="cancel"]'); time.sleep(0.3)
        check('Cancel keeps the group', bool(db("SELECT 1 FROM course_groups WHERE group_name=%s", (EMPTY_GROUP,))))
        pg.locator(f'#groups-table tr[data-group="{EMPTY_GROUP}"] .mc-del-group').click(); time.sleep(0.5)
        pg.click('.acf [data-acf="confirm"]'); time.sleep(2.0)
        check('approving deletes the empty group', not db("SELECT 1 FROM course_groups WHERE group_name=%s", (EMPTY_GROUP,)))
        check('its success message shows after the refresh', f'Deleted the group "{EMPTY_GROUP}"' in last_toast(), last_toast())
        check('no native browser pop-ups were used', not natives, str(natives)[:100])
        check('no script errors on the page', not errs, '; '.join(errs)[:160])

        print('\n== phone width ==')
        m = b.new_context(viewport={'width': 390, 'height': 800}, storage_state=ctx.storage_state()); mp = m.new_page()
        mp.goto(f'{ADMIN}/courses#panel-list', wait_until='domcontentloaded'); time.sleep(1.2)
        mp.locator(f'#courses-tbody tr[data-code="{USED}"] .mc-btn-danger').click(); time.sleep(0.8)
        box = mp.locator('.acf-box').bounding_box()
        check('approval box fits the phone screen with a side gutter',
              box and box['x'] >= 12 and box['x'] + box['width'] <= 378, str(box))
        check('no sideways scrolling', mp.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
        if SHOT:
            mp.screenshot(path=f'{ROOT}/scripts/checks/shots/courses_delete_blocked_mobile.png')
        m.close()
        if SHOT:
            open_list()
            row(USED).locator('.mc-btn-edit').click(); time.sleep(0.4)
            pg.fill('#editSubgroup', 'SELFTEST shot'); pg.click('#editSave'); time.sleep(0.5)
            pg.screenshot(path=f'{ROOT}/scripts/checks/shots/courses_edit_confirm.png')
        b.close()

    print('\n== the server refuses on its own ==')
    s = requests.Session()
    html = s.get(f'{ADMIN}/admin_login').text
    tok = re.search(r'name="csrf-token"[^>]*content="([^"]+)"', html).group(1)
    s.post(f'{ADMIN}/admin_login', data={'email': ADMIN_EMAIL, '_csrf_token': tok})
    s.post(f'{ADMIN}/admin_login', data={'password': ADMIN_PASSWORD, '_csrf_token': tok})
    page = s.get(f'{ADMIN}/courses').text
    tok = re.search(r'name="csrf-token"[^>]*content="([^"]+)"', page).group(1)
    r = s.get(f'{ADMIN}/courses/usage/{USED}', headers={'Accept': 'application/json'})
    check('usage endpoint reports the course as not deletable', r.ok and r.json().get('deletable') is False, r.text[:100])
    r = s.post(f'{ADMIN}/courses/delete/{USED}', headers={'X-CSRFToken': tok, 'Accept': 'application/json'})
    check('a direct delete of a course in use is refused (409)', r.status_code == 409 and 'enrolled student' in r.text, f'{r.status_code} {r.text[:90]}')
    r = s.post(f'{ADMIN}/courses/delete/{USED}', headers={'Accept': 'application/json'})
    check('a delete without the CSRF token is refused', r.status_code in (400, 403), str(r.status_code))
    anon = requests.get(f'{ADMIN}/courses/usage/{USED}', headers={'Accept': 'application/json'})
    check('usage endpoint needs a signed-in admin', anon.status_code == 401, str(anon.status_code))
finally:
    cleanup()
    left = db("SELECT COUNT(*) n FROM courses WHERE code LIKE 'SLFT%'")[0]['n'] \
        + db("SELECT COUNT(*) n FROM course_groups WHERE group_name LIKE 'SELFTEST%'")[0]['n'] \
        + db("SELECT COUNT(*) n FROM course_group_codes WHERE code LIKE 'SLFT%'")[0]['n']
    check('SELFTEST rows removed', left == 0, f'{left} left')
    check('your own courses, groups, codes and premium setup are untouched', snapshot() == before)

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
