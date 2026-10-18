import io, json, os, re, sys, time
from pathlib import Path
import mysql.connector, requests
from urllib3.util.retry import Retry
from dotenv import dotenv_values
from openpyxl import Workbook
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
ADMIN = 'http://127.0.0.1:5001'
ADMIN_EMAIL, ADMIN_PASSWORD = 'rajakumarvijeta7087@gmail.com', 'Raja@7479'
sys.path.insert(0, f'{ROOT}/scripts/checks')
import selftest_mocktest
SHOTS = f'{ROOT}/scripts/checks/shots'
SHOT = len(sys.argv) > 1
WORK = Path(f'{ROOT}/scripts/checks/__pycache__/mocktest_files')
WORK.mkdir(parents=True, exist_ok=True)
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


def snapshot():
    return json.dumps({
        'td': db("SELECT id, test_key, subject_title, total_questions FROM test_description WHERE test_key NOT LIKE 'free_selftest%%' AND subject_title NOT LIKE 'SELFTEST%%' ORDER BY id"),
        'tq': db("SELECT COUNT(*) n FROM test_questions WHERE test_key NOT LIKE 'free_selftest%%' AND test_key IN (SELECT test_key FROM test_description WHERE subject_title NOT LIKE 'SELFTEST%%')"),
        'cd': db("SELECT id, test_key, subject_title FROM comm_description WHERE test_key NOT LIKE 'free_selftest%%' ORDER BY id"),
        'cq': db("SELECT COUNT(*) n FROM comm_questions WHERE test_key NOT LIKE 'free_selftest%%'"),
        'cs': db("SELECT COUNT(*) n FROM comm_sections WHERE test_key NOT LIKE 'free_selftest%%'"),
        'cp': db("SELECT COUNT(*) n FROM cp_questions"),
    }, default=str)


def xlsx(path, header, rows):
    wb = Workbook(); ws = wb.active; ws.append(header)
    for r in rows: ws.append(r)
    wb.save(path); return str(path)


def question_image(path, label):
    im = Image.new('RGB', (900, 700), 'white'); d = ImageDraw.Draw(im)
    d.rectangle([40, 40, 860, 660], outline='white')
    d.text((80, 80), f'{label}: What is 2 + 2 ?', fill='black')
    for i, t in enumerate(['(A) 3', '(B) 4', '(C) 5', '(D) 6']):
        d.text((100, 220 + i * 90), t, fill='black')
    im.save(path); return str(path)


def uploaded_images():
    rows = db("SELECT question_image FROM test_questions WHERE test_key LIKE 'free_selftest%%' AND question_image IS NOT NULL")
    rows += db("SELECT question_image FROM test_questions WHERE question_image IS NOT NULL AND test_key IN "
               "(SELECT test_key FROM test_description WHERE subject_title LIKE 'SELFTEST%%')")
    return {r['question_image'] for r in rows if r['question_image']}


made_images = set()
before = snapshot()
fx = selftest_mocktest.setup(db)
MOCK, COMM, CODING = fx['mock_id'], fx['comm_id'], fx['coding_id']
COLS = ['question_type', 'question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_option',
        'correct_marks', 'negative_marks', 'question_level', 'answer_text', 'answer_link']
GOOD = [['MCQ', '<p>SELFTEST capital?</p>', 'Mumbai', 'Delhi', 'Pune', 'Goa', 'b', 2, '1/3', 'Easy', '', ''],
        ['MSQ', '<p>SELFTEST primes?</p>', '2', '4', '5', '9', 'ca', 2, 0, 'Medium', '', ''],
        ['NAT', '<p>SELFTEST x+3=10</p>', '', '', '', '', '7', 1, 0, 'Tough', '', '']]
good_file = xlsx(WORK / 'good.xlsx', COLS, GOOD)
bad_file = xlsx(WORK / 'bad.xlsx', COLS, GOOD[:1] + [['MCQ', '<p>SELFTEST bad</p>', 'a', 'b', '', '', 'E', 1, 0, 'Easy', '', ''],
                                                     ['MSQ', '<p>SELFTEST bad2</p>', 'a', 'b', '', '', 'AC', 1, 0, 'Easy', '', ''],
                                                     ['NAT', '<p>SELFTEST bad3</p>', '', '', '', '', 'seven', 1, 0, 'Easy', '', '']])
browser_file = xlsx(WORK / 'browser.xlsx', COLS, [['MCQ', '<p>SELFTEST from browser</p>', 'x', 'y', 'z', 'w', 'd', 1, 0, 'Easy', '', '']])
browser_bad = xlsx(WORK / 'browser_bad.xlsx', COLS, [['MCQ', '<p>SELFTEST from browser bad</p>', 'x', 'y', '', '', 'q', 1, 0, 'Easy', '', '']])
CCOLS = ['section_name', 'question_type', 'instruction_text', 'question_text', 'media_url', 'options_title', 'option_a',
         'option_b', 'option_c', 'option_d', 'correct_option', 'recording_time_seconds', 'thinking_time_seconds',
         'word_limit', 'correct_marks', 'negative_marks', 'question_level']
comm_good = xlsx(WORK / 'comm_good.xlsx', CCOLS, [
    ['SECTION_A', 'MCQ', 'Grammar', 'SELFTEST She ___ home.', '', 'Select', 'go', 'went', 'gone', 'going', 'b', '', '', '', 2, '1/3', 'Easy'],
    ['SECTION_A', 'SPEAK', 'Read', 'SELFTEST read this aloud.', '', '', '', '', '', '', '', 45.0, '', '', 5, 0, 'Medium'],
    ['SECTION_A', 'WRITING', 'Email', 'SELFTEST write an email.', '', '', '', '', '', '', '', '', '', 150, 10, 0, 'Tough']])
comm_bad = xlsx(WORK / 'comm_bad.xlsx', CCOLS, [
    ['SECTION_A', 'MCQ', 'Grammar', 'SELFTEST ok row', '', '', 'go', 'went', '', '', 'b', '', '', '', 2, 0, 'Easy'],
    ['SECTION_A', 'MCQ', 'Grammar', 'SELFTEST bad row', '', '', 'go', '', '', '', 'b', '', '', '', 2, 0, 'Easy'],
    ['SECTION_Z', 'SPEAK', 'Read', 'SELFTEST no section', '', '', '', '', '', '', '', 45, '', '', 5, 0, 'Medium']])
img1 = question_image(WORK / 'q1.png', 'SELFTEST image one')

s = requests.Session()
s.mount('http://', requests.adapters.HTTPAdapter(max_retries=Retry(total=4, connect=4, read=4, backoff_factor=1.5, allowed_methods=False)))
H = {}


def api(method, url, **kw):
    kw.setdefault('headers', {}); kw['headers'] = dict(H, **kw['headers'])
    return getattr(s, method)(ADMIN + url, timeout=60, **kw)


def upload(url, path, extra=None):
    with open(path, 'rb') as f:
        return api('post', url, files={'csv_file': (os.path.basename(path), f)}, data=extra or {})


