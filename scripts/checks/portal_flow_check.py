import json, re, sys, time
import mysql.connector, requests
from dotenv import dotenv_values
from playwright.sync_api import sync_playwright

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
ADMIN, USER = 'http://127.0.0.1:5001', 'http://127.0.0.1:5002'
ADMIN_EMAIL, ADMIN_PASSWORD = 'rajakumarvijeta7087@gmail.com', 'Raja@7479'
TAG = 'SELFTEST'
COMP_GROUP = 'SELFTESTCOMP'
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
    db("DELETE FROM course_group_sections WHERE group_name IN (%s, %s)", (COMP_GROUP, 'SELFTEST GROUP'))
    db("DELETE FROM course_groups WHERE group_name=%s", (COMP_GROUP,))
    db("DELETE FROM comm_user_log WHERE test_key LIKE 'free_selftest%%'")
    db("DELETE FROM cp_attempts WHERE test_id IN (SELECT id FROM cp_tests WHERE test_key LIKE 'free_selftest%%' OR test_key LIKE 'free_5e1f7e57%%')")


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
    print('\n== coding only under placement groups (admin) ==')
    r = api('post', '/api/catalog/groups', json={'group_name': COMP_GROUP, 'platform': 'competitive'})
    check('a competitive group can be created with its platform', r.status_code == 200 and db("SELECT platform FROM course_groups WHERE group_name=%s", (COMP_GROUP,))[0]['platform'] == 'competitive', r.text[:80])
    for key in ('coding_test', 'communication_test', 'tcs_test', 'coding_practice'):
        r = api('post', '/api/catalog/group-sections', json={'group_name': COMP_GROUP, 'section_key': key, 'enabled': True})
        check(f'{key} cannot be offered to a competitive group', r.status_code == 409 and not db("SELECT 1 FROM course_group_sections WHERE group_name=%s AND section_key=%s", (COMP_GROUP, key)), f'{r.status_code} {r.text[:90]}')
    r = api('post', '/api/catalog/group-sections', json={'group_name': COMP_GROUP, 'section_key': 'mock_test', 'enabled': True})
    check('mock_test can be offered to a competitive group', r.status_code == 200, r.text[:80])
    r = api('post', '/api/catalog/group-sections', json={'group_name': STU['name'], 'section_key': 'coding_test', 'enabled': True})
    check('coding_test can be offered to a placement group', r.status_code == 200, r.text[:80])
    r = api('put', f"/api/catalog/groups/{STU['name']}", json={'label': STU['name'], 'position': 99, 'platform': 'competitive'})
    check('a placement group that still offers coding cannot be switched to competitive', r.status_code == 409, r.text[:90])
    r = api('post', '/api/catalog/group-sections', json={'group_name': STU['name'], 'section_key': 'coding_test', 'enabled': False})
    check('coding cannot be unticked while the group has coding content', r.status_code == 409, r.text[:90])
    api('put', f'/api/catalog/groups/{COMP_GROUP}', json={'label': COMP_GROUP, 'position': 99, 'platform': 'placement'})
    api('post', '/api/catalog/group-sections', json={'group_name': COMP_GROUP, 'section_key': 'coding_test', 'enabled': True})
    r = api('put', f'/api/catalog/groups/{COMP_GROUP}', json={'label': COMP_GROUP, 'position': 99, 'platform': 'competitive'})
    api('post', '/api/catalog/group-sections', json={'group_name': COMP_GROUP, 'section_key': 'coding_test', 'enabled': False})
    r2 = api('put', f'/api/catalog/groups/{COMP_GROUP}', json={'label': COMP_GROUP, 'position': 99, 'platform': 'competitive'})
    check('a group offering coding cannot become competitive until coding is unticked', r.status_code == 409 and r2.status_code == 200 and db("SELECT platform FROM course_groups WHERE group_name=%s", (COMP_GROUP,))[0]['platform'] == 'competitive', f'{r.status_code} {r2.status_code}')
    html = s.get(ADMIN + '/manage_course_content').text
    m = re.search(r'window\.CC_GROUP_SECTIONS = (\{.*?\});</script>', html, re.S)
    sections = json.loads(m.group(1)) if m else {}
    comp = [x['value'] for x in sections.get(COMP_GROUP, [])]
    check('Course Content offers the competitive group mock tests only', comp == ['mock_test'], str(comp))
    gate = [x['value'] for x in sections.get('GATE', [])]
    check('GATE (a real competitive group) offers no coding, communication or TCS content', not any(k in gate for k in ('coding_test', 'communication_test', 'tcs_test', 'coding_practice')), str(gate))
    r = api('get', f"/api/coding-panel/{fx['mock_id']}")
    check('the coding editor refuses to open on a mock-test description', r.status_code in (400, 403), f'{r.status_code} {r.text[:80]}')
    try:
        db("INSERT INTO course_content (code,name,stream,section,section_id,title,subtitle,label,price,discount,details,status) VALUES ('CS','GATE','x','coding_test','SELFTESTTRG','SELFTEST trg','s','Free',0,0,'<p>x</p>','active')")
        db("DELETE FROM course_content WHERE section_id='SELFTESTTRG'"); blocked = False
    except Exception as e:
        blocked = 'Placement group' in str(e)
    check('even raw SQL cannot put coding content under GATE (database trigger)', blocked)
    r = s.post(ADMIN + '/manage_course_content', data={'code': 'CS', 'name': 'GATE', 'stream': 'SELFTEST stream', 'section': 'coding_test', 'title': 'SELFTEST comp coding',
                                                        'subtitle': 's', 'details': '<p>d</p>', 'label': 'Free', 'status': 'active', 'price': '0', 'discount': '0',
                                                        'syllabus_position': 'below', 'syllabus_label': '', 'max_test_descriptions': '', '_csrf_token': H['X-CSRFToken']}, headers=H)
    made = db("SELECT id FROM course_content WHERE title='SELFTEST comp coding'")
    for row in made: db("DELETE FROM course_content WHERE id=%s", (row['id'],))
    check('the Course Content form refuses coding content for a GATE course', r.status_code < 500 and not made, f'{r.status_code} made={len(made)}')
    html = s.get(ADMIN + '/courses').text
    check('Courses & Groups shows each group\'s platform', 'mc-group-platform' in html and 'group-platform' in html)

    print('\n== fixtures for the portals ==')
    r = api('post', '/api/test-descriptions/add', json={'test_id': fx['tcs_sid'], 'test_key': fx['tcs_key'], 'subject_title': f'{TAG} TCS exam',
                                                        'subject_subtitle': 'x', 'total_questions': 2, 'total_marks': 2, 'total_duration_minutes': 30,
                                                        'show_calculator': 1, 'access_label': 'free'})
    db("UPDATE tcs_exams SET is_published=1 WHERE aptitude_test_key=%s", (fx['tcs_key'],))
    D = fx['coding_id']; T = api('get', f'/api/coding-panel/{D}').json()['test']['id']
    sec = api('post', f'/api/coding-panel/{D}/sections', json={'title': f'{TAG} coding', 'section_type': 'coding', 'duration_min': 20}).json()['section_id']
    api('post', f'/api/coding-panel/sections/{sec}/questions', json={'title': f'{TAG} q', 'statement_html': '<p>Print 1</p>', 'difficulty': 'Easy', 'marks': 10,
                                                                     'allowed_languages': ['python'], 'time_limit_sec': 5, 'memory_limit': '256m',
                                                                     'testcases': [{'input_text': '', 'expected_output': '1', 'is_hidden': False}]})
    slug = db("SELECT slug FROM cp_tests WHERE id=%s", (T,))[0]['slug']
    check('a published coding test exists for the fixture', bool(slug) and db("SELECT is_published FROM cp_tests WHERE id=%s", (T,))[0]['is_published'] == 1)

    print('\n== the student pages ==')
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome', headless=True)
        ctx = b.new_context(viewport={'width': 1440, 'height': 960}); ctx.set_default_timeout(20000)
        pg = ctx.new_page(); errs, natives = [], []
        pg.on('pageerror', lambda e: errs.append(str(e)[:200]))
        pg.on('dialog', lambda d: (natives.append(d.message), d.dismiss()))
        pg.goto(f'{USER}/user_login'); time.sleep(1.0)
        pg.fill('input[name="email"]', STU['email']); pg.keyboard.press('Enter'); time.sleep(1.5)
        pg.fill('input[name="password"]', STU['password']); pg.keyboard.press('Enter'); time.sleep(2.0)

        def same_layout(label):
            ok = (pg.locator('.stats-grid').count() == 1 and pg.locator('.custom-tabs').count() == 1 and pg.locator('#testGrid').count() == 1
                  and pg.locator('#resultsList').count() == 1 and pg.locator('aside.sidebar').count() == 1
                  and pg.evaluate("!!document.querySelector('link[href*=\"test_dashboard/test_dashboard.css\"]')"))
            check(f'{label}: uses the one shared test-list layout (stats, tabs, cards, sidebar)', ok, pg.locator('.tl-portal-chip').inner_text() if pg.locator('.tl-portal-chip').count() else 'no chip')

        U = STU['unique_code']
        pg.goto(f"{USER}/open/mock_test/{fx['mock_sid']}/{CODE}/{U}"); time.sleep(1.8)
        same_layout('competitive')
        card = pg.locator('.test-card').first
        check('competitive: the card shows Free and Start Test', card.locator('.tag-free').count() == 1 and 'start test' in card.inner_text().lower(), card.inner_text()[:80] if card.count() else 'no card')
        href = card.locator('a.btn-action').get_attribute('href') or ''
        check('competitive: Start Test goes to the exam sign-in (which opens the exam window)', '/test-login/' in href, href)

        pg.goto(f"{USER}/tcs/{CODE}/{U}/{fx['tcs_sid']}"); time.sleep(1.8)
        same_layout('TCS')
        card = pg.locator('.test-card').first
        check('TCS: the exam card shows Free, Start Exam and the aptitude/coding parts', card.locator('.tag-free').count() == 1 and 'start exam' in card.inner_text().lower() and 'aptitude + coding' in card.inner_text().lower(), card.inner_text()[:120] if card.count() else 'no card')
        check('TCS: no TCS-only card markup remains', pg.locator('.tcs-card').count() == 0)
        with ctx.expect_page() as popup_info:
            card.locator('a.tl-launch').click()
        ex = popup_info.value; ex.set_default_timeout(20000); ex.wait_for_load_state(); time.sleep(2.0)
        check('TCS: Start Exam opens the exam window straight on the general instructions page (no launch page)', '/test-instruction/' in ex.url and 'General Instructions' in ex.inner_text('body'), ex.url)
        ex.click('button:has-text("Next")'); time.sleep(1.5)
        check('TCS: Next shows the paper-specific instructions', '/paper-instruction/' in ex.url and 'Paper-specific' in ex.inner_text('body'), ex.url)
        check('TCS: the card says the exam window is open', 'exam window is open' in pg.locator('.test-card').first.inner_text().lower())
        ex.evaluate("window.sppExamLeaving = true"); ex.close(); time.sleep(2.0)

        pg.goto(f"{USER}/coding/{CODE}/{U}?section_id={fx['code_sid']}"); time.sleep(1.8)
        same_layout('coding')
        card = pg.locator('.test-card').first
        href = card.locator('a.btn-action').get_attribute('href') if card.count() else ''
        check('coding: Start Test goes straight to the lobby (no system-check page)', card.count() == 1 and f'/coding/test/{slug}/lobby' in (href or ''), str(href))
        r = pg.request.get(f"{USER}/coding/test/{slug}/system-check/{CODE}/{U}", max_redirects=0)
        check('coding: the old system-check address redirects to the lobby', r.status in (301, 302) and '/lobby' in (r.headers.get('location') or ''), f"{r.status} {r.headers.get('location')}")
        pg.goto(href if href.startswith('http') else USER + href); time.sleep(1.5)
        check('coding: the lobby has the Start button and section list', pg.locator('#btnStart').count() == 1 and 'Sections you will attempt' in pg.inner_text('body'), pg.url)

        print('-- coding test window --')
        pg.wait_for_function("!document.getElementById('btnStart').disabled", timeout=20000)
        pg.click('#startLink'); time.sleep(5.0)
        fs = lambda page: page.evaluate("!!document.fullscreenElement")
        popup_on = lambda page: page.evaluate("(() => { const d = document.querySelector('.efg-popup'); return !!d && d.classList.contains('is-on'); })()")
        check('coding: Start Test enters full screen and opens the editor with no full-screen popup', fs(pg) and not popup_on(pg) and pg.locator('#code-editor textarea.editor-input').count() == 1, f'fs={fs(pg)} popup={popup_on(pg)} url={pg.url[-40:]}')
        code = pg.input_value('#code-editor textarea.editor-input')
        check('coding: with no starter code set by the admin, the editor opens on the standard skeleton', 'def main()' in code or 'public class Main' in code or '#include' in code, code[:60])
        pg.click('#code-editor textarea.editor-input')
        before = pg.input_value('#code-editor textarea.editor-input')
        pasted = pg.evaluate("""(() => { const ta = document.querySelector('#code-editor textarea.editor-input'); const dt = new DataTransfer(); dt.setData('text/plain', 'PASTED\\nTEXT');
            const ev = new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }); ta.dispatchEvent(ev); return ev.defaultPrevented; })()""")
        time.sleep(0.4)
        check('coding: paste is blocked in the editor and a notice appears', pasted and pg.input_value('#code-editor textarea.editor-input') == before and 'disabled' in (pg.locator('.spp-secure-toast').last.inner_text() if pg.locator('.spp-secure-toast').count() else ''), f'prevented={pasted}')
        copied = pg.evaluate("(() => { const ev = new ClipboardEvent('copy', { bubbles: true, cancelable: true }); document.querySelector('#code-editor textarea.editor-input').dispatchEvent(ev); return ev.defaultPrevented; })()")
        check('coding: copy is blocked too', copied)
        box = pg.locator('.spp-secure-toasts').bounding_box()
        check('coding: the notice sits at the top-left', box and box['x'] < 60 and box['y'] < 60, str(box))
        time.sleep(3.6)
        check('coding: the notice disappears after 3 seconds', pg.locator('.spp-secure-toast').count() == 0)
        pg.keyboard.press('PrintScreen'); time.sleep(0.5)
        check('coding: PrintScreen blanks the test behind a blurred cover with no message', pg.evaluate("(() => { const c = document.getElementById('sppSecureCover'); return !!c && c.classList.contains('is-on') && c.innerText.trim() === ''; })()"))
        check('coding: the candidate email is watermarked across the test', pg.locator('#sppSecureMark').count() == 1)
        pg.evaluate("document.getElementById('sppSecureCover').classList.remove('is-on')")
        att = db("SELECT a.id, a.status, a.resumed_at, a.last_seen FROM cp_attempts a JOIN cp_tests t ON t.id=a.test_id WHERE t.slug=%s", (slug,))
        check('coding: the running attempt carries a last-seen heartbeat', att and att[0]['status'] == 'in_progress' and att[0]['last_seen'] is not None and att[0]['resumed_at'] is not None, str(att))
        pg2 = ctx.new_page()
        r = pg2.request.get(f"{USER}/test-login/{fx['mock_sid']}/{fx['mock_key']}/{CODE}/{U}", max_redirects=0)
        check('lock: while the coding test window is open, starting another test is refused', r.status in (301, 302), f"{r.status} {r.headers.get('location')}")
        pg2.goto(f"{USER}/test-login/{fx['mock_sid']}/{fx['mock_key']}/{CODE}/{U}"); time.sleep(1.2)
        stack = pg2.locator('.app-flash-stack')
        sbox = stack.bounding_box() if stack.count() else None
        note = stack.inner_text() if stack.count() else ''
        check('lock: the refusal is a toast at the top-left', 'Already another test running' in note and sbox and sbox['x'] < 60 and sbox['y'] < 60, f'{note[:60]} {sbox} {pg2.url[-50:]}')
        time.sleep(3.8)
        check('lock: that toast hides itself after 3 seconds', pg2.locator('.app-flash').count() == 0)
        pg2.close()
        pg.evaluate("window.sppExamLeaving = true")
        pg.goto(f"{USER}/coding/{CODE}/{U}?section_id={fx['code_sid']}"); time.sleep(1.5)
        r = pg.request.get(f"{USER}/test-login/{fx['mock_sid']}/{fx['mock_key']}/{CODE}/{U}", max_redirects=0)
        check('lock: once the coding window is closed, another test can start straight away', r.status == 200, f"{r.status} {r.headers.get('location')}")

        pg.goto(f"{USER}/Communication/assessments/{CODE}/{U}"); time.sleep(1.8)
        same_layout('communication')
        card = pg.locator('.test-card').first
        href = card.locator('a.btn-action').get_attribute('href') if card.count() else ''
        check('communication: the card shows the test with Start Test', card.count() == 1 and 'start test' in card.inner_text().lower(), card.inner_text()[:80] if card.count() else 'no card')
        pg.goto(href if href.startswith('http') else USER + href); time.sleep(2.0)
        check('communication: Start Test lands on the single lobby page (system info, permission and verification pages are gone)', '/assessment_lobby/' in pg.url and pg.locator('#btnStart').count() == 1 and pg.locator('#consentCheck').count() == 1, pg.url)
        pg.wait_for_function("!document.getElementById('btnStart').disabled", timeout=20000)
        pg.click('#startLink'); time.sleep(0.6)
        check('communication: Start is held until the consent box is ticked', '/assessment_lobby/' in pg.url and pg.evaluate("document.getElementById('consentWrap').classList.contains('is-missing')"))
        pg.check('#consentCheck'); pg.click('#startLink'); time.sleep(5.0)
        here = pg.evaluate('location.href')
        check('communication: Start Test enters full screen and opens the test with no full-screen popup', '/start_test_window/' in here and fs(pg) and not popup_on(pg), f'fs={fs(pg)} popup={popup_on(pg)} {here[-60:]}')
        check('communication: the secure layer is active (watermark, clipboard block)', pg.locator('#sppSecureMark').count() == 1 and pg.evaluate("document.getElementById('examSecure').dataset.blockClipboard") == '1')
        pg.evaluate("window.sppExamLeaving = true; if (window.sppMarkExamFinished) window.sppMarkExamFinished();")
        pg.goto(f"{USER}/courses/{CODE}/{U}"); time.sleep(1.2)
        r = pg.request.get(f"{USER}/Communication/assessment_verification/{fx['comm_key']}/{CODE}/{U}", max_redirects=0)
        check('communication: the old verification address redirects to the lobby', r.status in (301, 302) and '/assessment_lobby/' in (r.headers.get('location') or ''), f"{r.status} {r.headers.get('location')}")
        gone = [f"{USER}/{x}" for x in (f"Communication/assessment_system_info/{fx['comm_key']}/{CODE}/{U}",)]
        r = pg.request.get(gone[0], max_redirects=0)
        check('communication: the old system-info address redirects onward instead of showing a page', r.status in (301, 302), str(r.status))
        check('student pages: no JavaScript errors', not errs, str(errs)[:200])
        check('student pages: no browser popups', not natives, str(natives))
        b.close()
finally:
    cleanup()
    selftest_mocktest.remove(db)

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
