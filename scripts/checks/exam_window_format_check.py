import json, os, re, sys, time
from pathlib import Path
import mysql.connector, requests
from dotenv import dotenv_values
from playwright.sync_api import sync_playwright

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
ADMIN, USER = 'http://127.0.0.1:5001', 'http://127.0.0.1:5002'
ADMIN_EMAIL, ADMIN_PASSWORD = 'rajakumarvijeta7087@gmail.com', 'Raja@7479'
TAG = 'SELFTEST'
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


def cleanup():
    db("DELETE FROM practice_questions WHERE title LIKE %s OR section LIKE %s", (f'{TAG}%', f'{TAG}%'))


cleanup()
selftest_mocktest.remove(db)
fx = selftest_mocktest.setup(db)
CODE, STU = fx['code'], fx['student']

s = requests.Session()
def csrf(html):
    m = re.search(r'name="csrf-token"[^>]*content="([^"]+)"', html)
    return m.group(1) if m else ''
tok = csrf(s.get(ADMIN + '/admin_login').text)
s.post(ADMIN + '/admin_login', data={'email': ADMIN_EMAIL, '_csrf_token': tok})
s.post(ADMIN + '/admin_login', data={'password': ADMIN_PASSWORD, '_csrf_token': tok})
page = s.get(ADMIN + '/manage-tests').text
assert 'mtPicker' in page, 'admin login failed'
H = {'X-CSRFToken': csrf(page) or tok}
def api(method, path, **kw):
    return getattr(s, method)(ADMIN + path, headers=H, timeout=60, **kw)