try:
    tok = re.search(r'name="csrf-token"[^>]*content="([^"]+)"', s.get(f'{ADMIN}/admin_login').text).group(1)
    s.post(f'{ADMIN}/admin_login', data={'email': ADMIN_EMAIL, '_csrf_token': tok})
    s.post(f'{ADMIN}/admin_login', data={'password': ADMIN_PASSWORD, '_csrf_token': tok})
    H.update({'X-CSRFToken': re.search(r'name="csrf-token"[^>]*content="([^"]+)"', s.get(f'{ADMIN}/manage-tests').text).group(1),
              'Accept': 'application/json'})
    base_form = {'test_id': fx['mock_sid'], 'test_key': fx['mock_key'], 'test_description_id': MOCK,
                 'section_id': 'SEC1', 'section_name': 'Physics'}
    count = lambda: db("SELECT COUNT(*) n FROM test_questions WHERE test_key=%s", (fx['mock_key'],))[0]['n']

    print('== competitive Excel upload ==')
    r = upload('/api/test-questions/upload-csv', bad_file, base_form)
    errs = r.json().get('errors', [])
    check('a file with bad rows is refused and nothing is saved', r.status_code == 400 and count() == 0, f'{r.status_code} {r.text[:80]}')
    check('each bad row is named (MCQ E, MSQ with an empty option, NAT not a number)',
          {e['row_number'] for e in errs} == {3, 4, 5}, str(errs)[:200])
    r = upload('/api/test-questions/upload-csv', good_file, base_form)
    check('a clean file saves every row in one go', r.status_code == 200 and count() == 3, r.text[:90])
    rows = db("SELECT question_type, correct_option, negative_marks FROM test_questions WHERE test_key=%s ORDER BY id", (fx['mock_key'],))
    check('answers are normalised (b -> B, ca -> AC) and 1/3 becomes 0.33',
          [x['correct_option'] for x in rows] == ['B', 'AC', '7'] and abs(float(rows[0]['negative_marks']) - 1 / 3) < 0.01, str(rows))

    print('\n== the same sheet again: nothing duplicated ==')
    r = upload('/api/test-questions/upload-csv', good_file, base_form)
    check('uploading the same file again adds nothing and says every row is already stored',
          r.status_code == 200 and r.json()['inserted_count'] == 0 and r.json()['skipped_count'] == 3 and count() == 3
          and 'already in this test' in r.json()['message'], r.text[:120])
    check('each skipped row says where the question already is', all('Physics Q' in sk['message'] for sk in r.json()['skipped']), str(r.json()['skipped'])[:120])
    mixed = xlsx(WORK / 'mixed.xlsx', COLS, [GOOD[0], ['MCQ', '<p>SELFTEST  capital?</p>', 'Mumbai', 'Delhi', 'Pune', 'Goa', 'b', 2, 0, 'Easy', '', ''],
                                             ['MCQ', '<p>SELFTEST brand new</p>', 'x', 'y', 'z', 'w', 'a', 1, 0, 'Easy', '', ''],
                                             ['MCQ', '<p>SELFTEST brand new</p>', 'x', 'y', 'z', 'w', 'a', 1, 0, 'Easy', '', '']])
    r = upload('/api/test-questions/upload-csv', mixed, base_form)
    j = r.json()
    check('a mixed file adds only the new question; stored ones, spacing-only variants and in-file repeats are skipped',
          r.ok and j['inserted_count'] == 1 and j['skipped_count'] == 3 and count() == 4, r.text[:140])
    check('the new one continues the numbering (Q4)', db("SELECT question_number FROM test_questions WHERE question_text='<p>SELFTEST brand new</p>'")[0]['question_number'] == 4)
    r = upload('/api/test-questions/upload-csv', xlsx(WORK / 'diff.xlsx', COLS, [['MCQ', '<p>SELFTEST capital?</p>', 'Mumbai', 'Delhi', 'Pune', 'Chennai', 'b', 2, 0, 'Easy', '', '']]), base_form)
    check('a question with one different option is a different question and is added', r.ok and r.json()['inserted_count'] == 1 and count() == 5, r.text[:100])
    db("DELETE FROM test_questions WHERE test_key=%s AND question_number IN (4, 5)", (fx['mock_key'],))

    print('\n== manual add and edit (server rules) ==')
    q = dict(base_form, question_type='MCQ', question_text='<p>SELFTEST manual</p>', option_a='<p>1</p>', option_b='<p>2</p>',
             option_c='<p><br></p>', option_d='<p><br></p>', correct_marks='2', negative_marks='0', question_level='Easy')
    r = api('post', '/api/test-questions/add', json=dict(q, correct_option='E'))
    check('an MCQ answer outside A-D is refused', r.status_code == 400 and 'one letter' in r.text, r.text[:80])
    r = api('post', '/api/test-questions/add', json=dict(q, correct_option='C'))
    check('an answer pointing at an empty option is refused', r.status_code == 400 and 'option C is empty' in r.text, r.text[:90])
    r = api('post', '/api/test-questions/add', json=dict(q, correct_option='b'))
    check('a valid manual question saves', r.status_code == 201 and count() == 4, r.text[:80])
    r = api('post', '/api/test-questions/add', json=dict(q, correct_option='a', question_text='<p> SELFTEST   MANUAL </p>'))
    check('adding the same question again by hand is refused and names where it is', r.status_code == 409 and 'Physics Q4' in r.text and count() == 4, r.text[:110])
    mid = db("SELECT id FROM test_questions WHERE question_text='<p>SELFTEST manual</p>'")[0]['id']
    r = api('put', f'/api/test-questions/update/{mid}', json={'question_type': 'MCQ', 'correct_option': 'D', 'correct_marks': '3'})
    now = db("SELECT correct_option, correct_marks FROM test_questions WHERE id=%s", (mid,))[0]
    check('an edit to an empty option is refused and changes nothing (no half save)',
          r.status_code == 400 and now['correct_option'] == 'B' and float(now['correct_marks']) == 2, f'{r.status_code} {now}')

    print('\n== sections and bulk delete ==')
    secs = api('get', f'/api/test-sections/{MOCK}').json()
    check('the sections list gives every section with its name and count',
          secs['sections'] == [{'section_id': 'SEC1', 'section_name': 'Physics', 'questions': 4, 'marks': 7.0}], str(secs)[:160])
    ids = [x['id'] for x in db("SELECT id FROM test_questions WHERE test_key=%s ORDER BY id", (fx['mock_key'],))]
    db("INSERT INTO test_attempt_details (email, test_id, test_key, question_id, attempt_number) VALUES (%s,%s,%s,%s,1)",
       (fx['student']['email'], fx['mock_sid'], fx['mock_key'], ids[0]))
    r = api('post', '/api/test-questions/bulk-delete', json={'description_id': MOCK, 'ids': ids[:2], 'dry_run': True})
    check('the delete preview counts the student answers that go with the questions',
          r.ok and r.json() == {'count': 2, 'answers': 1, 'students': 1} and count() == 4, r.text[:90])
    other = db("SELECT id FROM test_questions WHERE test_key NOT LIKE 'free_selftest%%' LIMIT 1")
    if other:
        r = api('post', '/api/test-questions/bulk-delete', json={'description_id': MOCK, 'ids': [ids[0], other[0]['id']]})
        check('a question from another test is refused and nothing is deleted', r.status_code == 409 and count() == 4, r.text[:90])
    r = api('post', '/api/test-questions/bulk-delete', json={'description_id': MOCK, 'ids': ids[:2]})
    check('bulk delete removes exactly the chosen questions', r.ok and count() == 2 and r.json()['deleted'] == 2, r.text[:80])
    nums = lambda: [x['question_number'] for x in db("SELECT question_number FROM test_questions WHERE test_key=%s AND section_id='SEC1' ORDER BY question_number, id", (fx['mock_key'],))]
    check('the remaining questions are renumbered with no gap (were 3,4 -> now 1,2)', nums() == [1, 2], str(nums()))
    r = api('post', '/api/test-questions/add', json=dict(q, question_text='<p>SELFTEST after delete</p>', correct_option='b'))
    check('a question added afterwards continues the numbering (3), not 1 or the database id', r.status_code == 201 and nums() == [1, 2, 3], str(nums()))
    newest = db("SELECT id FROM test_questions WHERE question_text='<p>SELFTEST after delete</p>'")[0]['id']
    r = api('delete', f'/api/test-questions/delete/{ids[2]}')
    check('a single delete renumbers too (deleted #1 -> the others become 1,2)', r.ok and nums() == [1, 2]
          and db("SELECT question_number FROM test_questions WHERE id=%s", (newest,))[0]['question_number'] == 2, str(nums()))
    anon = requests.post(ADMIN + '/api/test-questions/bulk-delete', json={'description_id': MOCK, 'ids': ids[2:]}, headers={'Accept': 'application/json'})
    check('bulk delete needs a signed-in admin with the CSRF token', anon.status_code in (400, 401, 403) and count() == 2, str(anon.status_code))

    print('\n== the database refuses duplicate numbers; bulk marks, move and rename ==')
    keys = {r['Key_name'] for r in db("SHOW INDEX FROM test_questions")} | {r['Key_name'] for r in db("SHOW INDEX FROM comm_questions")}
    check('unique (test, section, number) keys exist on both question tables', {'uq_tq_section_number', 'uq_cq_section_number'} <= keys, str(sorted(keys))[:120])
    dup_refused = False
    try:
        db("INSERT INTO test_questions (test_id, test_key, test_description_id, section_id, section_name, question_number, question_type, question_text, correct_option, correct_marks, negative_marks, question_level)"
           " VALUES (%s,%s,%s,'SEC1','Physics',1,'MCQ','<p>SELFTEST dup</p>','A',1,0,'Easy')", (fx['mock_sid'], fx['mock_key'], MOCK))
    except mysql.connector.Error as e:
        dup_refused = e.errno == 1062
    check('a second Q1 in the same section is refused by the database itself', dup_refused and not db("SELECT 1 FROM test_questions WHERE question_text='<p>SELFTEST dup</p>'"))
    ids = [x['id'] for x in db("SELECT id FROM test_questions WHERE test_key=%s AND section_id='SEC1' ORDER BY question_number", (fx['mock_key'],))]
    r = api('post', '/api/test-questions/bulk-marks', json={'description_id': MOCK, 'ids': ids, 'correct_marks': '', 'negative_marks': ''})
    check('set marks with both boxes empty is refused', r.status_code == 400, r.text[:70])
    r = api('post', '/api/test-questions/bulk-marks', json={'description_id': MOCK, 'ids': ids, 'correct_marks': '4', 'negative_marks': '2/3'})
    got = db("SELECT correct_marks, negative_marks FROM test_questions WHERE id IN (%s,%s)", tuple(ids))
    check('set marks updates only the chosen questions (+4 / -0.67)', r.ok and all(float(g['correct_marks']) == 4 and abs(float(g['negative_marks']) - 2 / 3) < 0.01 for g in got), str(got))
    r = api('post', '/api/test-questions/bulk-move', json={'description_id': MOCK, 'ids': ids[:1], 'section_id': 'SEC9', 'section_name': 'Chemistry'})
    sec9 = db("SELECT question_number FROM test_questions WHERE test_key=%s AND section_id='SEC9'", (fx['mock_key'],))
    check('move to a new section creates it and numbers from 1; the old section renumbers', r.ok and [x['question_number'] for x in sec9] == [1] and nums() == [1], r.text[:90])
    r = api('post', '/api/test-questions/bulk-move', json={'description_id': MOCK, 'ids': ids[1:], 'section_id': 'sec9', 'section_name': 'ignored'})
    sec9 = db("SELECT question_number, section_name FROM test_questions WHERE test_key=%s AND section_id='SEC9' ORDER BY question_number", (fx['mock_key'],))
    check('move to an existing section appends after its last number (case-insensitive ID, existing name kept)',
          r.ok and [x['question_number'] for x in sec9] == [1, 2] and sec9[1]['section_name'] == 'Chemistry' and nums() == [], str(sec9))
    r = api('post', '/api/test-questions/bulk-move', json={'description_id': MOCK, 'ids': ids, 'section_id': 'SEC9', 'section_name': 'Chemistry'})
    check('moving questions into the section they are already in is refused', r.status_code == 400, r.text[:70])
    r = api('post', f'/api/test-sections/{MOCK}/rename', json={'section_id': 'SEC9', 'section_name': 'Chemistry & Physics'})
    names = {x['section_name'] for x in db("SELECT section_name FROM test_questions WHERE test_key=%s AND section_id='SEC9'", (fx['mock_key'],))}
    check('rename changes the name on every question of that section, the ID stays SEC9', r.ok and names == {'Chemistry & Physics'}, r.text[:80])
    api('post', '/api/test-questions/bulk-move', json={'description_id': MOCK, 'ids': ids, 'section_id': 'SEC1', 'section_name': 'Physics'})
    check('moved back: SEC1 has 1,2 again', nums() == [1, 2] and not db("SELECT 1 FROM test_questions WHERE test_key=%s AND section_id='SEC9'", (fx['mock_key'],)))

    print('\n== TCS exam inside Test Question Upload (server) ==')
    tcs_add = {'test_id': fx['tcs_sid'], 'test_key': fx['tcs_key'], 'subject_title': 'SELFTEST TCS exam', 'subject_subtitle': 'x',
               'total_questions': 2, 'total_marks': 2, 'total_duration_minutes': 10, 'show_calculator': 0, 'access_label': 'free'}
    r = api('post', '/api/test-descriptions/add', json=tcs_add)
    exam = db("SELECT e.*, ct.title AS ctitle FROM tcs_exams e JOIN cp_tests ct ON ct.id=e.coding_test_id WHERE e.aptitude_test_key=%s", (fx['tcs_key'],))
    check('adding a description under a TCS block creates the exam link and its coding test, unpublished',
          r.status_code == 201 and len(exam) == 1 and exam[0]['is_published'] == 0 and exam[0]['section_id'] == fx['tcs_sid'], r.text[:100])
    TCS = db("SELECT id FROM test_description WHERE test_key=%s", (fx['tcs_key'],))[0]['id']
    r = api('get', f"/api/test-descriptions/{fx['tcs_sid']}")
    row = r.json()[0]
    check('the description list carries the exam state and counts', row.get('section') == 'tcs_test' and row['tcs']['published'] is False
          and row['tcs']['coding_questions'] == 0 and row['tcs']['aptitude_questions'] == 0, str(row.get('tcs')))
    r = api('get', f'/api/coding-panel/{TCS}')
    check('the coding panel opens on the TCS description (same coding test as the exam link)', r.ok and r.json()['test']['id'] == exam[0]['coding_test_id'], r.text[:100])
    r = api('post', f'/api/test-descriptions/{TCS}/tcs-publish', json={'published': True})
    check('publishing is refused while questions are missing', r.status_code == 400 and 'aptitude has 0 of 2' in r.text and 'no problem' in r.text, r.text[:120])
    tform = {'test_id': fx['tcs_sid'], 'test_key': fx['tcs_key'], 'test_description_id': TCS, 'section_id': '1', 'section_name': 'Numerical'}
    upload('/api/test-questions/upload-csv', xlsx(WORK / 'tcs.xlsx', COLS, GOOD[:2]), tform)
    sec = api('post', f'/api/coding-panel/{TCS}/sections', json={'title': 'Coding', 'section_type': 'coding', 'duration_min': 20}).json()
    api('post', f"/api/coding-panel/sections/{sec['section_id']}/questions", json={'title': 'SELFTEST tcs code', 'statement_html': 'Print 1', 'difficulty': 'Easy', 'marks': 10,
                                                                                'allowed_languages': ['python'], 'time_limit_sec': 5, 'memory_limit': '256m',
                                                                                'testcases': [{'input_text': '', 'expected_output': '1', 'is_hidden': False}]})
    r = api('post', f'/api/test-descriptions/{TCS}/tcs-publish', json={'published': True})
    exam = db("SELECT is_published FROM tcs_exams WHERE aptitude_test_key=%s", (fx['tcs_key'],))[0]
    check('with 2 aptitude questions and 1 coding problem it publishes', r.ok and exam['is_published'] == 1, r.text[:100])
    os.chdir(f'{ROOT}/user_app'); sys.path.insert(0, f'{ROOT}/user_app')
    from routes.exam_platform.placement_exam_portal.tcs_portal import models as tcs_models
    listed = tcs_models.list_exams(fx['tcs_sid'], fx['code'])
    check('the student portal lists the published exam with both parts', len(listed) == 1 and listed[0]['aptitude_questions'] == 2 and str(listed[0]['coding_title']).endswith('- Coding'), str(listed)[:120])
    r = api('put', f'/api/test-descriptions/update/{TCS}', json={'subject_title': 'SELFTEST TCS exam renamed'})
    ex = db("SELECT title FROM tcs_exams WHERE aptitude_test_key=%s", (fx['tcs_key'],))[0]
    check('renaming the description renames the exam students see', r.ok and ex['title'] == 'SELFTEST TCS exam renamed', str(ex))
    r = api('post', f'/api/test-descriptions/{TCS}/tcs-publish', json={'published': False})
    check('unpublish hides it again', r.ok and not tcs_models.list_exams(fx['tcs_sid'], fx['code']))
    r = api('delete', f'/api/test-descriptions/delete/{TCS}')
    check('deleting the description removes the exam link and its coding test too', r.ok and not db("SELECT 1 FROM tcs_exams WHERE aptitude_test_key=%s", (fx['tcs_key'],))
          and not db("SELECT 1 FROM cp_tests WHERE test_key=%s", (fx['tcs_key'] + '_code',)), r.text[:80])
    r = api('post', '/api/test-descriptions/add', json=tcs_add)
    TCS = db("SELECT id FROM test_description WHERE test_key=%s", (fx['tcs_key'],))[0]['id']

    print('\n== communication (server) ==')
    r = api('post', f'/api/comm-sections/{COMM}', json={'section_title': 'SELFTEST Grammar', 'section_instruction': 'x', 'section_duration_seconds': 600})
    check('a communication section is created', r.status_code == 201, r.text[:80])
    ccount = lambda: db("SELECT COUNT(*) n FROM comm_questions WHERE test_key=%s", (fx['comm_key'],))[0]['n']
    r = upload(f'/api/comm-questions/upload-csv/{COMM}', comm_bad)
    check('a communication file with bad rows is refused and nothing is saved (no duplicates on re-upload)',
          r.status_code == 400 and ccount() == 0 and len(r.json().get('errors', [])) == 2, r.text[:120])
    r = upload(f'/api/comm-questions/upload-csv/{COMM}', comm_good)
    cm = db("SELECT question_type, correct_marks, negative_marks, question_level, recording_time_seconds FROM comm_questions WHERE test_key=%s ORDER BY id", (fx['comm_key'],))
    check('a clean communication file saves all rows with their marks and levels',
          r.ok and ccount() == 3 and [float(x['correct_marks']) for x in cm] == [2, 5, 10]
          and abs(float(cm[0]['negative_marks']) - 1 / 3) < 0.01 and cm[1]['recording_time_seconds'] == 45
          and [x['question_level'] for x in cm] == ['Easy', 'Medium', 'Tough'], str(cm)[:200])
    r = upload(f'/api/comm-questions/upload-csv/{COMM}', comm_good)
    check('re-uploading the communication sheet adds nothing (3 skipped)', r.status_code == 200 and r.json()['inserted_count'] == 0 and r.json()['skipped_count'] == 3 and ccount() == 3, r.text[:120])
    r = api('post', f'/api/comm-questions/add/{COMM}', json={'section_name': 'SECTION_A', 'question_type': 'MCQ', 'question_text': 'SELFTEST manual comm',
                                                           'option_a': 'x', 'option_b': 'y', 'correct_option': 'a', 'correct_marks': '3', 'negative_marks': '1/4'})
    check('a manual communication question with negative 1/4 saves (used to fail)', r.status_code == 201 and ccount() == 4, r.text[:80])
    r = api('post', f'/api/comm-questions/add/{COMM}', json={'section_name': 'SECTION_A', 'question_type': 'MCQ', 'question_text': 'SELFTEST manual comm',
                                                           'option_a': 'x', 'option_b': 'y', 'correct_option': 'b', 'correct_marks': '3'})
    check('the same communication question by hand is refused', r.status_code == 409 and ccount() == 4, r.text[:100])
    cid = db("SELECT id FROM comm_questions WHERE question_text='SELFTEST manual comm'")[0]['id']
    upd = {'section_name': 'SECTION_A', 'question_type': 'MCQ', 'question_text': 'SELFTEST manual comm edited', 'option_a': 'x',
           'option_b': 'y', 'correct_option': 'b', 'correct_marks': '4', 'negative_marks': '0'}
    r = api('put', f'/api/comm-questions/update/{cid}', json=dict(upd, correct_option=''))
    check('a communication edit without a correct option is refused', r.status_code == 400, r.text[:80])
    r = api('put', f'/api/comm-questions/update/{cid}', json=upd)
    row = db("SELECT question_text, correct_option, correct_marks FROM comm_questions WHERE id=%s", (cid,))[0]
    check('a communication question can now be edited', r.ok and row['question_text'] == 'SELFTEST manual comm edited'
          and row['correct_option'] == 'b' and float(row['correct_marks']) == 4, str(row))
    cnums = lambda: [x['question_number'] for x in db("SELECT question_number FROM comm_questions WHERE test_key=%s AND section_name='SECTION_A' ORDER BY question_number, id", (fx['comm_key'],))]
    second = db("SELECT id FROM comm_questions WHERE test_key=%s AND section_name='SECTION_A' AND question_number=2", (fx['comm_key'],))[0]['id']
    r = api('post', '/api/test-questions/bulk-delete', json={'description_id': COMM, 'ids': [second]})
    check('communication questions renumber after a delete (1,2,3,4 -> 1,2,3)', r.ok and cnums() == [1, 2, 3], str(cnums()))
    r = api('post', f'/api/comm-questions/add/{COMM}', json={'section_name': 'SECTION_A', 'question_type': 'WRITING', 'question_text': 'SELFTEST comm next', 'word_limit': 100, 'correct_marks': '5'})
    check('the next communication question gets number 4', r.status_code == 201 and cnums() == [1, 2, 3, 4], str(cnums()))
    r = api('post', f'/api/comm-sections/{COMM}', json={'section_title': 'SELFTEST Writing', 'section_instruction': 'w', 'section_duration_seconds': 300})
    secb = db("SELECT id FROM comm_sections WHERE test_key=%s AND section_name='SECTION_B'", (fx['comm_key'],))[0]['id']
    last = db("SELECT id FROM comm_questions WHERE test_key=%s AND section_name='SECTION_A' AND question_number=4", (fx['comm_key'],))[0]['id']
    r = api('post', '/api/test-questions/bulk-move', json={'description_id': COMM, 'ids': [last], 'section_name': 'SECTION_B'})
    check('a communication question moves to another section and both renumber', r.ok and cnums() == [1, 2, 3]
          and [x['question_number'] for x in db("SELECT question_number FROM comm_questions WHERE test_key=%s AND section_name='SECTION_B'", (fx['comm_key'],))] == [1], r.text[:80])
    r = api('put', f'/api/comm-sections/update/{secb}', json={'section_title': 'SELFTEST Writing edited', 'section_instruction': 'w2', 'section_duration_seconds': 0})
    check('a section edit with 0 duration is refused', r.status_code == 400, r.text[:70])
    r = api('put', f'/api/comm-sections/update/{secb}', json={'section_title': 'SELFTEST Writing edited', 'section_instruction': 'w2', 'section_duration_seconds': 420})
    sb = db("SELECT section_title, section_duration_seconds FROM comm_sections WHERE id=%s", (secb,))[0]
    check('a communication section can be edited (title, instruction, duration)', r.ok and sb['section_title'] == 'SELFTEST Writing edited' and sb['section_duration_seconds'] == 420, str(sb))
    r = api('post', '/api/test-questions/bulk-marks', json={'description_id': COMM, 'ids': [last], 'correct_marks': '7'})
    check('set marks works for communication questions too', r.ok and float(db("SELECT correct_marks FROM comm_questions WHERE id=%s", (last,))[0]['correct_marks']) == 7)
    api('post', '/api/test-questions/bulk-move', json={'description_id': COMM, 'ids': [last], 'section_name': 'SECTION_A'})
    api('delete', f'/api/comm-sections/delete/{secb}')

    print('\n== the page ==')
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome', headless=True)
        ctx = b.new_context(viewport={'width': 1440, 'height': 960}); ctx.set_default_timeout(15000)
        pg = ctx.new_page(); errs, natives = [], []
        pg.on('pageerror', lambda e: errs.append(str(e)[:200]))
        pg.on('dialog', lambda d: (natives.append(d.message), d.dismiss()))
        pg.goto(f'{ADMIN}/admin_login')
        pg.fill('input[name="email"]', ADMIN_EMAIL); pg.keyboard.press('Enter'); time.sleep(1.2)
        pg.fill('input[name="password"]', ADMIN_PASSWORD); pg.keyboard.press('Enter'); time.sleep(1.5)

        dialog_open = lambda: pg.evaluate("(() => { const d = document.querySelector('.acf'); return !!d && !d.hidden; })()")
        dialog_text = lambda: pg.locator('.acf-box').inner_text() if dialog_open() else ''
        toast = lambda: pg.locator('.admin-toast').last.inner_text() if pg.locator('.admin-toast').count() else ''
        approve = lambda: (time.sleep(0.5), pg.click('.acf [data-acf="confirm"]'), time.sleep(1.4))
        cancel = lambda: (time.sleep(0.5), pg.click('.acf [data-acf="cancel"]'), time.sleep(0.5))

        GROUP, COURSE = fx['student']['name'], fx['code']

        def open_test(sid, desc_id):
            pg.goto(f'{ADMIN}/manage-tests'); time.sleep(1.8)
            try: pg.evaluate("sessionStorage.removeItem('mtPickerPlace')")
            except Exception: pass
            pg.reload(); time.sleep(1.8)
            pg.click(f'.mt-tcard--group[data-group="{GROUP}"]'); time.sleep(0.5)
            pg.click(f'.mt-tcard--course[data-course="{COURSE}"]'); time.sleep(0.5)
            pg.click(f'.mt-tcard[data-id="{sid}"]'); time.sleep(1.5)
            time.sleep(0.4)
            pg.click(f'.load-questions-btn[data-id="{desc_id}"]'); time.sleep(1.5)

        print('\n-- choosing the test: group, course, content --')
        pg.goto(f'{ADMIN}/manage-tests'); time.sleep(1.8)
        pg.evaluate("sessionStorage.removeItem('mtPickerPlace')"); pg.reload(); time.sleep(1.8)
        check('the section is named Test Question Upload', pg.locator('.as-title').inner_text() == 'Test Question Upload'
              and 'Test Question Upload' in pg.locator('.as-sidebar, aside, nav').first.inner_text(), pg.locator('.as-title').inner_text())
        check('step 1 shows course groups (GATE, PLACEMENT, the SELFTEST group), not test cards',
              pg.locator('.mt-tcard--group').count() >= 2 and pg.locator(f'.mt-tcard--group[data-group="{GROUP}"]').count() == 1
              and pg.locator('.mt-tcard[data-id]').count() == 0 and pg.locator('.mt-step.is-active').inner_text().strip().startswith('1'))
        pg.click(f'.mt-tcard--group[data-group="{GROUP}"]'); time.sleep(0.5)
        tile = pg.locator(f'.mt-tcard--course[data-course="{COURSE}"]')
        check('step 2 shows the courses inside that group with code and name', tile.count() == 1 and 'SELFTEST' in tile.inner_text()
              and pg.locator('.mt-tcard--course').count() == 1 and GROUP in pg.locator('.mt-step[data-stage="group"]').inner_text())
        pg.click(f'.mt-tcard--course[data-course="{COURSE}"]'); time.sleep(0.5)
        ids = pg.locator('.mt-tcard[data-id]').evaluate_all("els => els.map(e => e.dataset.id)")
        check('step 3 shows only that course\'s test content cards', sorted(ids) == sorted([fx['mock_sid'], fx['comm_sid'], fx['code_sid'], fx['tcs_sid']]), str(ids))
        heads = pg.locator('.mt-group-head').all_inner_texts()
        check('step 3 groups the cards by exam type in a fixed order: Communication, TCS, Coding, Mock',
              [h.split('\n')[0].strip().split(' ')[0] for h in heads] == ['COMMUNICATION', 'TCS', 'CODING', 'MOCK'], str(heads))
        order = pg.locator('.mt-picker__grid > *').evaluate_all("els => els.map(e => e.classList.contains('mt-group-head') ? 'H:' + e.textContent.trim().split(' ')[0].toUpperCase() : e.dataset.id)")
        check('each card sits under its own heading', order == ['H:COMMUNICATION', fx['comm_sid'], 'H:TCS', fx['tcs_sid'], 'H:CODING', fx['code_sid'], 'H:MOCK', fx['mock_sid']], str(order))
        pg.click('.mt-step[data-stage="group"]'); time.sleep(0.4)
        check('clicking a finished step goes back to it', pg.locator('.mt-tcard--group').count() >= 2)
        pg.fill('#mtPickerSearch', 'SELFTEST mock'); time.sleep(0.4)
        check('search still finds test content directly, with its group and course shown',
              pg.locator(f'.mt-tcard[data-id="{fx["mock_sid"]}"]').count() == 1 and GROUP in pg.locator(f'.mt-tcard[data-id="{fx["mock_sid"]}"]').inner_text())
        pg.fill('#mtPickerSearch', ''); time.sleep(0.4)
        pg.click(f'.mt-tcard--group[data-group="{GROUP}"]'); time.sleep(0.4); pg.click(f'.mt-tcard--course[data-course="{COURSE}"]'); time.sleep(0.4)
        pg.click(f'.mt-tcard[data-id="{fx["mock_sid"]}"]'); time.sleep(1.5)
        check('picking a card shows the path group › course and the test descriptions list with an add button',
              f'{GROUP} › {COURSE}' in pg.locator('#mtPickedPath').inner_text() and pg.locator('#testDescriptionsTable').is_visible()
              and pg.locator('#mtAddToggle').is_visible() and pg.locator('#addTestDescriptionContainer').is_hidden(), pg.locator('#mtPickedPath').inner_text())
        check('the sidebar has one option only: Upload Questions', pg.locator('.as-view[data-view]').count() == 1
              and 'Upload Questions' in pg.locator('.as-view[data-view="upload"]').inner_text())
        if SHOT:
            pg.screenshot(path=f'{SHOTS}/mocktest_descriptions.png')
        pg.click('#mtAddToggle'); time.sleep(0.5)
        check('+ Add new description opens the same form in place', pg.locator('#addTestDescriptionContainer').is_visible()
              and 'Add New Test Description' in pg.locator('#addTestDescriptionContainer').inner_text() and 'Close' in pg.locator('#mtAddToggle').inner_text())
        pg.click('#mtAddToggle'); time.sleep(0.4)
        check('it closes again', pg.locator('#addTestDescriptionContainer').is_hidden())
        pg.click('#mtChangeTestBtn'); time.sleep(0.5)
        check('Change Test returns to that course\'s cards, not to step 1', pg.locator('.mt-tcard[data-id]').count() == 4 and pg.locator('.mt-tcard--group').count() == 0)
        pg.reload(); time.sleep(1.8)
        check('after a refresh the picker reopens on the same course', pg.locator(f'.mt-tcard[data-id="{fx["mock_sid"]}"]').count() == 1 and pg.locator('.mt-tcard--group').count() == 0)
        if SHOT:
            pg.evaluate("sessionStorage.removeItem('mtPickerPlace')"); pg.reload(); time.sleep(1.5)
            pg.screenshot(path=f'{SHOTS}/mocktest_pick_group.png')
            pg.click(f'.mt-tcard--group[data-group="{GROUP}"]'); time.sleep(0.5)
            pg.screenshot(path=f'{SHOTS}/mocktest_pick_course.png')

        open_test(fx['mock_sid'], MOCK)
        icon = pg.evaluate("getComputedStyle(document.querySelector('#iqRotateBtn i'), '::before').content")
        check('icons load (the Rotate button is no longer blank)', len(icon) >= 3 and icon not in ('none', 'normal'), repr(icon))
        check('opening a test lists its sections with ID and name', pg.locator('.qm-section[data-sid="SEC1"]').count() == 1
              and 'Physics' in pg.locator('.qm-section[data-sid="SEC1"]').inner_text())
        pg.click('.qm-section[data-sid="SEC1"]'); time.sleep(1.4)
        check('clicking a section opens it with its questions listed', pg.locator('#qmQuestionTable tbody tr').count() == 2
              and pg.locator('#currentSectionBadge').inner_text() == 'Physics')
        methods = pg.locator('#questionControls .qm-method').all_inner_texts()
        check('four ways to add, Excel first and marked Recommended, then Manual, Image, Bulk image',
              len(methods) == 4 and 'Excel' in methods[0] and 'Recommended' in methods[0] and 'Manual' in methods[1]
              and 'Image question' in methods[2] and 'Bulk image' in methods[3], ' | '.join(m.replace('\n', ' ')[:30] for m in methods))
        check('the note says to use Excel or Manual', 'Excel sheet' in pg.locator('.qm-note').first.inner_text() and 'Manual' in pg.locator('.qm-note').first.inner_text())
        pg.click('#changeSectionBtn'); time.sleep(0.4)
        check('Switch section lists every section and a create option',
              pg.locator('#qmSwitchMenu .qm-switch-item[data-sid="SEC1"]').count() == 1 and pg.locator('#qmNewSectionItem').count() == 1)
        pg.click('#qmNewSectionItem'); time.sleep(0.6)
        pg.fill('#sectionIdInput', 'bad id'); pg.fill('#sectionNameInput', 'Chem'); pg.click('#loadQuestionsForSectionBtn'); time.sleep(0.5)
        check('a section ID with a space is refused with a clear message', 'Section ID' in toast() and pg.locator('#questionControls').is_hidden(), toast())
        pg.fill('#sectionIdInput', 'SEC2'); pg.click('#loadQuestionsForSectionBtn'); time.sleep(1.2)
        check('a new section opens empty and says so', pg.locator('#qmCurrentId').inner_text() == 'SEC2' and pg.locator('#noQuestionsMessage').is_visible())

        print('\n-- manual entry --')
        pg.click('.qm-method[data-method="manual"]'); time.sleep(0.8)
        check('the Manual window names the section it adds to', 'Chem (SEC2)' in pg.locator('#addQuestionModal .modal-title').inner_text())
        pg.select_option('#addQuestionType', 'MCQ'); pg.fill('#addCorrectMarks', '2')
        for sel, text in (('#addQuestionTextEditor', 'SELFTEST typed question'), ('#addOptionAEditor', 'one'), ('#addOptionBEditor', 'two'),
                          ('#addOptionCEditor', 'three'), ('#addOptionDEditor', 'four')):
            pg.click(f'{sel} .ql-editor'); pg.keyboard.type(text)
        pg.fill('#addCorrectOption', 'c'); pg.click('#addQuestionForm button[type="submit"]'); time.sleep(1.5)
        typed = db("SELECT id, correct_option, section_id FROM test_questions WHERE question_text LIKE '%%SELFTEST typed question%%'")
        check('a typed question saves into the open section', typed and typed[0]['section_id'] == 'SEC2' and typed[0]['correct_option'] == 'C', str(typed))
        check('it appears in the list', pg.locator('#qmQuestionTable tbody tr').count() == 1)
        check('the list shows the question number, not the database id', pg.locator('#qmQuestionTable .qm-num').first.inner_text() == 'Q1'
              and str(typed[0]['id']) not in pg.locator('#qmQuestionTable tbody').inner_text())
        head = pg.locator('#questionsDisplayArea .card-header h5').inner_text()
        check('the question card says "Question 1", without the database id', head.startswith('Question 1') and 'ID:' not in head, head)

        print('\n-- save & add another, find, rename --')
        pg.click('.qm-method[data-method="manual"]'); time.sleep(0.8)
        pg.select_option('#addQuestionType', 'MCQ'); pg.select_option('#addQuestionLevel', 'Tough'); pg.fill('#addCorrectMarks', '5'); pg.fill('#addNegativeMarks', '1/5')
        for sel, text in (('#addQuestionTextEditor', 'SELFTEST another one'), ('#addOptionAEditor', 'a'), ('#addOptionBEditor', 'b')):
            pg.click(f'{sel} .ql-editor'); pg.keyboard.type(text)
        pg.fill('#addCorrectOption', 'a'); pg.click('#addQuestionAnother'); time.sleep(1.5)
        check('Save & add another saves and keeps the window open with type, level and marks filled',
              pg.locator('#addQuestionModal').is_visible() and pg.input_value('#addQuestionType') == 'MCQ' and pg.input_value('#addQuestionLevel') == 'Tough'
              and pg.input_value('#addCorrectMarks') == '5' and pg.input_value('#addNegativeMarks') == '1/5'
              and pg.locator('#addQuestionTextEditor .ql-editor').inner_text().strip() == ''
              and bool(db("SELECT 1 FROM test_questions WHERE question_text LIKE '%%SELFTEST another one%%'")))
        pg.click('#addQuestionModal .btn-close'); time.sleep(0.6)
        check('the list now has 2 questions numbered Q1, Q2', pg.locator('#qmQuestionTable .qm-num').all_inner_texts() == ['Q1', 'Q2'])
        pg.fill('#qmFind', 'another'); time.sleep(0.3)
        visible = pg.locator('#qmQuestionTable tbody tr:not(.qm-hidden-row)').count()
        check('Find in section narrows the list', visible == 1 and '1 of 2 match' in pg.locator('#qmFindCount').inner_text(), str(visible))
        pg.fill('#qmFind', ''); time.sleep(0.3)
        pg.click('#qmRenameSection'); time.sleep(0.6)
        pg.fill('#qmFormModal [name="section_name"]', 'Chemistry Basics'); pg.click('#qmFormModal [data-qm="submit"]'); time.sleep(0.8)
        t = dialog_text()
        check('Rename asks for approval showing old and new name', 'Rename section SEC2' in t and 'Chem' in t and 'Chemistry Basics' in t, t.replace('\n', ' | ')[:120])
        approve()
        check('the section is renamed on its questions and in the bar', pg.locator('#currentSectionBadge').inner_text() == 'Chemistry Basics'
              and {x['section_name'] for x in db("SELECT section_name FROM test_questions WHERE test_key=%s AND section_id='SEC2'", (fx['mock_key'],))} == {'Chemistry Basics'})
        pg.locator('#qmQuestionTable tbody tr').nth(1).locator('.qm-row-check').check(); time.sleep(0.2)
        pg.click('#qmMarksSelected'); time.sleep(0.6)
        pg.fill('#qmFormModal [name="correct_marks"]', '9'); pg.click('#qmFormModal [data-qm="submit"]'); time.sleep(0.7)
        check('Set marks asks for approval', 'Apply these marks' in dialog_text())
        approve()
        check('the chosen question got +9, the other kept +2', [float(x['correct_marks']) for x in db("SELECT correct_marks FROM test_questions WHERE test_key=%s AND section_id='SEC2' ORDER BY question_number", (fx['mock_key'],))] == [2, 9])
        pg.locator('#qmQuestionTable tbody tr').nth(1).locator('.qm-row-check').check(); time.sleep(0.2)
        pg.click('#qmMoveSelected'); time.sleep(0.6)
        pg.select_option('#qmFormModal [name="target"]', 'SEC1'); pg.click('#qmFormModal [data-qm="submit"]'); time.sleep(0.7)
        check('Move asks for approval naming both sections', 'Move 1 question to Physics (SEC1)' in dialog_text(), dialog_text()[:90])
        approve()
        check('it moved to SEC1 as its next number and SEC2 renumbered', db("SELECT section_id, question_number FROM test_questions WHERE question_text LIKE '%%SELFTEST another one%%'")[0]['section_id'] == 'SEC1'
              and pg.locator('#qmQuestionTable .qm-num').all_inner_texts() == ['Q1'])
        db("DELETE FROM test_questions WHERE question_text LIKE '%%SELFTEST another one%%'")

        print('\n-- edit with approval --')
        pg.click('#qmQuestionTable .edit-question-btn'); time.sleep(0.8)
        pg.click('#editQuestionForm button[type="submit"]'); time.sleep(0.6)
        check('saving an edit with nothing changed asks nothing', not dialog_open() and 'No changes' in toast(), toast())
        pg.fill('#editCorrectMarks', '3'); pg.click('#editQuestionForm button[type="submit"]'); time.sleep(0.6)
        t = dialog_text()
        check('an edit asks for approval and lists the change', 'Correct marks' in t and '2' in t and '3' in t, t.replace('\n', ' | ')[:140])
        cancel()
        check('Cancel keeps the old value', float(db("SELECT correct_marks FROM test_questions WHERE id=%s", (typed[0]['id'],))[0]['correct_marks']) == 2)
        pg.click('#editQuestionForm button[type="submit"]'); approve()
        check('approving saves the edit and says so', float(db("SELECT correct_marks FROM test_questions WHERE id=%s", (typed[0]['id'],))[0]['correct_marks']) == 3
              and 'updated' in toast().lower(), toast())

        print('\n-- Excel from the page --')
        pg.click('.qm-method[data-method="excel"]'); time.sleep(0.8)
        pg.set_input_files('#csvFile', browser_bad); pg.click('#uploadCsvSubmitBtn'); time.sleep(1.6)
        check('a bad file shows its row problems and saves nothing', pg.locator('#csvErrorList li').count() == 1
              and 'Nothing was saved' in pg.locator('#csvUploadErrors').inner_text()
              and not db("SELECT 1 FROM test_questions WHERE question_text LIKE '%%from browser bad%%'"))
        pg.set_input_files('#csvFile', browser_file); pg.click('#uploadCsvSubmitBtn'); time.sleep(1.8)
        check('a good file saves, the window closes and the list grows',
              pg.locator('#qmQuestionTable tbody tr').count() == 2 and not pg.locator('#uploadQuestionsCsvModal').is_visible(), toast())
        pg.click('.qm-method[data-method="excel"]'); time.sleep(0.8)
        pg.set_input_files('#csvFile', browser_file); pg.click('#uploadCsvSubmitBtn'); time.sleep(1.8)
        check('uploading it again lists the row as already stored and adds nothing',
              pg.locator('#qmQuestionTable tbody tr').count() == 2 and 'already stored' not in '' and 'skipped' in pg.locator('#csvUploadErrors').inner_text().lower()
              and pg.locator('#csvErrorList li').count() == 1, pg.locator('#csvUploadErrors').inner_text()[:100])
        pg.click('#csv-modal-close-btn'); time.sleep(0.6)

        print('\n-- image question --')
        pg.click('.qm-method[data-method="image"]'); time.sleep(1.0)
        pg.set_input_files('#iqFile', img1); time.sleep(1.4)
        box = pg.locator('#iqImage').bounding_box()
        check('the whole image fits on screen', box['y'] + box['height'] <= 960 + 2, str(box))

        def drag(x0, y0, x1, y1):
            bb = pg.locator('#iqImage').bounding_box()
            pg.mouse.move(bb['x'] + x0 * bb['width'], bb['y'] + y0 * bb['height']); pg.mouse.down()
            pg.mouse.move(bb['x'] + x1 * bb['width'], bb['y'] + y1 * bb['height'], steps=8); pg.mouse.up(); time.sleep(0.4)

        regions = lambda: pg.evaluate("Array.from(document.querySelectorAll('#iqStage .iq-region')).map(r => r.querySelector('.iq-region__tag').textContent)")
        for i in range(4):
            drag(0.08, (215 + i * 90) / 700, 0.5, (250 + i * 90) / 700)
        check('dragging marks options A to D, moving to the next letter each time', regions() == ['A', 'B', 'C', 'D'], str(regions()))
        pg.click('#iqToolGroup [data-tool="hide"]'); drag(0.3, (215 + 90) / 700 + 0.005, 0.45, (250 + 90) / 700 - 0.005)
        check('Hide can be dragged over a marked option (used to be blocked)', pg.evaluate("document.querySelectorAll('#iqStage .iq-region').length") == 4)
        before_b = pg.evaluate("document.querySelectorAll('#iqStage .iq-region')[1].style.top")
        pg.click('#iqAutoTrimBtn'); time.sleep(0.8)
        after_b = pg.evaluate("document.querySelectorAll('#iqStage .iq-region')[1].style.top")
        check('Auto-trim keeps the marked options, moved to the trimmed image', regions() == ['A', 'B', 'C', 'D'] and before_b != after_b, f'{before_b} -> {after_b}')
        pg.click('#iqRotateBtn'); time.sleep(0.6)
        check('Rotate keeps the marked options', regions() == ['A', 'B', 'C', 'D'])
        pg.click('#iqUndoBtn'); time.sleep(0.5); pg.click('#iqUndoBtn'); time.sleep(0.5)
        check('Undo brings back the image and marks step by step', regions() == ['A', 'B', 'C', 'D']
              and pg.evaluate("document.querySelectorAll('#iqStage .iq-region')[1].style.top") == before_b)
        pg.click('#iqClearRegions'); time.sleep(0.3); pg.click('#iqUndoBtn'); time.sleep(0.4)
        check('Undo also restores cleared option areas', regions() == ['A', 'B', 'C', 'D'])
        pg.locator('#iqStatus li[data-letter="b"]').click(); time.sleep(0.3)
        check('clicking an option row sets it as the answer and stars it', pg.input_value('#iqAnswer') == 'B'
              and 'correct' in pg.locator('#iqStatus li[data-letter="b"]').inner_text())
        pg.fill('#iqAnswer', 'BC'); pg.click('#iqSaveBtn'); time.sleep(0.6)
        check('two answers on an MCQ are refused before saving', 'exactly one' in toast(), toast())
        pg.fill('#iqAnswer', 'B'); pg.click('#iqSaveBtn'); time.sleep(2.2)
        iq = db("SELECT id, correct_option, option_regions, question_image FROM test_questions WHERE section_id='SEC2' AND question_image IS NOT NULL AND test_key=%s", (fx['mock_key'],))
        made_images.update(x['question_image'] for x in iq)
        check('the image question saves with all four areas', iq and iq[0]['correct_option'] == 'B'
              and sorted(json.loads(iq[0]['option_regions'])) == ['a', 'b', 'c', 'd'], str(iq)[:120])
        pg.keyboard.press('Escape'); time.sleep(0.6)
        if pg.locator('#imageQuestionModal').is_visible():
            pg.click('#imageQuestionModal .btn-close'); time.sleep(0.6)
        pg.evaluate("document.querySelector('#qmQuestionTable tbody tr:last-child .edit-question-btn').click()"); time.sleep(1.6)
        pg.locator('#iqStatus li[data-letter="c"]').click(); time.sleep(0.2)
        pg.click('#iqSaveBtn'); time.sleep(0.6)
        t = dialog_text()
        check('saving an edited image question asks for approval', 'Save changes to image question' in t and 'C' in t, t.replace('\n', ' | ')[:120])
        approve(); time.sleep(1.0)
        now_img = db("SELECT correct_option, question_image FROM test_questions WHERE id=%s", (iq[0]['id'],))[0]
        made_images.add(now_img['question_image'])
        check('approving updates it', now_img['correct_option'] == 'C', str(now_img))
        if pg.locator('#imageQuestionModal').is_visible():
            pg.click('#imageQuestionModal .btn-close'); time.sleep(0.6)

        print('\n-- select and delete --')
        pg.click('#qmSelectAll'); time.sleep(0.3)
        check('Select all ticks every question', 'Delete selected (3)' in pg.locator('#qmDeleteSelected').inner_text(), pg.locator('#qmDeleteSelected').inner_text())
        pg.click('#qmDeleteSelected'); time.sleep(0.8)
        t = dialog_text()
        check('Delete selected asks for approval with the count', 'Delete 3 selected questions' in t and 'Chemistry Basics (SEC2)' in t, t.replace('\n', ' | ')[:140])
        cancel()
        check('Cancel deletes nothing', db("SELECT COUNT(*) n FROM test_questions WHERE section_id='SEC2' AND test_key=%s", (fx['mock_key'],))[0]['n'] == 3)
        pg.locator('#qmQuestionTable tbody tr').first.locator('.qm-row-check').uncheck(); time.sleep(0.2)
        pg.click('#qmDeleteSelected'); approve()
        left = db("SELECT question_text FROM test_questions WHERE section_id='SEC2' AND test_key=%s", (fx['mock_key'],))
        check('approving deletes exactly the ticked questions', len(left) == 1 and 'typed question' in left[0]['question_text'], str(left))
        check('after the delete the list restarts at Q1 with no gap', pg.locator('#qmQuestionTable .qm-num').first.inner_text() == 'Q1')
        check('a message confirms the delete', 'deleted' in toast(), toast())
        pg.click('#qmQuestionTable .delete-question-btn'); time.sleep(0.8)
        check('a single delete also asks first', 'Delete question 1' in dialog_text())
        cancel()
        if SHOT:
            pg.screenshot(path=f'{SHOTS}/mocktest_competitive.png', full_page=False)

        print('\n-- test descriptions --')
        pg.click(f'.edit-desc-btn[data-id="{MOCK}"]'); time.sleep(0.8)
        pg.fill('#editTotalQuestions', '41'); pg.click('#editTestDescriptionForm button[type="submit"]'); time.sleep(0.6)
        t = dialog_text()
        check('editing a test description asks with the change listed', 'Total questions' in t and '40' in t and '41' in t, t.replace('\n', ' | ')[:120])
        cancel()
        check('Cancel keeps it', db("SELECT total_questions FROM test_description WHERE id=%s", (MOCK,))[0]['total_questions'] == 40)
        pg.keyboard.press('Escape'); time.sleep(0.5)
        check('there is no Clone button on a test description', pg.locator('.clone-desc-btn').count() == 0)
        r = api('post', '/api/test-descriptions/add', json={'test_id': fx['mock_sid'], 'test_key': 'free_5e1f7e57000000000009', 'subject_title': 'SELFTEST spare paper',
                                                          'subject_subtitle': 'x', 'total_questions': 5, 'total_marks': 10, 'total_duration_minutes': 10,
                                                          'show_calculator': 1, 'access_label': 'free'})
        spare = db("SELECT id FROM test_description WHERE test_key='free_5e1f7e57000000000009'")
        check('a second description can be added the normal way', r.status_code in (200, 201) and len(spare) == 1, r.text[:80])
        pg.evaluate("$('#testDescriptionsTable').DataTable().ajax.reload()"); time.sleep(1.5)
        pg.click(f'.delete-desc-btn[data-id="{spare[0]["id"]}"]'); time.sleep(0.6)
        check('deleting a test description asks first', 'Delete "' in dialog_text())
        approve()
        check('approving deletes it', not db("SELECT 1 FROM test_description WHERE id=%s", (spare[0]['id'],)))

        print('\n-- communication page --')
        open_test(fx['comm_sid'], COMM)
        cm_methods = pg.locator('#commMethods .qm-method').all_inner_texts()
        check('communication shows two cards: Excel first (recommended), then Manual',
              len(cm_methods) == 2 and 'Excel' in cm_methods[0] and 'Recommended' in cm_methods[0] and 'Manual' in cm_methods[1])
        check('both panels stay closed until a card is clicked', pg.locator('#commExcelPanel').is_hidden() and pg.locator('#commManualPanel').is_hidden())
        pg.click('#commMethods [data-comm-method="manual"]'); time.sleep(0.4)
        check('Manual opens its form only', pg.locator('#commManualPanel').is_visible() and pg.locator('#commExcelPanel').is_hidden())
        pg.select_option('#commQType', 'MCQ'); pg.fill('#commQText', 'SELFTEST page comm'); pg.fill('#commQOptA', 'p'); pg.fill('#commQOptB', 'q')
        pg.select_option('#commQCorrect', 'a'); pg.fill('#commQNegative', '1/3'); pg.click('#commAddQuestionBtn'); time.sleep(1.4)
        check('a manual communication question saves from the page', bool(db("SELECT 1 FROM comm_questions WHERE question_text='SELFTEST page comm'")), toast())
        n_items = pg.locator('#commQuestionsList .comm-q').count()
        check('the list shows every question with edit and delete', n_items == 5 and pg.locator('#commQuestionsList .comm-edit-q').count() == 5, str(n_items))
        pg.locator('#commQuestionsList .comm-q').filter(has_text='SELFTEST page comm').locator('.comm-edit-q').click(); time.sleep(0.6)
        check('Edit fills the form and says which question', pg.input_value('#commQText') == 'SELFTEST page comm' and 'Editing question' in pg.locator('#commManualTitle').inner_text())
        pg.fill('#commQText', 'SELFTEST page comm edited'); pg.click('#commAddQuestionBtn'); time.sleep(0.6)
        t = dialog_text()
        check('saving a communication edit asks with the change listed', 'Question text' in t and 'edited' in t, t.replace('\n', ' | ')[:120])
        approve()
        check('approving saves it', bool(db("SELECT 1 FROM comm_questions WHERE question_text='SELFTEST page comm edited'")))
        pg.click('#commMethods [data-comm-method="excel"]'); time.sleep(0.4)
        pg.set_input_files('#commCsvFile', comm_bad); pg.click('#commCsvUploadBtn'); time.sleep(1.6)
        check('a bad communication file lists its problems, nothing saved', pg.locator('#commCsvErrors li').count() == 3 and ccount() == 5)
        pg.click('.comm-edit-sec'); time.sleep(0.6)
        pg.fill('#qmFormModal [name="section_duration_seconds"]', '900'); pg.click('#qmFormModal [data-qm="submit"]'); time.sleep(0.7)
        check('editing a communication section asks with the change listed', 'Duration (sec)' in dialog_text() and '900' in dialog_text())
        approve()
        check('the duration is saved', db("SELECT section_duration_seconds FROM comm_sections WHERE test_key=%s AND section_name='SECTION_A'", (fx['comm_key'],))[0]['section_duration_seconds'] == 900)
        pg.fill('#commFind', 'page comm edited'); time.sleep(0.3)
        check('Find works on the communication list', pg.locator('#commQuestionsList .comm-q:not(.qm-hidden-row)').count() == 1)
        pg.fill('#commFind', ''); time.sleep(0.3)
        pg.click('#commSelectAll'); time.sleep(0.2); pg.click('#commDeleteSelected'); time.sleep(0.8)
        check('communication Delete selected asks with the count', 'Delete 5 selected questions' in dialog_text())
        approve()
        check('approving deletes them all', ccount() == 0)
        pg.click('.comm-del-sec'); time.sleep(0.5)
        check('deleting a communication section asks first', 'Delete section' in dialog_text())
        cancel()

        print('\n-- admin home grouping --')
        pg.goto(f'{ADMIN}/admin_dashboard'); time.sleep(1.2)
        titles = [t.title() for t in pg.locator('.ah-section__title').all_inner_texts()]
        check('the home page groups tools into Placement Exam Portal and Competitive Exam Platform', 'Placement Exam Portal' in titles and 'Competitive Exam Platform' in titles
              and 'Tests & Questions' not in titles, str(titles))
        sec = pg.locator('.ah-section').filter(has_text='Placement Exam Portal').first.inner_text()
        check('Placement holds Test Question Upload, Practice Coding and Quiz Bank', all(x in sec for x in ('Test Question Upload', 'Practice Coding', 'Quiz Bank')) and 'Practice Papers' not in sec)
        sec2 = pg.locator('.ah-section').filter(has_text='Competitive Exam Platform').first.inner_text()
        check('Competitive holds Test Question Upload and Practice Papers', 'Practice Papers' in sec2 and 'Test Question Upload' in sec2 and 'Quiz Bank' not in sec2)
        pg.locator('.ah-section').filter(has_text='Placement Exam Portal').locator('a.ah-card').first.click(); time.sleep(1.8)
        check('the Placement card opens Test Question Upload already inside PLACEMENT (step 2)',
              pg.locator('.mt-tcard--course').count() >= 1 and 'PLACEMENT' in pg.locator('.mt-step[data-stage="group"]').inner_text(), pg.locator('#mtPickerLead').inner_text())

        print('\n-- TCS exam row --')
        open_test(fx['tcs_sid'], TCS)
        check('no TCS Exams entry in the sidebar', pg.locator('.as-view[data-view]').count() == 1 and 'TCS Exams' not in pg.locator('body').inner_text())
        check('the TCS note explains the row and both upload buttons', pg.locator('#mtDescLeadTcs').is_visible() and pg.locator('#mtDescLead').is_hidden())
        row = pg.locator(f'#testDescriptionsTable tr:has(.load-questions-btn[data-id="{TCS}"])')
        check('the exam row shows Draft, a Coding button and a Publish button', 'Draft' in row.inner_text() and row.locator('.coding-questions-btn').count() == 1
              and 'Publish' in row.locator('.tcs-publish-btn').inner_text(), row.inner_text().replace('\n', ' ')[:120])
        row.locator('.coding-questions-btn').click(); time.sleep(1.5)
        check('Coding opens the coding editor for this exam', pg.locator('#codingManagementContainer').is_visible() and 'Coding' in pg.locator('#codingManagementHeader').inner_text())
        row.locator('.tcs-publish-btn').click(); time.sleep(0.6)
        check('Publish asks for approval and shows the counts', 'Publish "SELFTEST TCS exam"' in dialog_text() and '0 of 2 questions' in dialog_text(), dialog_text()[:120])
        approve()
        check('publishing an empty exam is refused with the reason', 'Cannot publish yet' in toast(), toast()[:100])

        print('\n-- coding page --')
        sec = api('post', f'/api/coding-panel/{CODING}/sections', json={'title': 'SELFTEST coding', 'section_type': 'coding', 'duration_min': 30}).json()
        csid = sec.get('section_id')
        for i in range(3):
            api('post', f'/api/coding-panel/sections/{csid}/questions', json={
                'title': f'SELFTEST coding {i}', 'statement_html': 'Print 1', 'difficulty': 'Easy', 'marks': 10,
                'allowed_languages': ['python'], 'time_limit_sec': 5, 'memory_limit': '256m',
                'testcases': [{'input_text': '', 'expected_output': '1', 'is_hidden': False}]})
        cq = lambda: db("SELECT COUNT(*) n FROM cp_questions WHERE section_id=%s", (csid,))[0]['n']
        check('coding questions set up', cq() == 3, str(cq()))
        open_test(fx['code_sid'], CODING); time.sleep(1.0)
        if pg.locator('#cdpViewSection').count():
            pg.select_option('#cdpViewSection', str(csid)); time.sleep(1.2)
        pg.click('#cdpSelectAll'); time.sleep(0.3); pg.click('#cdpDeleteSelected'); time.sleep(0.6)
        check('coding Delete selected asks with the count', 'Delete 3 selected coding questions' in dialog_text(), dialog_text()[:80])
        cancel()
        check('Cancel keeps them', cq() == 3)
        pg.click('#cdpDeleteSelected'); approve(); time.sleep(1.5)
        check('approving deletes them', cq() == 0, str(cq()))
        pg.select_option('#cdpTargetSection', str(csid)); time.sleep(0.6)
        pg.click('.cdp-part[data-part="statement"] .cdp-mode[data-mode="image"]'); time.sleep(0.3)
        pg.set_input_files('.cdp-pick[data-slot="statement_image"]', img1); time.sleep(1.5)
        size = lambda: pg.evaluate("[document.getElementById('cdpCanvas').width, document.getElementById('cdpCanvas').height]")
        w0 = size()

        def cdrag(x0, y0, x1, y1):
            bb = pg.locator('#cdpCanvas').bounding_box()
            pg.mouse.move(bb['x'] + x0 * bb['width'], bb['y'] + y0 * bb['height']); pg.mouse.down()
            pg.mouse.move(bb['x'] + x1 * bb['width'], bb['y'] + y1 * bb['height'], steps=6); pg.mouse.up(); time.sleep(0.4)

        check('the coding crop window opens with the image', pg.locator('#cdpCropModal').is_visible() and w0[0] == 900, str(w0))
        pg.click('#cdpCropTools [data-tool="hide"]'); cdrag(0.1, 0.1, 0.3, 0.2)
        check('Hide applies when the drag ends (no separate Apply step)', size() == w0 and pg.evaluate("document.querySelector('#cdpCropTools [data-tool=hide]').classList.contains('active')"))
        pg.click('#cdpCropTools [data-tool="crop"]'); cdrag(0.05, 0.05, 0.75, 0.85)
        w1 = size()
        check('Crop applies when the drag ends', w1[0] < w0[0] and w1[1] < w0[1], f'{w0} -> {w1}')
        pg.click('#cdpRotate'); time.sleep(0.3)
        check('Rotate turns the image', size() == [w1[1], w1[0]], str(size()))
        pg.click('#cdpUndo'); time.sleep(0.3)
        check('Undo reverses the last step', size() == w1, str(size()))
        pg.click('#cdpResetImg'); time.sleep(0.3)
        check('Reset restores the original', size() == w0, str(size()))
        pg.click('#cdpCropTools [data-tool="crop"]'); cdrag(0.05, 0.05, 0.9, 0.9)
        pg.click('#cdpCropSave'); time.sleep(1.6)
        src = pg.evaluate("(document.querySelector('.cdp-preview[data-slot=\"statement_image\"] img') || {}).src || ''")
        check('"Use this image" stores the edited image and shows it', '/static/uploads/coding_questions/' in src and not pg.locator('#cdpCropModal').is_visible(), src[-60:])
        if src:
            made_images.add('coding:' + src.rsplit('/', 1)[-1])

        print('\n-- bulk image page --')
        pg.goto(f"{ADMIN}/manage-tests/image-batch?test={fx['mock_sid']}&desc={MOCK}&sid=SEC1&sname=Physics"); time.sleep(3)
        check('opening it from a section fills the test, description and section',
              pg.input_value('#ibTest') == fx['mock_sid'] and pg.input_value('#ibDesc') == str(MOCK) and pg.input_value('#ibSection') == 'SEC1',
              f"{pg.input_value('#ibTest')} {pg.input_value('#ibDesc')} {pg.input_value('#ibSection')}")
        opts = pg.locator('#ibTest option').all_inner_texts()
        check('communication and coding tests are not offered for images', not any('comm block' in o or 'coding block' in o for o in opts))
        check('no script errors on any page', not errs, '; '.join(errs)[:200])
        check('no plain browser pop-ups were used', not natives, str(natives)[:120])
        b.close()
