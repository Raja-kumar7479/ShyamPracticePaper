import io, csv, os, re, sys, time, threading
from pathlib import Path
import mysql.connector, requests
from urllib3.util.retry import Retry
from dotenv import dotenv_values
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
ADMIN = 'http://127.0.0.1:5001'
ADMIN_EMAIL, ADMIN_PASSWORD = 'rajakumarvijeta7087@gmail.com', 'Raja@7479'
sys.path.insert(0, f'{ROOT}/scripts/checks')
import selftest_mocktest
v = dotenv_values(f'{ROOT}/user_app/.env')
WORK = Path(f'{ROOT}/scripts/checks/__pycache__/coding_files'); WORK.mkdir(parents=True, exist_ok=True)


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


def clean_practice():
    for r in db("SELECT id FROM pcp_questions WHERE title LIKE 'SELFTEST%%' OR subject = 'SELFTEST'"):
        for t in ('pcp_testcases', 'pcp_templates', 'pcp_submissions', 'pcp_bookmarks', 'pcp_question_companies', 'pcp_editorials'):
            db(f"DELETE FROM {t} WHERE question_id=%s", (r['id'],))
        db("DELETE FROM pcp_questions WHERE id=%s", (r['id'],))
    db("DELETE FROM pcp_companies WHERE name LIKE 'SELFTEST%%'")


def snapshot():
    return str(db("SELECT COUNT(*) n, COALESCE(MAX(id),0) m FROM pcp_questions WHERE title NOT LIKE 'SELFTEST%%'")) + \
           str(db("SELECT COUNT(*) n FROM cp_questions WHERE title NOT LIKE 'SELFTEST%%' AND title <> 'Two Sum'"))


before = snapshot()
clean_practice()
fx = selftest_mocktest.setup(db)
s = requests.Session()
s.mount('http://', requests.adapters.HTTPAdapter(max_retries=Retry(total=4, connect=4, read=4, backoff_factor=1.5, allowed_methods=False)))
H = {}
api = lambda m, u, **k: getattr(s, m)(ADMIN + u, headers=dict(H, **k.pop('headers', {})), timeout=60, **k)


def sheet(hdr, sample, **over):
    row = dict(zip(hdr, sample)); row.update(over)
    buf = io.StringIO(); w = csv.writer(buf); w.writerow(hdr); w.writerow([row[h] for h in hdr])
    return buf.getvalue().encode()


