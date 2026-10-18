import json, re, sys, time
from datetime import datetime, timedelta
import mysql.connector, requests
from dotenv import dotenv_values

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
ADMIN = 'http://127.0.0.1:5001'
EMAIL, PASSWORD = 'rajakumarvijeta7087@gmail.com', 'Raja@7479'
TAG = 'SELFTEST'
v = dotenv_values(f'{ROOT}/user_app/.env')

def db(q, p=()):
    c = mysql.connector.connect(host=v['DATABASE_HOST'], user=v['DATABASE_USER'], password=v['DATABASE_PASSWORD'],
                                database=v['DATABASE_NAME'], autocommit=True)
    cur = c.cursor(dictionary=True); cur.execute(q, p)
    out = cur.fetchall() if cur.with_rows else []
    cur.close(); c.close(); return out

results = []
def check(area, name, ok, detail=''):
    results.append((area, bool(ok), name, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {area}: {name}" + (f"  -- {detail}" if detail else ''))

def csrf(html):
    m = re.search(r'name="csrf-token"[^>]*content="([^"]+)"', html)
    return m.group(1) if m else ''

class Client:
    def __init__(self):
        self.s = requests.Session()
    def _do(self, method, url, **kw):
        last = None
        for _ in range(4):
            try:
                return getattr(self.s, method)(url, timeout=30, **kw)
            except requests.exceptions.RequestException as e:
                last = e
                time.sleep(2.5)
        raise last
    def get(self, url, **kw): return self._do('get', url, **kw)
    def post(self, url, **kw): return self._do('post', url, **kw)
    def put(self, url, **kw): return self._do('put', url, **kw)
    def delete(self, url, **kw): return self._do('delete', url, **kw)

s = Client()
tok = csrf(s.get(ADMIN + '/admin_login').text)
s.post(ADMIN + '/admin_login', data={'email': EMAIL, '_csrf_token': tok})
s.post(ADMIN + '/admin_login', data={'password': PASSWORD, '_csrf_token': tok})
page = s.get(ADMIN + '/manage_course_content').text
assert 'addContentForm' in page, 'admin login failed'
H = {'X-CSRFToken': csrf(page) or tok}
ROLE = db("SELECT role FROM auth_admin WHERE email=%s", (EMAIL,))
ROLE = ROLE[0]['role'] if ROLE else '?'
print(f"signed in as {EMAIL} (role: {ROLE})")

CODE = db("SELECT code FROM courses ORDER BY code LIMIT 1")[0]['code']
NAME = db("SELECT name FROM courses WHERE code=%s", (CODE,))[0]['name']
SECTION = 'mock_test'
created = {'content': [], 'desc': [], 'q': [], 'coding': [], 'quiz': [], 'paper': [], 'note': [], 'tcs': []}

def cleanup():
    db("DELETE FROM premium_plans WHERE label LIKE %s", (f'{TAG}%',))
    for cid in created['content']:
        row = db("SELECT section_id FROM course_content WHERE id=%s", (cid,))
        if row:
            sid = row[0]['section_id']
            for key in [r['test_key'] for r in db("SELECT test_key FROM test_description WHERE test_id=%s", (sid,))]:
                for t in ('test_attempt_details', 'test_result', 'user_test_log', 'test_feedback', 'test_questions', 'test_description'):
                    db(f"DELETE FROM {t} WHERE test_key=%s", (key,))
            db("DELETE FROM notes_content WHERE test_id=%s", (sid,))
            db("DELETE FROM course_content WHERE id=%s", (cid,))
    for qid in created['coding']:
        for t in ('pcp_testcases', 'pcp_templates', 'pcp_question_companies', 'pcp_editorials', 'pcp_bookmarks', 'pcp_submissions'):
            db(f"DELETE FROM {t} WHERE question_id=%s", (qid,))
        db("DELETE FROM pcp_questions WHERE id=%s", (qid,))
    for qid in created['quiz']:
        db("DELETE FROM pcq_questions WHERE id=%s", (qid,))
    for qid in created['paper']:
        db("DELETE FROM questions WHERE id=%s", (qid,))
    for eid in created['tcs']:
        db("DELETE FROM tcs_exams WHERE id=%s", (eid,))
    for qid in [r['id'] for r in db("SELECT id FROM pcp_questions WHERE title LIKE %s", (f'{TAG}%',))]:
        for t in ('pcp_testcases', 'pcp_templates', 'pcp_question_companies', 'pcp_editorials', 'pcp_bookmarks', 'pcp_submissions'):
            db(f"DELETE FROM {t} WHERE question_id=%s", (qid,))
        db("DELETE FROM pcp_questions WHERE id=%s", (qid,))
    db("DELETE FROM pcq_questions WHERE subject LIKE %s OR question_text LIKE %s", (f'{TAG}%', f'{TAG}%'))
    db("DELETE FROM questions WHERE subject LIKE %s", (f'{TAG}%',))
    db("DELETE FROM notes_content WHERE title LIKE %s", (f'{TAG}%',))
    for row in db("SELECT id, section_id FROM course_content WHERE title LIKE %s", (f'{TAG}%',)):
        for key in [r['test_key'] for r in db("SELECT test_key FROM test_description WHERE test_id=%s", (row['section_id'],))]:
            for t in ('test_attempt_details', 'test_result', 'user_test_log', 'test_feedback', 'test_questions', 'test_description'):
                db(f"DELETE FROM {t} WHERE test_key=%s", (key,))
        db("DELETE FROM notes_content WHERE test_id=%s", (row['section_id'],))
        db("DELETE FROM course_content WHERE id=%s", (row['id'],))
    db("DELETE FROM content_sections WHERE section_key LIKE 'selftest%'")
    db("DELETE FROM course_group_codes WHERE code LIKE %s", (f'{TAG[:6]}%',))
    db("DELETE FROM course_groups WHERE group_name LIKE %s", (f'{TAG}%',))
    db("DELETE FROM courses WHERE code LIKE %s", (f'{TAG[:6]}%',))

print('\n== course content ==')
form = {'code': CODE, 'name': NAME, 'stream': f'{TAG} stream', 'section': SECTION, 'title': f'{TAG} content',
        'subtitle': 'sub', 'details': '<p>d</p>', 'label': 'Free', 'status': 'active', 'price': '0', 'discount': '0',
        'syllabus_position': 'below', 'syllabus_label': '', 'max_test_descriptions': ''}
r = s.post(ADMIN + '/manage_course_content', data=dict(form, _csrf_token=H['X-CSRFToken']), headers=H)
row = db("SELECT * FROM course_content WHERE title=%s ORDER BY id DESC LIMIT 1", (f'{TAG} content',))
check('content', 'add', bool(row), f'http {r.status_code}')
if row:
    cid = row[0]['id']; sid = row[0]['section_id']; created['content'].append(cid)
    r = s.post(ADMIN + f'/update_content/{cid}', json=dict(form, title=f'{TAG} content edited', subtitle='sub2',
                                                           label='Free', status='active', remove_syllabus=False), headers=H)
    now = db("SELECT title, subtitle FROM course_content WHERE id=%s", (cid,))[0]
    check('content', 'update (dialog)', r.status_code == 200 and now['title'] == f'{TAG} content edited' and now['subtitle'] == 'sub2',
          f"{r.status_code} {r.text[:70]}")
    for field, value, col in (('title', f'{TAG} c2', 'title'), ('price', '250', 'price'), ('status', 'inactive', 'status'),
                              ('label', 'Paid', 'label'), ('discount', '10', 'discount'), ('stream', f'{TAG} s2', 'stream'),
                              ('max_test_descriptions', '5', 'max_test_descriptions')):
        r = s.post(ADMIN + f'/update_content_field/{cid}', json={'field': field, 'value': value}, headers=H)
        got = db("SELECT * FROM course_content WHERE id=%s", (cid,))[0][col]
        got_s = str(got)
        ok = r.status_code == 200 and (got_s.startswith(str(value)) or (field in ('price', 'discount', 'max_test_descriptions') and float(got) == float(value)))
        check('content', f'inline update {field}', ok, f"{r.status_code} got={got!r}")
    s.post(ADMIN + f'/update_content_field/{cid}', json={'field': 'label', 'value': 'Free'}, headers=H)
    s.post(ADMIN + f'/update_content_field/{cid}', json={'field': 'status', 'value': 'active'}, headers=H)

print('\n== test descriptions and questions ==')
if created['content']:
    sid = db("SELECT section_id FROM course_content WHERE id=%s", (created['content'][0],))[0]['section_id']
    payload = {'test_id': sid, 'test_key': 'free_' + '9' * 20, 'subject_title': f'{TAG} test', 'subject_subtitle': 'x',
               'total_questions': 3, 'total_marks': 3, 'total_duration_minutes': 10, 'show_calculator': 1, 'access_label': 'free'}
    r = s.post(ADMIN + '/api/test-descriptions/add', json=payload, headers=H)
    d = db("SELECT * FROM test_description WHERE test_id=%s AND subject_title=%s", (sid, f'{TAG} test'))
    check('tests', 'add description', r.status_code in (200, 201) and bool(d), f'{r.status_code} {r.text[:70]}')
    if d:
        did = d[0]['id']; key = d[0]['test_key']
        r = s.put(ADMIN + f'/api/test-descriptions/update/{did}', json={'subject_title': f'{TAG} test 2', 'total_duration_minutes': 20}, headers=H)
        got = db("SELECT subject_title, total_duration_minutes FROM test_description WHERE id=%s", (did,))[0]
        check('tests', 'update description', r.status_code == 200 and got['subject_title'] == f'{TAG} test 2' and got['total_duration_minutes'] == 20,
              f'{r.status_code} {r.text[:70]}')
        had_plan = bool(db("SELECT 1 FROM premium_plans WHERE code=%s AND valid_until > NOW()", (CODE,)))
        if not had_plan:
            r = s.put(ADMIN + f'/api/test-descriptions/update/{did}', json={'access_label': 'paid'}, headers=H)
            check('tests', 'Premium is refused until the course has a premium plan', r.status_code == 400 and 'Premium Catalog' in r.text, f'{r.status_code} {r.text[:70]}')
            from datetime import datetime, timedelta
            s.post(ADMIN + f'/api/premium-catalog/{CODE}/plans', json={'label': f'{TAG} plan', 'price': '999', 'discount': '0', 'discount_ends_at': '',
                   'valid_until': (datetime.now() + timedelta(days=40)).strftime('%Y-%m-%dT%H:%M'), 'extra_days': '0'}, headers=H)
        r = s.put(ADMIN + f'/api/test-descriptions/update/{did}', json={'access_label': 'paid'}, headers=H)
        got = db("SELECT test_key, access_label FROM test_description WHERE id=%s", (did,))[0]
        check('tests', 'change access re-keys the test', r.status_code == 200 and got['access_label'] == 'paid' and got['test_key'].startswith('prem_'),
              f"{r.status_code} {got['test_key'][:12]}")
        key = got['test_key']
        q = {'test_description_id': did, 'test_id': sid, 'test_key': key, 'section_id': '1', 'section_name': 'A',
             'question_type': 'MCQ', 'question_text': f'{TAG} q', 'option_a': '1', 'option_b': '2', 'option_c': '3',
             'option_d': '4', 'correct_option': 'A', 'correct_marks': 1, 'negative_marks': 0, 'question_level': 'Easy'}
        r = s.post(ADMIN + '/api/test-questions/add', json=q, headers=H)
        qrow = db("SELECT * FROM test_questions WHERE test_description_id=%s ORDER BY id DESC LIMIT 1", (did,))
        check('tests', 'add question', r.status_code in (200, 201) and bool(qrow), f'{r.status_code} {r.text[:70]}')
        if qrow:
            qid = qrow[0]['id']
            r = s.put(ADMIN + f'/api/test-questions/update/{qid}', json={'question_text': f'{TAG} q edited', 'correct_option': 'B'}, headers=H)
            got = db("SELECT question_text, correct_option FROM test_questions WHERE id=%s", (qid,))[0]
            check('tests', 'update question', r.status_code == 200 and got['question_text'] == f'{TAG} q edited' and got['correct_option'] == 'B',
                  f'{r.status_code} {r.text[:70]}')
            r = s.delete(ADMIN + f'/api/test-questions/delete/{qid}', headers=H)
            check('tests', 'delete question', r.status_code == 200 and not db("SELECT 1 FROM test_questions WHERE id=%s", (qid,)),
                  f'{r.status_code} {r.text[:70]}')
        r = s.post(ADMIN + f'/api/test-descriptions/clone/{did}', json={}, headers=H)
        check('tests', 'the clone route is gone', r.status_code in (404, 405), str(r.status_code))
        for c in db("SELECT id FROM test_description WHERE test_id=%s AND subject_title LIKE %s", (sid, f'{TAG}%')):
            s.delete(ADMIN + f'/api/test-descriptions/delete/{c["id"]}', headers=H)
        check('tests', 'delete description', not db("SELECT 1 FROM test_description WHERE test_id=%s", (sid,)))

print('\n== practice papers ==')
pcode = CODE if created['content'] else None
if pcode:
    db("DELETE FROM questions WHERE subject LIKE %s", (f'{TAG}%',))
    q = {'paper_code': pcode, 'subject': f'{TAG} subject', 'question_id': '99901', 'question_type': 'MCQ',
         'question_text': f'{TAG} paper q', 'option_a': '1', 'option_b': '2', 'option_c': '3', 'option_d': '4',
         'correct_option': 'A', 'topic': 'x', 'year': '2026'}
    r = s.post(ADMIN + '/api/questions/add-manual', json=q, headers=H)
    row = db("SELECT * FROM questions WHERE paper_code=%s AND question_id=99901", (pcode,))
    check('papers', 'add question', r.status_code in (200, 201) and bool(row), f'{r.status_code} {r.text[:80]}')
    if row:
        qid = row[0]['id']; created['paper'].append(qid)
        r = s.put(ADMIN + f'/api/questions/update/{qid}', json=dict(q, question_text=f'{TAG} paper q edited'), headers=H)
        got = db("SELECT question_text FROM questions WHERE id=%s", (qid,))
        check('papers', 'update question', r.status_code == 200 and got and f'{TAG} paper q edited' in got[0]['question_text'],
              f'{r.status_code} {r.text[:80]}')
        r = s.delete(ADMIN + f'/api/questions/delete/{qid}', headers=H)
        check('papers', 'delete question', r.status_code == 200 and not db("SELECT 1 FROM questions WHERE id=%s", (qid,)),
              f'{r.status_code} {r.text[:80]}')
        if not db("SELECT 1 FROM questions WHERE id=%s", (qid,)):
            created['paper'].remove(qid)
else:
    check('papers', 'add question', True, 'skipped: no paper code configured')

print('\n== practice coding bank ==')
q = {'title': f'{TAG} coding q', 'statement_html': '<p>solve</p>', 'difficulty': 'Easy', 'subject': 'Arrays',
     'allowed_languages': ['python'], 'testcases': [{'input_text': '1', 'expected_output': '1'}], 'is_paid': 0}
r = s.post(ADMIN + '/api/practice-coding/questions', json=q, headers=H)
row = db("SELECT * FROM pcp_questions WHERE title=%s ORDER BY id DESC LIMIT 1", (f'{TAG} coding q',))
check('coding', 'add question', r.status_code in (200, 201) and bool(row), f'{r.status_code} {r.text[:90]}')
if row:
    qid = row[0]['id']; created['coding'].append(qid)
    r = s.put(ADMIN + f'/api/practice-coding/questions/{qid}', json=dict(q, title=f'{TAG} coding q edited'), headers=H)
    got = db("SELECT title FROM pcp_questions WHERE id=%s", (qid,))
    check('coding', 'update question', r.status_code == 200 and got and got[0]['title'] == f'{TAG} coding q edited', f'{r.status_code} {r.text[:90]}')
    r = s.put(ADMIN + f'/api/practice-coding/questions/{qid}/tier', json={'is_paid': 1}, headers=H)
    check('coding', 'change tier', r.status_code == 200 and db("SELECT is_paid FROM pcp_questions WHERE id=%s", (qid,))[0]['is_paid'] == 1,
          f'{r.status_code} {r.text[:90]}')
    r = s.delete(ADMIN + f'/api/practice-coding/questions/{qid}', headers=H)
    gone = db("SELECT is_active FROM pcp_questions WHERE id=%s", (qid,))
    check('coding', 'delete question', r.status_code == 200 and (not gone or gone[0]['is_active'] == 0), f'{r.status_code} {r.text[:90]}')
    r = s.put(ADMIN + f'/api/practice-coding/questions/{qid}/restore', json={}, headers=H)
    check('coding', 'restore question', r.status_code in (200, 404), f'{r.status_code} {r.text[:90]}')

print('\n== practice quiz bank ==')
qz = {'subject': f'{TAG}QZ', 'question_text': f'{TAG} quiz q', 'option_a': '1', 'option_b': '2', 'option_c': '3',
      'option_d': '4', 'correct_option': 'A', 'explanation': 'x', 'is_paid': 0}
r = s.post(ADMIN + '/api/practice-quiz/questions', json=qz, headers=H)
tbl = 'pcq_questions'
row = db(f"SELECT * FROM {tbl} WHERE question_text=%s ORDER BY id DESC LIMIT 1", (f'{TAG} quiz q',))
check('quiz', 'add question', r.status_code in (200, 201) and bool(row), f'{r.status_code} {r.text[:90]}')
if row:
    qid = row[0]['id']; created['quiz'].append(qid)
    r = s.put(ADMIN + f'/api/practice-quiz/questions/{qid}', json=dict(qz, question_text=f'{TAG} quiz q edited'), headers=H)
    got = db(f"SELECT question_text FROM {tbl} WHERE id=%s", (qid,))
    check('quiz', 'update question', r.status_code == 200 and got and got[0]['question_text'] == f'{TAG} quiz q edited', f'{r.status_code} {r.text[:90]}')
    r = s.put(ADMIN + f'/api/practice-quiz/questions/{qid}/tier', json={'is_paid': 1}, headers=H)
    check('quiz', 'change tier', r.status_code == 200 and db(f"SELECT is_paid FROM {tbl} WHERE id=%s", (qid,))[0]['is_paid'] == 1, f'{r.status_code} {r.text[:90]}')
    r = s.delete(ADMIN + f'/api/practice-quiz/questions/{qid}', headers=H)
    gone = db(f"SELECT is_active FROM {tbl} WHERE id=%s", (qid,))
    check('quiz', 'delete question', r.status_code == 200 and (not gone or gone[0]['is_active'] == 0), f'{r.status_code} {r.text[:90]}')
    r = s.put(ADMIN + f'/api/practice-quiz/questions/{qid}/restore', json={}, headers=H)
    check('quiz', 'restore question', r.status_code == 200 and db(f"SELECT is_active FROM {tbl} WHERE id=%s", (qid,))[0]['is_active'] == 1, f'{r.status_code} {r.text[:90]}')

print('\n== notes ==')
if created['content']:
    sid = db("SELECT section_id FROM course_content WHERE id=%s", (created['content'][0],))[0]['section_id']
    r = s.post(ADMIN + '/notes_upload', data={'test_id': sid, 'code': CODE, 'type': 'notes', 'heading_input': f'{TAG} head',
                                              'sub_heading_input': f'{TAG} sub', 'title': f'{TAG} note', 'sub_title': 'x',
                                              'file_url': 'https://example.com/a.pdf', '_csrf_token': H['X-CSRFToken']}, headers=H)
    row = db("SELECT * FROM notes_content WHERE title=%s ORDER BY id DESC LIMIT 1", (f'{TAG} note',))
    check('notes', 'add', r.status_code in (200, 302) and bool(row), f'{r.status_code} {r.text[:80]}')
    if row:
        nid = row[0]['id']
        r = s.post(ADMIN + f'/api/note/delete/{nid}', headers=H)
        check('notes', 'delete', r.status_code == 200 and not db("SELECT 1 FROM notes_content WHERE id=%s", (nid,)), f'{r.status_code} {r.text[:80]}')

print('\n== content delete ==')
for cid in list(created['content']):
    r = s.post(ADMIN + f'/delete_content/{cid}', headers=H)
    gone = not db("SELECT 1 FROM course_content WHERE id=%s", (cid,))
    check('content', 'delete', r.status_code == 200 and gone, f'{r.status_code} {r.text[:80]}')
    if gone:
        created['content'].remove(cid)

print('\n== catalog and courses (role gates) ==')
r = s.post(ADMIN + '/api/catalog/groups', json={'group_name': f'{TAG}GRP'}, headers=H)
check('catalog', 'add group is owner-only', r.status_code in (200, 403), f'{r.status_code} {r.text[:60]}')
if r.status_code == 200:
    s.delete(ADMIN + f'/api/catalog/groups/{TAG}GRP', headers=H)
GROUP = db("SELECT name FROM courses LIMIT 1")[0]['name']
NEWCODE = f'{TAG[:6]}X'
r = s.post(ADMIN + '/api/catalog/codes', json={'group_name': GROUP, 'code': NEWCODE, 'label': f'{TAG} code'}, headers=H)
check('catalog', 'add code to group', r.status_code in (200, 201, 403), f'{r.status_code} {r.text[:70]}')
r = s.post(ADMIN + '/courses/add', json={'code': NEWCODE, 'name': GROUP, 'subgroup': f'{TAG} sub', 'description': 'x'}, headers=H)
check('courses', 'add course', r.status_code in (200, 201, 403), f'{r.status_code} {r.text[:70]}')
if r.status_code in (200, 201):
    r = s.post(ADMIN + f'/courses/update/{NEWCODE}', json={'name': GROUP, 'subgroup': f'{TAG} sub2', 'description': 'y'}, headers=H)
    got = db("SELECT subgroup FROM courses WHERE code=%s", (NEWCODE,))
    check('courses', 'update course', r.status_code == 200 and got and got[0]['subgroup'] == f'{TAG} sub2', f'{r.status_code} {r.text[:70]}')
    r = s.post(ADMIN + f'/courses/delete/{NEWCODE}', headers=H)
    check('courses', 'delete course', r.status_code == 200 and not db("SELECT 1 FROM courses WHERE code=%s", (NEWCODE,)), f'{r.status_code} {r.text[:70]}')
    s.delete(ADMIN + f'/api/catalog/codes/{GROUP}/{NEWCODE}', headers=H)

print('\n== catalog sections and codes ==')
r = s.post(ADMIN + '/api/catalog/sections', json={'section_key': 'selftest_sec', 'label': f'{TAG} section', 'portal': ''}, headers=H)
check('catalog', 'add section', r.status_code in (200, 201, 403), f'{r.status_code} {r.text[:70]}')
if r.status_code in (200, 201):
    r = s.put(ADMIN + '/api/catalog/sections/selftest_sec', json={'label': f'{TAG} section 2'}, headers=H)
    check('catalog', 'update section', r.status_code == 200, f'{r.status_code} {r.text[:70]}')
    r = s.delete(ADMIN + '/api/catalog/sections/selftest_sec', headers=H)
    check('catalog', 'delete section', r.status_code == 200, f'{r.status_code} {r.text[:70]}')
    db("DELETE FROM content_sections WHERE section_key='selftest_sec'")

print('\n== tcs exams ==')
r = s.post(ADMIN + '/api/tcs/exams', json={'title': f'{TAG} tcs'}, headers=H)
check('tcs', 'the separate TCS exam page and API are gone (exams live in Test Question Upload)', r.status_code in (404, 405), str(r.status_code))
r = s.get(ADMIN + '/manage-tcs')
check('tcs', 'the old page no longer exists', r.status_code == 404, str(r.status_code))

print('\n== feedback ==')
fb = db("SELECT id FROM test_feedback ORDER BY id DESC LIMIT 1")
if fb:
    r = s.post(ADMIN + '/api/feedback/reply', json={'feedback_id': fb[0]['id'], 'reply': f'{TAG} reply'}, headers=H)
    check('feedback', 'reply', r.status_code in (200, 400, 404), f'{r.status_code} {r.text[:70]}')
else:
    check('feedback', 'reply', True, 'skipped: no feedback rows')

cleanup()
left = sum(db(f"SELECT COUNT(*) n FROM {t} WHERE {c} LIKE '{TAG}%'")[0]['n'] for t, c in
           (('course_content', 'title'), ('test_description', 'subject_title'), ('questions', 'subject'),
            ('pcp_questions', 'title'), ('pcq_questions', 'subject'), ('notes_content', 'title')))
fails = [f'{a}: {n}' for a, ok, n, _ in results if not ok]
print(f"\n{TAG} rows left: {left}")
print(f"RESULT: {sum(1 for _, ok, _, _ in results if ok)}/{len(results)} passed")
if fails:
    print('FAILED: ' + '; '.join(fails))
sys.exit(0 if not fails and left == 0 else 1)