try:
    print('\n== calculator option per test type ==')
    r = api('post', '/api/test-descriptions/add', json={'test_id': fx['code_sid'], 'test_key': 'free_5e1f7e57000000000077', 'subject_title': f'{TAG} coding desc',
                                                        'subject_subtitle': 'x', 'total_questions': 3, 'total_marks': 30, 'total_duration_minutes': 30,
                                                        'show_calculator': 1, 'access_label': 'free'})
    row = db("SELECT id, show_calculator FROM comm_description WHERE test_key='free_5e1f7e57000000000077'")
    check('a coding test saved with the calculator on is stored with the calculator off', r.status_code == 201 and row and row[0]['show_calculator'] == 0, f'{r.status_code} {row} {r.text[:60]}')
    if row:
        r = api('put', f"/api/test-descriptions/update/{row[0]['id']}", json={'show_calculator': 1, 'subject_title': f'{TAG} coding desc 2'})
        got = db("SELECT show_calculator FROM comm_description WHERE id=%s", (row[0]['id'],))[0]['show_calculator']
        check('editing a coding test cannot turn the calculator on', r.ok and got == 0, f'{r.status_code} {got}')
        api('delete', f"/api/test-descriptions/delete/{row[0]['id']}")
    r = api('post', '/api/test-descriptions/add', json={'test_id': fx['comm_sid'], 'test_key': 'free_5e1f7e57000000000078', 'subject_title': f'{TAG} comm desc',
                                                        'subject_subtitle': 'x', 'total_questions': 3, 'total_marks': 30, 'total_duration_minutes': 30,
                                                        'show_calculator': 1, 'access_label': 'free'})
    row = db("SELECT id, show_calculator FROM comm_description WHERE test_key='free_5e1f7e57000000000078'")
    check('a communication test is stored with the calculator off too', r.status_code == 201 and row and row[0]['show_calculator'] == 0, f'{r.status_code} {row}')
    if row: api('delete', f"/api/test-descriptions/delete/{row[0]['id']}")
    check('the mock test keeps its calculator', db("SELECT show_calculator FROM test_description WHERE test_key=%s", (fx['mock_key'],))[0]['show_calculator'] == 1)

    print('\n== practice formats ==')
    fd = {'code': CODE, 'section': f'{TAG} Chapter-wise', 'title': f'{TAG} PYQ set', '_csrf_token': H['X-CSRFToken']}
    r = api('post', '/admin/practice_questions', data=fd)
    check('a format with a section the admin typed is accepted', r.status_code in (200, 201) and db("SELECT 1 FROM practice_questions WHERE section=%s", (f'{TAG} Chapter-wise',)), f'{r.status_code} {r.text[:80]}')
    r = api('post', '/admin/practice_questions', data=dict(fd, title=f'{TAG} Mixed drills'))
    check('a second title under the same section is accepted', r.status_code in (200, 201), r.text[:80])
    r = api('post', '/admin/practice_questions', data=dict(fd, section=f'{TAG} Year PYQ', title=f'{TAG} 2019 to 2024'))
    check('a section containing "year" is accepted', r.status_code in (200, 201), r.text[:80])
    r = api('post', '/admin/practice_questions', data=dict(fd, section='x' * 101))
    check('a section over 100 characters is refused', r.status_code == 400, r.text[:80])
    col = db("SELECT COLUMN_TYPE t FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='practice_questions' AND COLUMN_NAME='section'")[0]['t']
    check('the section column is free text in the database', col.lower().startswith('varchar'), col)

    print('\n== TCS exam access ==')
    r = api('post', '/api/test-descriptions/add', json={'test_id': fx['tcs_sid'], 'test_key': fx['tcs_key'], 'subject_title': f'{TAG} TCS exam',
                                                        'subject_subtitle': 'x', 'total_questions': 2, 'total_marks': 2, 'total_duration_minutes': 30,
                                                        'show_calculator': 1, 'access_label': 'free'})
    tcs_desc = db("SELECT id FROM test_description WHERE test_key=%s", (fx['tcs_key'],))
    check('a TCS description creates the exam link', r.status_code == 201 and tcs_desc and db("SELECT 1 FROM tcs_exams WHERE aptitude_test_key=%s", (fx['tcs_key'],)), f'{r.status_code} {r.text[:80]}')
    db("UPDATE tcs_exams SET is_published=1 WHERE aptitude_test_key=%s", (fx['tcs_key'],))

    print('\n== coding questions in the admin panel ==')
    D = fx['coding_id']
    api('get', f'/api/coding-panel/{D}')
    sec = api('post', f'/api/coding-panel/{D}/sections', json={'title': f'{TAG} coding', 'section_type': 'coding', 'duration_min': 20}).json()['section_id']
    r = api('post', f'/api/coding-panel/sections/{sec}/questions', json={'title': f'{TAG} sum two', 'statement_html': '<p>Print the sum of two numbers</p>', 'difficulty': 'Easy', 'marks': 10,
                                                                          'allowed_languages': ['python', 'java'], 'time_limit_sec': 5, 'memory_limit': '256m',
                                                                          'templates': {'python': 'a, b = map(int, input().split())\n'},
                                                                          'testcases': [{'input_text': '1 2', 'expected_output': '3', 'is_hidden': False}]})
    cq = r.json().get('question_id')
    check('a coding question is stored with its own starter code', r.ok and db("SELECT COUNT(*) n FROM cp_question_templates WHERE question_id=%s", (cq,))[0]['n'] == 1, r.text[:80])
    r = api('get', '/api/coding-panel/starter-templates')
    tpl = r.json().get('templates', {})
    check('the standard starter skeletons are available for every language', r.ok and all(k in tpl for k in ('python', 'java', 'c', 'cpp', 'csharp', 'javascript')) and 'public class Main' in tpl['java'], str(list(tpl))[:80])
    os.chdir(f'{ROOT}/user_app'); sys.path.insert(0, f'{ROOT}/user_app')
    from routes.exam_platform.placement_exam_portal.coding_portal.starter_templates import with_defaults, STARTER_TEMPLATES
    merged = with_defaults({'python': 'x = 1'}, ['python', 'java'])
    check('students keep the admin starter code and get the skeleton only where none was set', merged['python'] == 'x = 1' and merged['java'] == STARTER_TEMPLATES['java'] and STARTER_TEMPLATES == tpl)

    print('\n== the pages ==')
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome', headless=True)
        ctx = b.new_context(viewport={'width': 1440, 'height': 960}); ctx.set_default_timeout(20000)
        pg = ctx.new_page(); errs, natives = [], []
        pg.on('pageerror', lambda e: errs.append(str(e)[:200]))
        pg.on('dialog', lambda d: (natives.append(d.message), d.dismiss()))

        print('-- admin: add description form --')
        pg.goto(f'{ADMIN}/admin_login')
        pg.fill('input[name="email"]', ADMIN_EMAIL); pg.keyboard.press('Enter'); time.sleep(1.2)
        pg.fill('input[name="password"]', ADMIN_PASSWORD); pg.keyboard.press('Enter'); time.sleep(1.5)
        dialog_open = lambda: pg.evaluate("(() => { const d = document.querySelector('.acf'); return !!d && !d.hidden; })()")
        pg.goto(f'{ADMIN}/manage-tests'); time.sleep(1.8)
        try: pg.evaluate("sessionStorage.removeItem('mtPickerPlace')")
        except Exception: pass
        pg.reload(); time.sleep(1.8)
        pg.click(f'.mt-tcard--group[data-group="{STU["name"]}"]'); time.sleep(0.5)
        pg.click(f'.mt-tcard--course[data-course="{CODE}"]'); time.sleep(0.5)
        pg.click(f'.mt-tcard[data-id="{fx["code_sid"]}"]'); time.sleep(1.5)
        pg.click('#mtAddToggle'); time.sleep(0.6)
        check('coding test: the calculator switch is hidden on the add form', pg.evaluate("document.getElementById('addCalcWrap').classList.contains('is-hidden')")
              and not pg.evaluate("document.getElementById('addShowCalculator').checked"))
        pg.click('#mtChangeTestBtn'); time.sleep(0.8)
        pg.click(f'.mt-tcard[data-id="{fx["comm_sid"]}"]'); time.sleep(1.5)
        if pg.locator('#addTestDescriptionContainer.is-hidden').count(): pg.click('#mtAddToggle'); time.sleep(0.5)
        check('communication test: the calculator switch is hidden too', pg.evaluate("document.getElementById('addCalcWrap').classList.contains('is-hidden')"))
        pg.click('#mtChangeTestBtn'); time.sleep(0.8)
        pg.click(f'.mt-tcard[data-id="{fx["mock_sid"]}"]'); time.sleep(1.5)
        if pg.locator('#addTestDescriptionContainer.is-hidden').count(): pg.click('#mtAddToggle'); time.sleep(0.5)
        check('mock test: the calculator switch is shown and on', not pg.evaluate("document.getElementById('addCalcWrap').classList.contains('is-hidden')")
              and pg.evaluate("document.getElementById('addShowCalculator').checked"))
        pg.locator('#testDescriptionsTable .edit-desc-btn').first.click(); time.sleep(0.8)
        check('mock test: the edit dialog shows the calculator switch', not pg.evaluate("document.getElementById('editCalcWrap').classList.contains('is-hidden')"))
        pg.keyboard.press('Escape'); time.sleep(0.5)

        print('-- admin: coding questions panel --')
        pg.click('#mtChangeTestBtn'); time.sleep(0.8)
        pg.click(f'.mt-tcard[data-id="{fx["code_sid"]}"]'); time.sleep(1.5)
        pg.locator('#testDescriptionsTable .coding-questions-btn, #testDescriptionsTable .load-questions-btn').first.click(); time.sleep(2.0)
        order = pg.evaluate("(() => { const list = document.getElementById('cdpQuestionsList'); const editor = document.getElementById('cdpEditor'); return !!(list.compareDocumentPosition(editor) & Node.DOCUMENT_POSITION_FOLLOWING); })()")
        row = pg.locator('#cdpQuestionsList .cdp-q-wrap').first
        check('the stored coding questions are listed before the editor, with their text and languages', order and row.count() == 1 and f'{TAG} sum two' in row.inner_text() and 'Print the sum' in row.inner_text() and 'python, java' in row.inner_text(), row.inner_text()[:120] if row.count() else 'no row')
        check('each question has View, Edit and Delete', row.locator('[data-view-q]').count() == 1 and row.locator('[data-edit-q]').count() == 1 and row.locator('[data-del-q]').count() == 1)
        row.locator('[data-view-q]').click(); time.sleep(1.5)
        detail = row.locator('.cdp-q-detail').inner_text()
        check('View shows the question, its test cases and the starter code the candidate sees', 'Print the sum of two numbers' in detail and 'TEST CASES (1)' in detail.upper() and 'a, b = map(int' in detail and 'public class Main' in detail and 'STANDARD SKELETON' in detail.upper(), detail[:160])
        row.locator('[data-edit-q]').click(); time.sleep(1.5)
        check('Edit loads the question into the editor with its starter code', pg.input_value('#cdpTitle') == f'{TAG} sum two' and 'a, b = map(int' in pg.input_value('.cdp-tpl[data-lang="python"]'))
        pg.click('#cdpFillStarter'); time.sleep(0.8)
        if dialog_open(): pg.click('.acf [data-acf="alt"]'); time.sleep(0.6)
        check('Fill TCS-style starter code fills the empty languages and keeps what was typed', 'a, b = map(int' in pg.input_value('.cdp-tpl[data-lang="python"]') and 'public class Main' in pg.input_value('.cdp-tpl[data-lang="java"]'))
        if pg.locator('#cdpCancelEdit:not(.is-hidden)').count(): pg.click('#cdpCancelEdit'); time.sleep(0.4)

        print('-- admin: practice format form --')
        pg.goto(f'{ADMIN}/manage-practice-papers'); time.sleep(1.5)
        pg.evaluate("window.ppShowView('format')"); time.sleep(0.4)
        check('the format section is a text box, not a dropdown', pg.evaluate("document.querySelector('#ppView-format #section').tagName") == 'INPUT')
        pg.fill('#ppView-format #section', 'Previous year papers'); time.sleep(0.3)
        check('typing a section shows which practice view it opens', 'year-wise' in pg.locator('#sectionOpens').inner_text())
        pg.fill('#ppView-format #section', 'Chapter drills'); time.sleep(0.3)
        check('a section without topic/year opens subject-wise browsing', 'subject-wise' in pg.locator('#sectionOpens').inner_text())
        check('admin pages: no JavaScript errors', not errs, str(errs)[:200])

        print('-- student: dashboard cards --')
        pg.goto(f'{USER}/user_login'); time.sleep(1.0)
        pg.fill('input[name="email"]', STU['email']); pg.keyboard.press('Enter'); time.sleep(1.5)
        pg.fill('input[name="password"]', STU['password']); pg.keyboard.press('Enter'); time.sleep(2.0)
        pg.goto(f"{USER}/courses/{CODE}/{STU['unique_code']}"); time.sleep(2.0)
        body = pg.inner_text('body')
        check('the practice card heading is the section the admin typed', f'{TAG} Chapter-wise' in body, body[:100])
        card = pg.locator(f'.resource-card:has(.card-title:text-is("{TAG} Chapter-wise"))')
        desc = card.locator('.card-desc').inner_text() if card.count() else ''
        check('the card text is the admin title(s), not the old fixed sentence', f'{TAG} PYQ set' in desc and f'{TAG} Mixed drills' in desc and 'Comprehensive practice questions' not in body, desc)
        href = card.locator('a.card-action').get_attribute('href') if card.count() else ''
        check('a plain section opens subject-wise browsing', '/questions/subject/' in (href or ''), str(href))
        ycard = pg.locator(f'.resource-card:has(.card-title:text-is("{TAG} Year PYQ"))')
        yhref = ycard.locator('a.card-action').get_attribute('href') if ycard.count() else ''
        check('a section containing "year" opens year-wise browsing', '/questions/year/' in (yhref or ''), str(yhref))

        print('-- student: TCS exams --')
        pg.goto(f"{USER}/tcs/{CODE}/{STU['unique_code']}/{fx['tcs_sid']}"); time.sleep(1.8)
        card = pg.locator('.test-card').first
        check('the free exam shows a Free badge and a Start button', card.count() == 1 and card.locator('.tag-free').count() == 1 and 'start exam' in card.inner_text().lower(), card.inner_text()[:120] if card.count() else 'no card')
        colour = pg.evaluate("getComputedStyle(document.querySelector('.test-card .btn-action')).backgroundColor")
        primary = pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--primary-color').trim()")
        check('the TCS list uses the site colour, not blue', primary == '#992c25' and 'rgb(0, 123, 255)' not in colour and 'rgb(51, 122, 183)' not in colour, f'{colour} {primary}')
        db("UPDATE test_description SET access_label='paid' WHERE test_key=%s", (fx['tcs_key'],))
        pg.reload(); time.sleep(1.8)
        card = pg.locator('.test-card').first
        txt = card.inner_text().lower()
        check('a Premium exam shows the Premium badge and offers Get Premium', card.locator('.tag-premium').count() == 1 and 'get premium' in txt and 'unlocked' not in txt, txt[:160])
        unlock = card.locator('a.btn-unlock-custom').get_attribute('href')
        check('Get Premium goes to the Premium page, not the shop', '/premium' in (unlock or '') and 'shop' not in (unlock or ''), str(unlock))
        r2 = pg.request.get(f"{USER}/tcs/exam/{db('SELECT id FROM tcs_exams WHERE aptitude_test_key=%s', (fx['tcs_key'],))[0]['id']}/start/{CODE}/{STU['unique_code']}", max_redirects=0)
        check('starting a Premium exam without Premium is redirected away', r2.status in (301, 302, 303) and '/premium' in (r2.headers.get('location') or ''), f"{r2.status} {r2.headers.get('location')}")
        db("UPDATE test_description SET access_label='free' WHERE test_key=%s", (fx['tcs_key'],))
        db("UPDATE course_content SET label='Paid', price=100 WHERE section_id=%s", (fx['tcs_sid'],))
        pg.reload(); time.sleep(1.8)
        card = pg.locator('.test-card').first
        txt = card.inner_text().lower()
        check('an exam inside Paid content shows Paid and Buy content instead', card.locator('.tag-paid').count() == 1 and 'buy content' in txt and 'premium' not in txt, txt[:160])
        db("UPDATE course_content SET label='Free', price=0 WHERE section_id=%s", (fx['tcs_sid'],))

        print('-- student: the test window goes full screen --')
        pg.goto(f"{USER}/open/mock_test/{fx['mock_sid']}/{CODE}/{STU['unique_code']}"); time.sleep(1.8)
        start = pg.locator('a:has-text("Start Test")').first
        href = start.get_attribute('href') or ''
        pg.goto(href if href.startswith('http') else USER + href); time.sleep(1.5)
        with ctx.expect_page() as popup_info:
            pg.click('#test-login-form .sign-in-box')
        ex = popup_info.value; ex.set_default_timeout(20000)
        exerrs = []; ex.on('pageerror', lambda e: exerrs.append(str(e)[:200]))
        ex.wait_for_load_state(); time.sleep(1.5)
        body = ex.inner_text('body')
        check('the exam window opens on the general instructions page first', '/test-instruction/' in ex.url and 'General Instructions' in body and 'Paper-specific' not in body, ex.url)
        ex.click('button:has-text("Next")'); time.sleep(1.5)
        body = ex.inner_text('body')
        check('Next leads to the paper-specific instructions page', '/paper-instruction/' in ex.url and 'Paper-specific' in body and 'General Instructions' not in body, ex.url)
        ex.check('#readiness_checkbox'); ex.click('#ready_to_begin_button'); time.sleep(4.5)
        here = ex.evaluate('location.href')
        check('the test window opened (address shows the test, so a reload stays guarded)', '/start-test/' in here, here)
        fs = lambda: ex.evaluate("!!document.fullscreenElement")
        popup_on = lambda: ex.evaluate("(() => { const d = document.querySelector('.efg-popup'); return !!d && d.classList.contains('is-on'); })()")
        popup_txt = lambda: ex.locator('.efg-card').inner_text() if popup_on() else ''
        check('"I am ready to begin" itself puts the test in full screen, with no full-screen popup at the start', fs() and not popup_on(), f'fs={fs()} popup={popup_on()}')
        clock = ex.locator('#time-left-display').inner_text()
        check('the test loaded in place and its clock is running', bool(re.search(r'\d\d:\d\d', clock)), clock)
        check('the question palette or the empty-test notice rendered', ex.locator('#question-box-container').count() == 1)
        check('the test window carries the full-screen guard', ex.locator('#examFullscreenGuard').count() == 1 and ex.evaluate("!!document.querySelector('script[src*=\"exam_fullscreen_guard\"]')"))
        if not fs():
            check('without full screen the window is blocked by the Enter full screen popup', popup_on() and 'Enter full screen' in popup_txt(), popup_txt()[:80])
            ex.click('#efgAction'); time.sleep(1.0)
        check('the test window is in full screen', fs())
        check('the popup is gone once in full screen', not popup_on())
        ex.evaluate("document.exitFullscreen()"); time.sleep(1.0)
        check('leaving full screen is a violation: a countdown popup demands a return', popup_on() and 'Return to full screen' in popup_txt() and 'Auto-ending' in popup_txt(), popup_txt()[:100])
        ex.click('#efgAction'); time.sleep(1.0)
        check('returning to full screen clears the popup', fs() and not popup_on())
        ex.click('#fullscreen-toggle-btn'); time.sleep(0.8)
        check('the header full-screen button can no longer exit full screen', fs())
        ex.keyboard.press('PrintScreen'); time.sleep(0.6)
        check('PrintScreen blanks the test behind a blurred cover and the email is watermarked', ex.evaluate("(() => { const c = document.getElementById('sppSecureCover'); return !!c && c.classList.contains('is-on'); })()") and ex.locator('#sppSecureMark').count() == 1)
        ex.evaluate("document.getElementById('sppSecureCover').classList.remove('is-on')")
        ex.evaluate("window.dispatchEvent(new Event('beforeunload')); document.exitFullscreen()"); time.sleep(2.0)
        st = db("SELECT status FROM user_test_log WHERE test_key=%s ORDER BY id DESC LIMIT 1", (fx['mock_key'],))
        check('the Leave prompt alone does not end the attempt (it used to be released before the student answered)', st and st[0]['status'] == 'in_progress', str(st))
        check('cancelling the browser Leave prompt does not let the test continue in a normal window: the return-to-full-screen countdown appears', popup_on() and 'Return to full screen' in popup_txt(), popup_txt()[:80])
        ex.click('#efgAction'); time.sleep(1.0)
        check('and returning to full screen clears it again', fs() and not popup_on())
        check('the test window has no JavaScript errors', not exerrs, str(exerrs)[:200])
        ex.evaluate("window.sppExamLeaving = true"); ex.close()
        check('student pages: no browser popups', not natives, str(natives))
        b.close()
finally:
    cleanup()
    selftest_mocktest.remove(db)

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