finally:
    made_images |= uploaded_images()
    selftest_mocktest.remove(db)
    removed = 0
    for rel in made_images:
        if rel.startswith('coding:'):
            path = Path(f'{ROOT}/admin_app/uploads/coding_questions') / rel[7:]
        else:
            path = Path(f'{ROOT}/admin_app/uploads/images') / os.path.basename(rel)
        if (rel.startswith('coding:') or rel.startswith('/static/uploads/images/')) and path.is_file():
            path.unlink(); removed += 1
        if rel.startswith('coding:') or rel.startswith('/static/uploads/images/'):
            published = ('coding_questions/' + rel[7:]) if rel.startswith('coding:') else ('images/' + os.path.basename(rel))
            db("DELETE FROM shared_file_chunks WHERE path=%s", (published,))
            db("DELETE FROM shared_files WHERE path=%s", (published,))
            try: os.remove(f'{ROOT}/user_app/uploads/{published}')
            except OSError: pass
    left = db("SELECT (SELECT COUNT(*) FROM test_description WHERE test_key LIKE 'free_selftest%%' OR subject_title LIKE 'SELFTEST%%') a,"
              " (SELECT COUNT(*) FROM comm_description WHERE test_key LIKE 'free_selftest%%') b,"
              " (SELECT COUNT(*) FROM course_content WHERE section_id LIKE 'SELFTEST%%') c,"
              " (SELECT COUNT(*) FROM cp_tests WHERE test_key LIKE 'free_selftest%%') d")[0]
    check('SELFTEST rows removed', sum(left.values()) == 0, str(left))
    check(f'uploaded test images removed ({removed})', True)
    check('your own tests and questions are untouched', snapshot() == before)

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
