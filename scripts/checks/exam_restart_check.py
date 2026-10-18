import base64, faulthandler, io, os, re, sys, time
import mysql.connector, requests
from dotenv import dotenv_values
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
ADMIN = 'http://127.0.0.1:5001'
USER = os.environ.get('SPP_USER_BASE', 'http://127.0.0.1:5002')
ADMIN_EMAIL, ADMIN_PASSWORD = 'rajakumarvijeta7087@gmail.com', 'Raja@7479'
TAG = 'SELFTEST'
sys.path.insert(0, f'{ROOT}/scripts/checks')
import selftest_mocktest
v = dotenv_values(f'{ROOT}/user_app/.env')
ONLY = set(sys.argv[1:])
faulthandler.dump_traceback_later(int(os.environ.get('SPP_CHECK_LIMIT', '900')), exit=True)


def db(q, p=()):
    c = mysql.connector.connect(host=v['DATABASE_HOST'], user=v['DATABASE_USER'], password=v['DATABASE_PASSWORD'],
                                database=v['DATABASE_NAME'], autocommit=True)
    cur = c.cursor(dictionary=True); cur.execute(q, p)
    out = cur.fetchall() if cur.with_rows else []
    cur.close(); c.close(); return out


results = []
def check(name, ok, detail=''):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ''), flush=True)


def want(part):
    return not ONLY or part in ONLY


SHOTS = os.environ.get('SPP_SHOTS') == '1'
def shot(page, name):
    if not SHOTS:
        return
    try:
        os.makedirs(f'{ROOT}/scripts/checks/shots', exist_ok=True)
        page.screenshot(path=f'{ROOT}/scripts/checks/shots/restart_{name}.png')
    except Exception:
        pass


def cleanup():
    db("DELETE FROM comm_attempt_details WHERE email LIKE 'selftest.%%'")
    db("DELETE FROM comm_user_log WHERE test_key LIKE 'free_selftest%%'")
    db("DELETE FROM cp_attempts WHERE test_id IN (SELECT id FROM cp_tests WHERE test_key LIKE 'free_selftest%%' OR test_key LIKE 'free_5e1f7e57%%')")


cleanup()
selftest_mocktest.remove(db)
fx = selftest_mocktest.setup(db)
CODE, STU = fx['code'], fx['student']
EMAIL, U = STU['email'], STU['unique_code']
MOCK = f"{fx['mock_sid']}/{fx['mock_key']}/{CODE}/{U}"
APT = f"{fx['tcs_sid']}/{fx['tcs_key']}/{CODE}/{U}"

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


def add_mcq(section_sid, key, desc_id, rows):
    for number, (sec_id, sec_name) in enumerate(rows, 1):
        db("INSERT INTO test_questions (test_id, test_key, test_description_id, section_id, section_name, question_number, question_type,"
           " question_text, option_a, option_b, option_c, option_d, correct_option, correct_marks, negative_marks, question_level)"
           " VALUES (%s,%s,%s,%s,%s,%s,'MCQ',%s,'<p>first</p>','<p>second</p>','<p>third</p>','<p>fourth</p>','A',1,0,'Easy')",
           (section_sid, key, desc_id, sec_id, sec_name, number, f'<p>{TAG} question {number} of {sec_name}</p>'))


def coding_question(section, title, marks):
    r = api('post', f'/api/coding-panel/sections/{section}/questions', json={
        'title': title, 'statement_html': '<p>Print 1</p>', 'difficulty': 'Easy', 'marks': marks,
        'allowed_languages': ['python'], 'time_limit_sec': 5, 'memory_limit': '256m',
        'templates': {'python': 'print(0)\n'},
        'testcases': [{'input_text': '', 'expected_output': '1', 'is_hidden': False}]})
    return r.json()['question_id']


def student_session():
    u = requests.Session()
    page = u.get(USER + '/user_login', timeout=30).text
    ctok = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    u.post(USER + '/user_login', data={'email': EMAIL, 'csrf_token': ctok}, timeout=30)
    u.post(USER + '/user_login', data={'password': STU['password'], 'csrf_token': ctok}, timeout=30)
    return u


def log_status(key):
    rows = db("SELECT status FROM user_test_log WHERE email=%s AND test_key=%s ORDER BY attempt_number DESC", (EMAIL, key))
    return [r['status'] for r in rows]