made_images = []
try:
    tok = re.search(r'name="csrf-token"[^>]*content="([^"]+)"', s.get(f'{ADMIN}/admin_login').text).group(1)
    s.post(f'{ADMIN}/admin_login', data={'email': ADMIN_EMAIL, '_csrf_token': tok})
    s.post(f'{ADMIN}/admin_login', data={'password': ADMIN_PASSWORD, '_csrf_token': tok})
    H.update({'X-CSRFToken': re.search(r'name="csrf-token"[^>]*content="([^"]+)"', s.get(f'{ADMIN}/manage-tests').text).group(1), 'Accept': 'application/json'})

    print('== test coding editor: limits and languages ==')
    D = fx['coding_id']; T = api('get', f'/api/coding-panel/{D}').json()['test']['id']
    sec = api('post', f'/api/coding-panel/{D}/sections', json={'title': 'SELFTEST coding', 'section_type': 'coding', 'duration_min': 20}).json()['section_id']
    base = {'title': 'SELFTEST q', 'statement_html': 'Print 1', 'difficulty': 'Easy', 'marks': 10, 'allowed_languages': ['python'], 'time_limit_sec': 5,
            'testcases': [{'input_text': '', 'expected_output': '1'}]}
    r = api('post', f'/api/coding-panel/sections/{sec}/questions', json=dict(base, memory_limit='abc'))
    check('memory limit "abc" is refused with a clear message', r.status_code == 400 and 'unit' in r.text, r.text[:90])
    r = api('post', f'/api/coding-panel/sections/{sec}/questions', json=dict(base, memory_limit='8m'))
    check('memory limit below 16m is refused', r.status_code == 400 and 'between' in r.text, r.text[:90])
    r = api('post', f'/api/coding-panel/sections/{sec}/questions', json=dict(base, memory_limit=' 1G '))
    check('memory limit "1G" is accepted and stored in Docker form', r.status_code == 200 and db("SELECT memory_limit FROM cp_questions WHERE title='SELFTEST q'")[0]['memory_limit'] == '1g')
    r = api('post', f'/api/coding-panel/sections/{sec}/questions', json=dict(base, title='SELFTEST mod', difficulty='Moderate'))
    check('"Moderate" is accepted as Medium in the test editor', r.status_code == 200 and db("SELECT difficulty FROM cp_questions WHERE title='SELFTEST mod'")[0]['difficulty'] == 'Medium')
    r = api('post', f'/api/coding-panel/sections/{sec}/questions', json=dict(base, title='SELFTEST  q ', statement_html='<p>Print   1</p>'))
    check('the same question again (spacing/tags differ) is refused as a duplicate', r.status_code == 409 and 'already in this section' in r.text, r.text[:90])
    qid = db("SELECT id FROM cp_questions WHERE title='SELFTEST q'")[0]['id']
    r = api('put', f'/api/coding-panel/questions/{qid}', json=dict(base, marks=12))
    check('re-saving a question with its own title is allowed', r.status_code == 200 and db("SELECT marks FROM cp_questions WHERE id=%s", (qid,))[0]['marks'] == 12)
    api('put', f'/api/coding-panel/{D}/languages', json={'languages': ['python', 'java']})
    r = api('post', f'/api/coding-panel/sections/{sec}/questions', json=dict(base, title='SELFTEST js', allowed_languages=['javascript']))
    check('a question outside the test languages is refused by hand', r.status_code == 400 and 'allows only python, java' in r.text, r.text[:100])
    tpl = api('get', f'/api/coding-panel/sections/{sec}/bulk/template').text
    rows = list(csv.reader(io.StringIO(tpl))); hdr, sample = rows[0], rows[1]
    r = api('post', f'/api/coding-panel/sections/{sec}/bulk/upload', files={'file': ('t.csv', sheet(hdr, sample, title='SELFTEST js sheet', languages='javascript'))})
    check('...and by sheet, naming the row', r.status_code == 400 and 'Row 2' in r.text and 'allows only' in r.text, r.text[:110])
    r = api('post', f'/api/coding-panel/sections/{sec}/bulk/upload', files={'file': ('t.csv', sheet(hdr, sample, title='SELFTEST sheet', languages='python'))})
    check('a valid sheet row imports', r.ok and r.json()['imported'] == 1, r.text[:80])
    r = api('post', f'/api/coding-panel/sections/{sec}/bulk/upload', files={'file': ('t.csv', sheet(hdr, sample, title='SELFTEST sheet', languages='python'))})
    check('the same sheet again adds nothing and says why', r.ok and r.json()['imported'] == 0 and r.json()['skipped'] and db("SELECT COUNT(*) n FROM cp_questions WHERE title='SELFTEST sheet'")[0]['n'] == 1, r.text[:110])
    r = api('post', f'/api/coding-panel/sections/{sec}/bulk/upload', files={'file': ('t.csv', sheet(hdr, sample, title='SELFTEST bs', languages='python', statement='Use \\\\n for a newline, then\\nnext line'))})
    st = db("SELECT statement_html FROM cp_questions WHERE title='SELFTEST bs'")[0]['statement_html']
    check('sheet cells: \\n is a line break, \\\\n stays as the two characters', st == 'Use \\n for a newline, then\nnext line', repr(st))

    print('\n== test coding editor: student work is protected ==')
    uid = db("SELECT id FROM auth WHERE email=%s", (fx['student']['email'],))[0]['id']
    db("INSERT INTO cp_attempts (test_id, user_id, status) VALUES (%s, %s, 'submitted')", (T, uid))
    att = db("SELECT id FROM cp_attempts WHERE test_id=%s AND user_id=%s", (T, uid))[0]['id']
    verdict = re.findall(r"'([^']+)'", db("SHOW COLUMNS FROM cp_submissions LIKE 'verdict'")[0]['Type'])[0]
    db("INSERT INTO cp_submissions (attempt_id, question_id, language, code, verdict, passed, total, score) VALUES (%s,%s,'python','print(1)',%s,1,1,10)", (att, qid, verdict))
    r = api('delete', f'/api/coding-panel/questions/{qid}')
    check('deleting a question with a student submission is refused', r.status_code == 409 and '1 student submission' in r.text and db("SELECT 1 FROM cp_questions WHERE id=%s", (qid,)), r.text[:100])
    r = api('delete', f'/api/coding-panel/sections/{sec}')
    check('deleting its section is refused too', r.status_code == 409 and db("SELECT 1 FROM cp_sections WHERE id=%s", (sec,)))
    db("DELETE FROM cp_submissions WHERE attempt_id=%s", (att,))
    r = api('delete', f'/api/coding-panel/questions/{qid}')
    check('without student work the delete goes through', r.ok and not db("SELECT 1 FROM cp_questions WHERE id=%s", (qid,)))

    print('\n== published TCS exam never left empty ==')
    tcs = {'test_id': fx['tcs_sid'], 'test_key': fx['tcs_key'], 'subject_title': 'SELFTEST TCS', 'subject_subtitle': 'x', 'total_questions': 1, 'total_marks': 1, 'total_duration_minutes': 10, 'show_calculator': 0, 'access_label': 'free'}
    api('post', '/api/test-descriptions/add', json=tcs)
    TCS = db("SELECT id FROM test_description WHERE test_key=%s", (fx['tcs_key'],))[0]['id']
    db("INSERT INTO test_questions (test_id, test_key, test_description_id, section_id, section_name, question_number, question_type, question_text, option_a, option_b, correct_option, correct_marks, negative_marks, question_level)"
       " VALUES (%s,%s,%s,'1','Apt',1,'MCQ','<p>SELFTEST</p>','a','b','A',1,0,'Easy')", (fx['tcs_sid'], fx['tcs_key'], TCS))
    tsec = api('post', f'/api/coding-panel/{TCS}/sections', json={'title': 'Coding', 'section_type': 'coding', 'duration_min': 20}).json()['section_id']
    api('post', f'/api/coding-panel/sections/{tsec}/questions', json=dict(base, title='SELFTEST only problem'))
    api('post', f'/api/test-descriptions/{TCS}/tcs-publish', json={'published': True})
    cq = db("SELECT id FROM cp_questions WHERE title='SELFTEST only problem'")[0]['id']
    r = api('delete', f'/api/coding-panel/questions/{cq}')
    check('deleting the last coding problem unpublishes the exam and says so', r.ok and 'unpublished' in r.json().get('message', '')
          and db("SELECT is_published FROM tcs_exams WHERE aptitude_test_key=%s", (fx['tcs_key'],))[0]['is_published'] == 0, r.text[:120])

    print('\n== practice coding editor ==')
    P = '/api/practice-coding/questions'
    pb = {'title': 'SELFTEST practice', 'statement_html': 'x', 'difficulty': 'Medium', 'subject': 'SELFTEST', 'allowed_languages': ['python'],
          'testcases': [{'input_text': '', 'expected_output': '1'}], 'companies': ['SELFTEST Corp', ' SELFTEST Corp', 'SELFTEST Inc'], 'position': 7}
    r = api('post', P, json=dict(pb, memory_limit='abc'))
    check('practice: memory limit "abc" refused', r.status_code == 400 and 'unit' in r.text, r.text[:80])
    r = api('post', P, json=dict(pb, memory_limit='256m'))
    row = db("SELECT id, slug, difficulty, position FROM pcp_questions WHERE title='SELFTEST practice'")
    check('practice: "Medium" is accepted (stored as Moderate), companies and order are stored', r.status_code == 200 and row and row[0]['difficulty'] == 'Moderate' and row[0]['position'] == 7
          and db("SELECT COUNT(*) n FROM pcp_question_companies WHERE question_id=%s", (row[0]['id'],))[0]['n'] == 2, str(row))
    pid, slug = row[0]['id'], row[0]['slug']
    r = api('post', P, json=dict(pb, memory_limit='256m', title=' SELFTEST practice ', statement_html='<b>x</b>'))
    check('practice: an exact duplicate is refused naming the existing one', r.status_code == 409 and f'#{pid}' in r.text, r.text[:100])
    r = api('put', f'{P}/{pid}', json=dict(pb, title='SELFTEST practice renamed', memory_limit='256m'))
    check('practice: renaming keeps the student URL slug', r.ok and db("SELECT slug FROM pcp_questions WHERE id=%s", (pid,))[0]['slug'] == slug)
    api('delete', f'{P}/{pid}')
    r = api('post', P, json=dict(pb, title='SELFTEST practice renamed', memory_limit='256m'))
    check('practice: re-adding a removed question is refused and points to Restore', r.status_code == 409 and 'restore' in r.text.lower(), r.text[:100])
    api('put', f'{P}/{pid}/restore')
    tpl = api('get', '/api/practice-coding/bulk/template').text
    rows = list(csv.reader(io.StringIO(tpl))); hdr, sample = rows[0], rows[1]
    r1 = api('post', '/api/practice-coding/bulk/upload', files={'file': ('t.csv', sheet(hdr, sample, title='SELFTEST sheet p', difficulty='Medium'))})
    r2 = api('post', '/api/practice-coding/bulk/upload', files={'file': ('t.csv', sheet(hdr, sample, title='SELFTEST sheet p', difficulty='Medium'))})
    check('practice sheet: Medium accepted, second upload adds nothing', r1.ok and r1.json()['imported'] == 1 and r2.ok and r2.json()['imported'] == 0
          and db("SELECT COUNT(*) n FROM pcp_questions WHERE title='SELFTEST sheet p'")[0]['n'] == 1, f'{r1.text[:60]} | {r2.text[:80]}')

    print('\n== the editors in a browser ==')
    D2 = fx['coding_id']
    wsec = api('post', f'/api/coding-panel/{D2}/sections', json={'title': 'SELFTEST web', 'section_type': 'web', 'duration_min': 20}).json()['section_id']
    api('post', f'/api/coding-panel/sections/{wsec}/questions', json={'title': 'SELFTEST web q', 'statement_html': 'Make a heading', 'assertions': [{'kind': 'element_exists', 'selector': 'h1'}]})
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome', headless=True); ctx = b.new_context(viewport={'width': 1440, 'height': 1000}); ctx.set_default_timeout(15000)
        pg = ctx.new_page(); errs, natives = [], []
        pg.on('pageerror', lambda e: errs.append(str(e)[:160])); pg.on('dialog', lambda d: (natives.append(d.message[:40]), d.accept()))
        pg.goto(f'{ADMIN}/admin_login'); pg.fill('input[name="email"]', ADMIN_EMAIL); pg.keyboard.press('Enter'); time.sleep(1.2)
        pg.fill('input[name="password"]', ADMIN_PASSWORD); pg.keyboard.press('Enter'); time.sleep(1.5)
        pg.goto(f'{ADMIN}/manage-tests'); time.sleep(1.5); pg.evaluate("sessionStorage.removeItem('mtPickerPlace')"); pg.reload(); time.sleep(1.8)
        pg.click(f".mt-tcard--group[data-group=\"{fx['student']['name']}\"]"); time.sleep(0.5); pg.click(f".mt-tcard--course[data-course=\"{fx['code']}\"]"); time.sleep(0.5)
        pg.click(f".mt-tcard[data-id=\"{fx['code_sid']}\"]"); time.sleep(1.5); pg.locator('.load-questions-btn').first.click(); time.sleep(1.5)
        def approve():
            time.sleep(0.6)
            if pg.evaluate("(() => { const d = document.querySelector('.acf'); return !!d && !d.hidden; })()"): pg.click('.acf [data-acf="confirm"]')
            time.sleep(1.5)
        pg.select_option('#cdpTargetSection', str(wsec)); time.sleep(0.4); pg.select_option('#cdpViewSection', str(wsec)); time.sleep(1.0)
        pg.click('#cdpQuestionsList [data-edit-q]'); time.sleep(1.2)
        check('editing a Web question shows exactly its stored checks', pg.locator('#cdpAssertions .cdp-row').count() == 1 and pg.locator('#cdpAssertions .cdp-as-sel').first.input_value() == 'h1')
        pg.fill('#cdpTitle', 'SELFTEST web q edited'); pg.click('#cdpSaveBtn'); approve()
        check('...and saving that edit works', db("SELECT title FROM cp_questions WHERE section_id=%s", (wsec,))[0]['title'] == 'SELFTEST web q edited')
        check('the memory field explains the format', 'm' in (pg.get_attribute('#cdpMemory', 'placeholder') or ''))
        pg.goto(f'{ADMIN}/manage-practice-coding'); time.sleep(1.8)
        pg.fill('#pcqTitle', 'SELFTEST ui p'); pg.fill('#pcqSubject', 'SELFTEST'); pg.fill('#pcqStatement', 'x'); pg.locator('#pcqTestcases .pcq-tc-out').first.fill('1')
        pg.fill('#pcqCompanies', 'SELFTEST A, SELFTEST B'); pg.fill('#pcqPosition', '3'); pg.click('#pcqSaveBtn'); time.sleep(1.6)
        q = db("SELECT id, position FROM pcp_questions WHERE title='SELFTEST ui p'")
        check('practice page: Companies and Order typed in the form are saved', q and q[0]['position'] == 3 and db("SELECT COUNT(*) n FROM pcp_question_companies WHERE question_id=%s", (q[0]['id'],))[0]['n'] == 2, str(q))
        pg.select_option('#pcqFilterSubject', 'SELFTEST'); time.sleep(1.0); pg.click('#pcqList [data-edit-q]'); time.sleep(1.2)
        check('editing shows them again', pg.input_value('#pcqCompanies') == 'SELFTEST A, SELFTEST B' and pg.input_value('#pcqPosition') == '3', pg.input_value('#pcqCompanies'))
        pg.fill('#pcqPosition', '4'); pg.click('#pcqSaveBtn'); time.sleep(0.7)
        check('updating a practice question asks for approval', pg.evaluate("(() => { const d = document.querySelector('.acf'); return !!d && !d.hidden; })()"))
        approve()
        check('...and saves after approval', db("SELECT position FROM pcp_questions WHERE id=%s", (q[0]['id'],))[0]['position'] == 4)
        pg.select_option('#pcqFilterSubject', 'SELFTEST'); time.sleep(1.0); pg.click('#pcqList [data-tier-q]'); time.sleep(0.6)
        check('the Free/Paid flip asks first', 'Make this question Paid' in (pg.locator('.acf-box').inner_text() if pg.locator('.acf-box').count() else ''))
        pg.click('.acf [data-acf="cancel"]'); time.sleep(0.4)
        pg.click('#pcqList [data-del-q]'); time.sleep(0.6)
        check('remove uses the approval box, not a browser pop-up', pg.locator('.acf-box').count() and 'Remove' in pg.locator('.acf-box').inner_text() and not natives)
        approve()
        check('...and soft-removes after approval', db("SELECT is_active FROM pcp_questions WHERE id=%s", (q[0]['id'],))[0]['is_active'] == 0)
        check('no script errors', not errs, '; '.join(errs)[:120])
        b.close()

    print('\n== judge gate ==')
    os.chdir(f'{ROOT}/user_app'); sys.path.insert(0, f'{ROOT}/user_app')
    from routes.exam_platform.placement_exam_portal.coding_portal.services import code_executor, judge_gate
    from app import app
    g = judge_gate.JudgeGate(max_parallel=2, max_waiting=2, queue_wait=1)
    code_executor.gate = g
    peak = {'running': 0}; lock = threading.Lock()
    def fake_now(code, language, testcases, *a, **k):
        with lock: peak['running'] = max(peak['running'], g.running)
        time.sleep(0.6)
        return code_executor.RunResult(compiled=True, cases=[code_executor.CaseResult('PASS', '1', '', 0.1)])
    code_executor._execute_now = fake_now
    outs = []
    def worker(): outs.append(code_executor.execute('print(1)', 'python', [{'input_text': '', 'expected_output': '1'}]))
    ts = [threading.Thread(target=worker) for _ in range(6)]
    [t.start() for t in ts]; [t.join() for t in ts]
    ran = sum(1 for o in outs if o.cases); busy = sum(1 for o in outs if o.error and 'busy' in o.error)
    check('never more containers than the limit (2) run at once', peak['running'] <= 2, str(peak))
    check('6 simultaneous runs: 2 run, 2 wait and run, 2 get "judge is busy" instead of piling up', ran == 4 and busy == 2, f'ran={ran} busy={busy}')
    st = g.stats()
    check('the gate keeps counters for monitoring', st['completed'] == 4 and st['rejected_busy'] == 2 and st['peak_running'] == 2, str(st))
    g2 = judge_gate.JudgeGate(max_parallel=4, max_waiting=4, queue_wait=1); code_executor.gate = g2
    outs = []
    with app.test_request_context('/'):
        from flask import session
        session['user_email'] = 'selftest.student@example.com'
        def w2():
            with app.test_request_context('/'):
                from flask import session as ss
                ss['user_email'] = 'selftest.student@example.com'
                outs.append(code_executor.execute('print(1)', 'python', [{'input_text': '', 'expected_output': '1'}]))
        ts = [threading.Thread(target=w2) for _ in range(2)]
        [t.start() for t in ts]; [t.join() for t in ts]
    check('the same student cannot run twice at the same time', sum(1 for o in outs if o.error and 'previous run' in o.error) == 1 and sum(1 for o in outs if o.cases) == 1, str([o.error for o in outs]))
    out = code_executor.run_custom_input('x', 'python', '1')
    check('a busy answer on custom input is reported, not lost', 'output' in out and 'error' in out)
    client = app.test_client()
    r = client.get('/practice-coding/api/judge/health')
    j = r.get_json() or {}
    check('the health endpoint reports the live gate (limits and counters)', r.status_code == 200 and j.get('max_parallel', 0) >= 1 and j.get('healthy') is True
          and {'running', 'waiting', 'peak_running', 'rejected_busy', 'avg_wait_seconds'} <= set(j), r.get_data(as_text=True)[:100])
finally:
    db("DELETE FROM cp_attempts WHERE test_id IN (SELECT id FROM cp_tests WHERE test_key IN (%s, %s))", (fx['coding_key'], fx['tcs_key'] + '_code'))
    selftest_mocktest.remove(db)
    clean_practice()
    left = db("SELECT COUNT(*) n FROM cp_questions WHERE title LIKE 'SELFTEST%%'")[0]['n'] + db("SELECT COUNT(*) n FROM pcp_questions WHERE title LIKE 'SELFTEST%%'")[0]['n']
    check('SELFTEST rows removed', left == 0, str(left))
    check('your own questions are untouched', snapshot() == before)

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