try:
    print('\n== fixtures ==')
    add_mcq(fx['mock_sid'], fx['mock_key'], fx['mock_id'], [('1', 'General')] * 4)
    r = api('post', '/api/test-descriptions/add', json={'test_id': fx['tcs_sid'], 'test_key': fx['tcs_key'], 'subject_title': f'{TAG} TCS exam',
                                                        'subject_subtitle': 'x', 'total_questions': 6, 'total_marks': 6, 'total_duration_minutes': 30,
                                                        'show_calculator': 0, 'access_label': 'free'})
    TCS = db("SELECT id FROM test_description WHERE test_key=%s", (fx['tcs_key'],))[0]['id']
    add_mcq(fx['tcs_sid'], fx['tcs_key'], TCS, [('1', 'Numerical Ability')] * 2 + [('2', 'Verbal Ability')] * 2 + [('3', 'Reasoning Ability')] * 2)
    ts1 = api('post', f'/api/coding-panel/{TCS}/sections', json={'title': f'{TAG} Advanced Coding - 1', 'section_type': 'coding', 'duration_min': 20}).json()['section_id']
    ts2 = api('post', f'/api/coding-panel/{TCS}/sections', json={'title': f'{TAG} Advanced Coding - 2', 'section_type': 'coding', 'duration_min': 20}).json()['section_id']
    TQ1 = coding_question(ts1, f'{TAG} tcs one', 10)
    TQ2 = coding_question(ts1, f'{TAG} tcs two', 20)
    TQ3 = coding_question(ts2, f'{TAG} tcs three', 20)
    db("UPDATE tcs_exams SET is_published=1 WHERE aptitude_test_key=%s", (fx['tcs_key'],))
    exam = db("SELECT id, coding_test_id, coding_label FROM tcs_exams WHERE aptitude_test_key=%s", (fx['tcs_key'],))[0]
    db("UPDATE cp_tests SET is_published=1 WHERE id=%s", (exam['coding_test_id'],))
    tcs_coding = db("SELECT slug, total_duration_min FROM cp_tests WHERE id=%s", (exam['coding_test_id'],))[0]
    EXAM, TCS_CT = exam['id'], exam['coding_test_id']
    D = fx['coding_id']; T = api('get', f'/api/coding-panel/{D}').json()['test']['id']
    cs = api('post', f'/api/coding-panel/{D}/sections', json={'title': f'{TAG} coding', 'section_type': 'coding', 'duration_min': 20}).json()['section_id']
    CQ1 = coding_question(cs, f'{TAG} code one', 10)
    CQ2 = coding_question(cs, f'{TAG} code two', 10)
    slug = db("SELECT slug FROM cp_tests WHERE id=%s", (T,))[0]['slug']
    uid = db("SELECT id FROM auth WHERE email=%s", (EMAIL,))[0]['id']
    check('the fixtures exist: a mock test, a TCS exam with three aptitude sections and two coding sections, a coding test',
          bool(EXAM and slug and TQ1 and TQ3 and CQ2), f'exam={EXAM} coding_test={TCS_CT} slug={slug}')

    def tcs_attempt_rows():
        att = db("SELECT id, status FROM cp_attempts WHERE test_id=%s AND user_id=%s", (TCS_CT, uid))
        if not att:
            return None, 0, 0
        a = att[0]
        answers = db("SELECT COUNT(*) n FROM cp_answers WHERE attempt_id=%s", (a['id'],))[0]['n']
        subs = db("SELECT COUNT(*) n FROM cp_submissions WHERE attempt_id=%s", (a['id'],))[0]['n']
        return a, answers, subs

    if want('instructions'):
        print('\n== instruction pages list every section ==')
        u = student_session()
        r = u.get(f"{USER}/tcs/exam/{EXAM}/start/{CODE}/{U}", timeout=30)
        minutes = 30 + int(tcs_coding['total_duration_min'] or 0)
        check('the TCS general instructions show the time of the whole paper (aptitude + coding)',
              '/test-instruction/' in r.url and f'<strong>{minutes}</strong> minutes' in r.text, f'{r.url[-60:]} want {minutes}')
        r = u.get(f"{USER}/paper-instruction/{APT}", timeout=30)
        text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', r.text))
        check('the paper-specific page counts four sections for a TCS exam (three aptitude + Coding)', '4 sections' in text and 'Coding' in text, text[text.find('This question paper'):][:260])
        check('the Coding section has its own row with its questions and marks', 'id="coding-section-row"' in r.text and '3 coding questions for 50 marks' in text, text[text.find('Section Number'):][:300])
        check('the totals include the coding questions and marks', 'has 9 questions for a total of 56 marks' in text, text[text.find('This question paper'):][:120])
        check('the wording is right for more than two sections', 'All sections are compulsory' in text and 'sections sections' not in text)
        u.post(f"{USER}/test-login/{MOCK}", data={'test_key': fx['mock_key']}, headers={'X-Requested-With': 'XMLHttpRequest'}, timeout=30)
        r = u.get(f"{USER}/paper-instruction/{MOCK}", timeout=30)
        text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', r.text))
        check('a competitive test has no Coding row', r.status_code == 200 and 'coding-section-row' not in r.text and '1 section' in text, text[text.find('This question paper'):][:160])
        for key in (fx['mock_key'], fx['tcs_key']):
            db("DELETE FROM user_test_log WHERE email=%s AND test_key=%s", (EMAIL, key))
        db("DELETE FROM tcs_attempts WHERE email=%s", (EMAIL,))

    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome', headless=True)
        ctx = b.new_context(viewport={'width': 1440, 'height': 960}); ctx.set_default_timeout(25000)
        pg = ctx.new_page(); errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)[:200]))
        pg.goto(f'{USER}/user_login'); time.sleep(1.0)
        pg.fill('input[name="email"]', EMAIL); pg.keyboard.press('Enter'); time.sleep(1.5)
        pg.fill('input[name="password"]', STU['password']); pg.keyboard.press('Enter'); time.sleep(2.0)

        def go(url):
            for attempt in range(4):
                try:
                    pg.goto(url)
                    return
                except Exception as exc:
                    if 'interrupted by another navigation' not in str(exc) or attempt == 3:
                        raise
                    time.sleep(1.5)

        def open_mock_window():
            go(f"{USER}/test-login/{MOCK}"); time.sleep(1.2)
            with ctx.expect_page() as popup_info:
                pg.click('#test-login-form .sign-in-box')
            ex = popup_info.value; ex.set_default_timeout(25000)
            ex.wait_for_url('**/test-instruction/**', timeout=25000); time.sleep(1.0)
            ex.click('button:has-text("Next")'); time.sleep(1.2)
            ex.check('#readiness_checkbox'); ex.click('#ready_to_begin_button'); time.sleep(4.5)
            return ex

        def counts(ex):
            return ex.evaluate("({answered: +document.getElementById('answered-count').textContent, notAnswered: +document.getElementById('not-answered-count').textContent,"
                               " notVisited: +document.getElementById('not-visited-count').textContent, review: +document.getElementById('marked-review-count').textContent})")

        if want('list'):
            print('\n== test list: one click, with a spinner ==')
            go(f"{USER}/open/mock_test/{fx['mock_sid']}/{CODE}/{U}"); time.sleep(1.8)
            pg.evaluate("""(() => {
                const a = document.querySelector('#testGrid .test-card a.btn-action');
                let again = false;
                a.addEventListener('click', () => {
                    if (again) return;
                    again = true;
                    const sp = a.querySelector('.tl-spin');
                    const second = new MouseEvent('click', {bubbles: true, cancelable: true});
                    a.dispatchEvent(second);
                    sessionStorage.setItem('selftestSpin', JSON.stringify({loading: a.classList.contains('is-loading'), spin: !!sp,
                        turning: sp ? getComputedStyle(sp).animationName : '', busy: document.body.classList.contains('tl-busy'),
                        text: a.textContent.trim(), secondStopped: second.defaultPrevented}));
                });
            })()""")
            pg.locator('#testGrid .test-card a.btn-action').first.click()
            pg.wait_for_url('**/test-login/**', timeout=20000); time.sleep(0.8)
            state = pg.evaluate("JSON.parse(sessionStorage.getItem('selftestSpin') || '{}')")
            check('Start Test shows a turning spinner as soon as it is clicked', state.get('loading') and state.get('spin') and state.get('turning') == 'tl-spin' and state.get('busy'), str(state))
            check('a second click while it is opening is ignored', state.get('secondStopped') is True, str(state))
            check('it then arrives on the exam sign-in page', pg.locator('#test-login-form .sign-in-box').count() == 1, pg.url[-70:])

        if want('guard'):
            print('\n== competitive test window: leaving, countdown, restart, no retake ==')
            ex = open_mock_window()
            check('the test window opened in full screen', '/start-test/' in ex.evaluate('location.href') and ex.evaluate('!!document.fullscreenElement'))
            ex.click('#question-options-area input[type="radio"]'); ex.click('#save-next-btn'); time.sleep(0.6)
            first = counts(ex)
            check('answering a question turns it green', first['answered'] == 1, str(first))
            ex.click('#view-question-paper-btn'); time.sleep(2.5)
            mock_paper = ex.evaluate("(() => { const b = document.getElementById('question-paper-body'); return {tabs: Array.from(b.querySelectorAll('.qp-tab')).map(t => t.textContent.trim()), items: b.querySelectorAll('.qp-item').length}; })()")
            check('a competitive test: Question Paper shows its section tab and all its questions', mock_paper['tabs'] == ['All sections', 'General'] and mock_paper['items'] == 4, str(mock_paper))
            ex.click('#close-question-paper-btn'); time.sleep(0.4)
            count = lambda: int(ex.locator('#efgCount').inner_text() or 0)
            title = lambda: ex.locator('#efgTitle').inner_text()
            ex.evaluate("document.exitFullscreen()"); time.sleep(1.3)
            c1 = count()
            alpha = ex.evaluate("(() => { const m = getComputedStyle(document.querySelector('.efg-popup')).backgroundColor.match(/[\\d.]+/g); return m.length > 3 ? parseFloat(m[3]) : 1; })()")
            shot(ex, 'countdown_popup')
            check('leaving full screen starts the 20 second countdown', 18 <= c1 <= 20 and 'Return to full screen' in title(), f'{c1} {title()}')
            check('the countdown popup hides the test behind it (not a see-through layer)', alpha >= 0.9, f'alpha={alpha}')
            time.sleep(3.0)
            c2 = count()
            ex.evaluate("document.hasFocus = () => false; window.dispatchEvent(new Event('blur'))"); time.sleep(0.9)
            c3 = count()
            ex.evaluate("delete document.hasFocus; window.dispatchEvent(new Event('focus'))"); time.sleep(0.6)
            c4 = count()
            ex.evaluate("document.hasFocus = () => false; window.dispatchEvent(new Event('blur'))"); time.sleep(0.9)
            ex.evaluate("delete document.hasFocus; window.dispatchEvent(new Event('focus'))"); time.sleep(0.6)
            c5 = count()
            check('clicking outside the page (address bar) and back does not restart the countdown', c2 <= 17 and c5 < c4 <= c3 <= c2 and c5 >= c2 - 5, f'{c1} -> {c2} -> {c3} -> {c4} -> {c5}')
            ex.click('#efgAction'); time.sleep(0.8)
            check('returning to full screen clears the popup', ex.evaluate('!!document.fullscreenElement') and not ex.evaluate("document.querySelector('.efg-popup').classList.contains('is-on')"))
            ex.evaluate("document.exitFullscreen()"); time.sleep(1.0)
            c6 = count()
            check('leaving again straight away continues from the time that was left, not from 20', c6 <= c5 and c6 >= 5, f'{c5} -> {c6}')
            ex.click('#efgAction'); time.sleep(0.8)

            cdp = ctx.new_cdp_session(ex)
            frames = []
            def on_frame(ev):
                im = Image.open(io.BytesIO(base64.b64decode(ev['data']))).convert('RGB')
                w, h = im.size
                px = im.getpixel((int(w * 0.30), int(h * 0.72)))
                frames.append((time.time(), sum(px) / 3.0))
                try: cdp.send('Page.screencastFrameAck', {'sessionId': ev['sessionId']})
                except Exception: pass
            cdp.on('Page.screencastFrame', on_frame)
            time.sleep(1.5)
            cdp.send('Page.startScreencast', {'format': 'png', 'everyNthFrame': 3, 'maxWidth': 720, 'maxHeight': 480})
            pg.wait_for_timeout(1200)
            before_clock = ex.evaluate("testManager.timeLeft")
            dialogs = []
            ex.on('dialog', lambda d: dialogs.append(d))
            t_open = time.time()
            ex.close(run_before_unload=True)
            pg.wait_for_timeout(3500)
            check('closing the test window asks "Leave site?"', len(dialogs) == 1 and dialogs[0].type == 'beforeunload', str([d.type for d in dialogs]))
            lit = [f for f in frames if f[0] < t_open]
            dark = [f for f in frames if f[0] >= t_open]
            check('while that prompt is open the test behind it is blanked out within about a second',
                  bool(lit) and lit[-1][1] > 150 and bool(dark) and dark[-1][1] < 60 and dark[-1][0] - t_open < 2.0,
                  f"before={lit[-1][1] if lit else -1:.0f} during={[round(f[1]) for f in dark[-3:]]} after {dark[-1][0] - t_open if dark else -1:.1f}s frames={len(frames)}")
            if dialogs:
                dialogs[0].dismiss()
            pg.wait_for_timeout(350)
            held_cover = ex.evaluate("(() => { const c = document.getElementById('sppSecureCover'); return !!c && c.classList.contains('is-on'); })()")
            check('after Cancel the test stays covered for a moment instead of flashing back', held_cover)
            wording = ex.evaluate("(() => { const c = document.getElementById('sppSecureCover'); const w = document.getElementById('sppSecureWatch'); return {cover: c ? c.textContent.trim() : '', watch: w ? w.textContent.trim() : '', blur: c ? getComputedStyle(c).backdropFilter : ''}; })()")
            check('the covers carry no message, only a blurred dark screen', wording['cover'] == '' and wording['watch'] == '' and 'blur' in wording['blur'], str(wording))
            pg.wait_for_timeout(2600)
            state = ex.evaluate("(() => { const c = document.getElementById('sppSecureCover'); const w = document.getElementById('sppSecureWatch');"
                                " return {cover: !!c && c.classList.contains('is-on'), watch: w ? parseFloat(getComputedStyle(w).opacity) : -1, fs: !!document.fullscreenElement, left: testManager.timeLeft}; })()")
            check('then, still in full screen, the test is readable again and continues', not state['cover'] and state['watch'] < 0.05 and log_status(fx['mock_key'])[0] == 'in_progress', f"{state} {log_status(fx['mock_key'])}")
            check('the exam clock kept running while the prompt was open', before_clock - state['left'] >= 5, f"{before_clock} -> {state['left']}")
            try: cdp.send('Page.stopScreencast')
            except Exception: pass

            ex.evaluate("window.sppExamLeaving = true"); ex.close(); time.sleep(2.5)
            check('closing the window ends that sitting', log_status(fx['mock_key'])[0] != 'in_progress', str(log_status(fx['mock_key'])))
            ex = open_mock_window()
            again = counts(ex)
            check('opening the test again starts from new: nothing answered, nothing marked', '/start-test/' in ex.evaluate('location.href') and again['answered'] == 0 and again['review'] == 0 and again['notVisited'] == 3 and again['notAnswered'] == 1, str(again))
            ex.click('#submit-test-btn'); time.sleep(0.6)
            ex.click('button:has-text("OK")')
            for _ in range(40):
                time.sleep(0.5)
                if '/test_feedback/' in ex.evaluate('location.href'): break
            check('Submit finishes the test', '/test_feedback/' in ex.evaluate('location.href') and 'completed' in log_status(fx['mock_key']), str(log_status(fx['mock_key'])))
            try: ex.close()
            except Exception: pass
            rows_before = len(log_status(fx['mock_key']))
            ajax = {'X-Requested-With': 'XMLHttpRequest'}
            r = pg.request.post(f"{USER}/test-login/{MOCK}", form={'test_key': fx['mock_key']}, headers=ajax)
            check('after Submit the exam sign-in refuses a second attempt', r.status == 403 and 'already completed' in r.text(), f'{r.status} {r.text()[:80]}')
            r = pg.request.post(f"{USER}/process-readiness/{MOCK}", form={'readiness_checkbox': 'on'})
            r2 = pg.request.post(f"{USER}/test-login/{MOCK}", form={'test_key': fx['mock_key']}, headers=ajax)
            check('a hand-made "ready to begin" request cannot open a new attempt either', len(log_status(fx['mock_key'])) == rows_before and '/start-test/' not in r.url and r2.status == 403, f'rows {rows_before} -> {len(log_status(fx["mock_key"]))} {r.url[-50:]} {r2.status}')
            go(f"{USER}/open/mock_test/{fx['mock_sid']}/{CODE}/{U}"); time.sleep(1.5)
            check('the test list shows it under results, with no Start button', pg.locator('#testGrid .test-card a.btn-action').count() == 0 and pg.locator('#resultsList .report-card').count() == 1,
                  f"start buttons={pg.locator('#testGrid .test-card a.btn-action').count()} results={pg.locator('#resultsList .report-card').count()} {pg.url[-60:]}")

        if want('tcs'):
            print('\n== TCS exam window: coding palette, restart, no retake ==')
            def open_tcs_window(label):
                go(f"{USER}/tcs/{CODE}/{U}/{fx['tcs_sid']}"); time.sleep(1.8)
                card = pg.locator('#testGrid .test-card').first
                text = card.inner_text().lower()
                with ctx.expect_page() as popup_info:
                    card.locator('a.tl-launch').click()
                ex = popup_info.value; ex.set_default_timeout(25000); ex.wait_for_load_state(); time.sleep(1.5)
                return ex, text

            def into_test(ex):
                ex.click('button:has-text("Next")'); time.sleep(1.2)
                body = ex.inner_text('body')
                shot(ex, 'paper_instruction')
                ex.check('#readiness_checkbox'); ex.click('#ready_to_begin_button'); time.sleep(5.0)
                return body

            def open_coding(ex):
                ex.click('#section-tabs-container .tab[data-section-id="__coding__"]')
                frame = ex.frame_locator('#coding-frame')
                frame.locator('#code-editor textarea').wait_for(state='visible', timeout=25000)
                time.sleep(1.5)
                return frame

            cls = lambda ex, qid: ex.evaluate(f"(document.getElementById('cqbtn_{qid}') || {{className: 'missing'}}).className")

            ex, text = open_tcs_window('first')
            check('the TCS card starts with "Start Exam"', 'start exam' in text, text[:80])
            time.sleep(1.0)
            opened = pg.evaluate("(() => { const a = document.querySelector('#testGrid .test-card a.tl-launch'); return {open: a.classList.contains('is-open'), text: a.textContent.trim(), busy: document.body.classList.contains('tl-busy')}; })()")
            check('the card then says the exam window is open and cannot be clicked twice', opened['open'] and 'Exam window is open' in opened['text'], str(opened))
            body = into_test(ex)
            check('in the browser the paper-specific page lists the Coding section', 'Coding' in body and '3 coding questions for 50 marks' in re.sub(r'\s+', ' ', body), re.sub(r'\s+', ' ', body)[:200])
            tabs = ex.evaluate("Array.from(document.querySelectorAll('#section-tabs-container .tab')).map(t => t.textContent.trim())")
            check('the test window has the three aptitude tabs and the Coding tab', '/start-test/' in ex.evaluate('location.href') and len(tabs) == 4 and 'Coding' in tabs[-1], str(tabs))
            start_counts = counts(ex)
            check('the status panel counts the coding questions from the start (6 aptitude + 3 coding)',
                  start_counts['notVisited'] == 8 and start_counts['notAnswered'] == 1 and start_counts['answered'] == 0, str(start_counts))
            ex.click('#view-question-paper-btn'); time.sleep(2.5)
            paper = lambda: ex.evaluate("(() => { const b = document.getElementById('question-paper-body'); return {tabs: Array.from(b.querySelectorAll('.qp-tab')).map(t => t.textContent.trim()), on: (b.querySelector('.qp-tab.is-on') || {}).textContent, sections: Array.from(b.querySelectorAll('.qp-sec')).map(h => h.textContent.trim()), items: b.querySelectorAll('.qp-item').length}; })()")
            first = paper()
            check('Question Paper offers a tab for every section, including the coding sections', first['tabs'] == ['All sections', 'Numerical Ability', 'Verbal Ability', 'Reasoning Ability', f'{TAG} Advanced Coding - 1', f'{TAG} Advanced Coding - 2'], str(first['tabs']))
            check('it opens on the section the student is in', first['on'] == 'Numerical Ability' and first['sections'] == ['Numerical Ability'] and first['items'] == 2, str(first))
            ex.click('#question-paper-body .qp-tab:has-text("Verbal Ability")'); time.sleep(0.5)
            second = paper()
            check('another section tab shows that section', second['on'] == 'Verbal Ability' and second['sections'] == ['Verbal Ability'] and second['items'] == 2, str(second))
            ex.click('#question-paper-body .qp-tab:has-text("All sections")'); time.sleep(0.5)
            whole = paper()
            check('All sections shows every aptitude question and the coding questions', whole['items'] == 9 and len(whole['sections']) == 5, str(whole))
            ex.click('#close-question-paper-btn'); time.sleep(0.5)
            att, answers, subs = tcs_attempt_rows()
            check('the coding part starts empty', att is not None and answers == 0 and subs == 0, f'{att} answers={answers} subs={subs}')
            frame = open_coding(ex)
            check('opening the Coding tab marks only the open question as visited (red), the rest stay grey',
                  'red-shield' in cls(ex, TQ1) and 'gray-box' in cls(ex, TQ2), f'{cls(ex, TQ1)} | {cls(ex, TQ2)}')
            frame.locator('#code-editor textarea').fill('print(1)\n'); time.sleep(3.0)
            saved = db("SELECT code FROM cp_answers WHERE attempt_id=%s AND question_id=%s", (att['id'], TQ1))
            check('typed code is saved automatically', bool(saved) and 'print(1)' in (saved[0]['code'] or ''), str(saved)[:80])
            check('typing and autosave do not turn the question green', 'green' not in cls(ex, TQ1) and 'red-shield' in cls(ex, TQ1), cls(ex, TQ1))
            frame.locator('#btn-run').click()
            for _ in range(60):
                time.sleep(0.5)
                if not frame.locator('#btn-run').is_disabled(): break
            ran = frame.locator('#panel-cases').inner_text()
            check('Compile Code runs the sample test', 'Test Cases Passed' in ran or 'Passed' in ran, ran[:80])
            check('compiling does not turn the question green either', 'green' not in cls(ex, TQ1), cls(ex, TQ1))
            frame.locator('#btn-submit').click(); time.sleep(0.5)
            frame.locator('.modal-backdrop .btn-primary').click()
            for _ in range(80):
                time.sleep(0.5)
                if db("SELECT 1 FROM cp_submissions WHERE attempt_id=%s AND question_id=%s", (att['id'], TQ1)): break
            time.sleep(1.2)
            check('only Final Submit turns the question green', 'green-shield' in cls(ex, TQ1), cls(ex, TQ1))
            check('the Answered counter counts it', counts(ex)['answered'] == 1, str(counts(ex)))
            frame.locator('#emb-review').click(); time.sleep(1.2)
            check('Marked For Review on a submitted question shows the answered-and-marked badge', 'purple-green-circle' in cls(ex, TQ1), cls(ex, TQ1))
            frame.locator('.emb-footer a:has-text("Next")').click(); time.sleep(2.0)
            check('Next opens the second question: it becomes visited (red), not green', 'red-shield' in cls(ex, TQ2), cls(ex, TQ2))
            frame.locator('#emb-review').click(); time.sleep(1.2)
            shot(ex, 'tcs_coding_palette')
            check('Marked For Review on an unsubmitted question shows purple', 'purple-circle' in cls(ex, TQ2) and 'green' not in cls(ex, TQ2), cls(ex, TQ2))
            sub_tabs = ex.evaluate("Array.from(document.querySelectorAll('#coding-subtabs .tab')).map(t => t.textContent.trim())")
            ex.click(f'#coding-subtabs .tab[data-coding-section="{ts2}"]'); time.sleep(2.5)
            check('the second coding section opens from its own tab', len(sub_tabs) == 2 and 'red-shield' in cls(ex, TQ3), f'{sub_tabs} {cls(ex, TQ3)}')
            att, answers, subs = tcs_attempt_rows()
            check('this sitting now has saved code, a review mark and a submission', answers >= 2 and subs == 1, f'answers={answers} subs={subs}')

            ex.evaluate("window.sppExamLeaving = true"); ex.close(); time.sleep(3.0)
            ex, text = open_tcs_window('again')
            check('after leaving, the card offers the exam again', 'resume exam' in text or 'start exam' in text, text[:80])
            into_test(ex)
            att, answers, subs = tcs_attempt_rows()
            check('opening the exam again clears the coding part: no saved code, no review marks, no submissions', '/start-test/' in ex.evaluate('location.href') and answers == 0 and subs == 0 and att['status'] == 'in_progress', f'answers={answers} subs={subs} {att}')
            fresh = counts(ex)
            check('the aptitude part is new as well', fresh['answered'] == 0 and fresh['review'] == 0, str(fresh))
            frame = open_coding(ex)
            code = frame.locator('#code-editor textarea').input_value()
            marked = frame.locator('#emb-review').get_attribute('class')
            check('the coding palette is new: nothing green, nothing purple', 'red-shield' in cls(ex, TQ1) and 'gray-box' in cls(ex, TQ2) and 'purple' not in cls(ex, TQ1) + cls(ex, TQ2), f'{cls(ex, TQ1)} | {cls(ex, TQ2)}')
            check('the editor shows the starter code, not the code from the earlier sitting', 'print(0)' in code and 'print(1)' not in code and 'is-marked' not in (marked or ''), f'{code!r} {marked}')
            frame.locator('#code-editor textarea').fill('print(1)\n'); time.sleep(0.5)
            frame.locator('#btn-submit').click(); time.sleep(0.5)
            frame.locator('.modal-backdrop .btn-primary').click()
            for _ in range(80):
                time.sleep(0.5)
                if db("SELECT 1 FROM cp_submissions WHERE attempt_id=%s AND question_id=%s", (att['id'], TQ1)): break
            time.sleep(1.0)
            ex.click('#section-tabs-container .tab[data-section-id="1"]'); time.sleep(0.8)
            ex.click('#question-options-area input[type="radio"]'); ex.click('#save-next-btn'); time.sleep(0.5)
            ex.click('#submit-test-btn'); time.sleep(0.6)
            ex.click('button:has-text("OK")')
            for _ in range(60):
                time.sleep(0.5)
                if '/result/' in ex.evaluate('location.href'): break
            stage = db("SELECT stage FROM tcs_attempts WHERE tcs_exam_id=%s AND email=%s", (EXAM, EMAIL))
            att, answers, subs = tcs_attempt_rows()
            check('Submit closes both parts and shows the result', '/tcs/exam/' in ex.evaluate('location.href') and '/result/' in ex.evaluate('location.href') and stage and stage[0]['stage'] == 'completed' and att['status'] == 'submitted', f"{ex.evaluate('location.href')[-60:]} {stage} {att}")
            scored = db("SELECT verdict, score FROM cp_submissions WHERE attempt_id=%s AND question_id=%s", (att['id'], TQ1))
            check('the submitted program was graded', bool(scored) and scored[0]['verdict'] == 'AC' and scored[0]['score'] == 10, str(scored))
            try: ex.close()
            except Exception: pass
            rows_before = len(log_status(fx['tcs_key']))
            r = pg.request.get(f"{USER}/tcs/exam/{EXAM}/start/{CODE}/{U}")
            check('starting the exam again only shows the result', '/result/' in r.url and len(log_status(fx['tcs_key'])) == rows_before, f'{r.url[-60:]} rows {rows_before} -> {len(log_status(fx["tcs_key"]))}')
            r = pg.request.post(f"{USER}/test-login/{APT}", form={'test_key': fx['tcs_key']}, headers={'X-Requested-With': 'XMLHttpRequest'})
            check('its aptitude part cannot be started on its own either', r.status == 403, f'{r.status} {r.text()[:80]}')
            r = pg.request.get(f"{USER}/coding/test/{tcs_coding['slug']}/start/{CODE}/{U}")
            check('its coding part cannot be started on its own either', r.status == 403 and 'already' in r.text().lower(), f'{r.status}')
            go(f"{USER}/tcs/{CODE}/{U}/{fx['tcs_sid']}"); time.sleep(1.5)
            check('the TCS list shows it under results, with no Start button', pg.locator('#testGrid .test-card a.btn-action').count() == 0 and pg.locator('#resultsList .report-card').count() == 1)

        if want('coding'):
            print('\n== coding test: palette, refresh, restart, no retake ==')
            def launch_coding():
                go(f"{USER}/coding/test/{slug}/lobby/{CODE}/{U}"); time.sleep(1.0)
                for _ in range(40):
                    time.sleep(0.5)
                    if not pg.locator('#btnStart').is_disabled(): break
                pg.click('#startLink')
                pg.wait_for_url('**/coding/attempt/**', timeout=25000)
                pg.locator('#code-editor textarea').wait_for(state='visible', timeout=25000); time.sleep(1.5)

            nav = lambda qid: pg.evaluate(f"(document.querySelector('.qnav-btn[data-qid=\"{qid}\"]') || {{className: 'missing'}}).className")
            sub_count = lambda: pg.locator('#submitted-count').inner_text()
            go(f"{USER}/coding/{CODE}/{U}?section_id={fx['code_sid']}"); time.sleep(1.5)
            href = pg.locator('#testGrid .test-card a.btn-action').first.get_attribute('href') or ''
            check('the coding list leads to the lobby', f'/coding/test/{slug}/lobby' in href, href)
            launch_coding()
            att = db("SELECT id, status FROM cp_attempts WHERE test_id=%s AND user_id=%s", (T, uid))[0]
            check('Start opens the editor in full screen', pg.evaluate('!!document.fullscreenElement') and '/question/' in pg.url, pg.url[-50:])
            pg.locator('#code-editor textarea').fill('print(1)\n'); time.sleep(3.0)
            check('typing and autosave do not mark the question as done', 'is-attempted' not in nav(CQ1) and sub_count() == '0', f'{nav(CQ1)} count={sub_count()}')
            pg.click('#btn-revisit'); time.sleep(0.5)
            check('Revisit Later marks the question for review', 'is-review' in nav(CQ1), nav(CQ1))
            pg.click('#btn-submit'); time.sleep(0.5)
            pg.click('.modal-backdrop .btn-primary')
            for _ in range(80):
                time.sleep(0.5)
                if db("SELECT 1 FROM cp_submissions WHERE attempt_id=%s AND question_id=%s", (att['id'], CQ1)): break
            time.sleep(1.2)
            check('Submit Code marks it as done and counts it', 'is-attempted' in nav(CQ1) and sub_count() == '1', f'{nav(CQ1)} count={sub_count()}')
            pg.reload(); time.sleep(2.0)
            body = pg.inner_text('body')
            check('refreshing the editor page ends the sitting instead of restoring it', '/terminated' in pg.url and 'Start Test Again' in body and pg.locator('#code-editor').count() == 0, pg.url[-50:])
            check('that page says the answers are not kept', 'starts again from the beginning' in body)
            r = pg.request.get(f"{USER}/coding/attempt/{att['id']}/question/{CQ1}", max_redirects=0)
            check('the old question address no longer opens the editor', r.status in (301, 302) and '/terminated' in (r.headers.get('location') or ''), f"{r.status} {r.headers.get('location')}")
            restart = pg.locator('#tmResume').get_attribute('href') or ''
            check('Start Test Again leads back to the lobby', f'/coding/test/{slug}/lobby' in restart, restart)
            launch_coding()
            rows = (db("SELECT COUNT(*) n FROM cp_answers WHERE attempt_id=%s", (att['id'],))[0]['n'], db("SELECT COUNT(*) n FROM cp_submissions WHERE attempt_id=%s", (att['id'],))[0]['n'])
            code = pg.locator('#code-editor textarea').input_value()
            check('the new sitting is empty: no saved code, no submissions, the full time again',
                  rows == (0, 0) and 'print(0)' in code and 'print(1)' not in code and db("SELECT elapsed_seconds e FROM cp_attempts WHERE id=%s", (att['id'],))[0]['e'] == 0, f'{rows} {code!r}')
            check('its palette is new: nothing done, nothing marked for review', 'is-attempted' not in nav(CQ1) and 'is-review' not in nav(CQ1) and sub_count() == '0', f'{nav(CQ1)} count={sub_count()}')
            pg.click('#btn-finish'); time.sleep(1.5)
            summary = pg.locator('#cfin-overlay').inner_text()
            check('Finish Test shows what was submitted', 'Submitted: 0' in re.sub(r'\s+', ' ', summary) and 'Not submitted: 2' in re.sub(r'\s+', ' ', summary), re.sub(r'\s+', ' ', summary)[:160])
            pg.click('#cfin-final'); time.sleep(4.0)
            status = db("SELECT status FROM cp_attempts WHERE id=%s", (att['id'],))[0]['status']
            check('Finish Test submits the test', status == 'submitted', f'{status} {pg.url[-50:]}')
            r = pg.request.get(f"{USER}/coding/test/{slug}/lobby/{CODE}/{U}")
            r2 = pg.request.get(f"{USER}/coding/test/{slug}/start/{CODE}/{U}")
            check('after that the lobby and the start address both refuse a second attempt', r.status == 403 and r2.status == 403 and db("SELECT status FROM cp_attempts WHERE id=%s", (att['id'],))[0]['status'] == 'submitted', f'{r.status} {r2.status}')
            go(f"{USER}/coding/{CODE}/{U}?section_id={fx['code_sid']}"); time.sleep(1.5)
            check('the coding list shows it under results, with no Start button', pg.locator('#testGrid .test-card a.btn-action').count() == 0 and pg.locator('#resultsList .report-card').count() == 1)

        check('no JavaScript errors on the student pages', not errs, str(errs)[:300])
        b.close()

    if want('comm'):
        print('\n== communication test starts clean ==')
        u = student_session()
        db("INSERT INTO comm_attempt_details (email, test_key, question_id, section_name, selected_option, is_submitted, created_at) VALUES (%s,%s,1,'SELFTEST','A',1,NOW())", (EMAIL, fx['comm_key']))
        r = u.get(f"{USER}/Communication/assessment_system_info/{fx['comm_key']}/{CODE}/{U}", timeout=30)
        left = db("SELECT COUNT(*) n FROM comm_attempt_details WHERE email=%s AND test_key=%s", (EMAIL, fx['comm_key']))[0]['n']
        check('opening the communication test clears answers from an earlier sitting', '/assessment_lobby/' in r.url and left == 0, f'{r.url[-60:]} left={left}')
finally:
    cleanup()
    selftest_mocktest.remove(db)
    left = db("SELECT COUNT(*) n FROM cp_attempts a JOIN auth u ON u.id = a.user_id WHERE u.email LIKE 'selftest.%%'")[0]['n'] + \
        db("SELECT COUNT(*) n FROM user_test_log WHERE email LIKE 'selftest.%%'")[0]['n']
    check('the SELFTEST rows are removed', left == 0, f'left={left}')

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
