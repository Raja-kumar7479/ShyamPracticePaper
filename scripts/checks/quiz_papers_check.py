import io, json, os, re, sys, time
from pathlib import Path
import mysql.connector, requests
from dotenv import dotenv_values
from openpyxl import Workbook
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
ADMIN = 'http://127.0.0.1:5001'
ADMIN_EMAIL, ADMIN_PASSWORD = 'rajakumarvijeta7087@gmail.com', 'Raja@7479'
TAG = 'SELFTEST'
sys.path.insert(0, f'{ROOT}/scripts/checks')
import selftest_mocktest
WORK = Path(f'{ROOT}/scripts/checks/__pycache__/quiz_papers_files')
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


def xlsx(path, header, rows):
    wb = Workbook(); ws = wb.active; ws.append(header)
    for r in rows: ws.append(r)
    wb.save(path); return str(path)


def csvf(path, header, rows):
    import csv
    with open(path, 'w', newline='') as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)
    return str(path)


def question_image(path, label):
    im = Image.new('RGB', (900, 700), 'white'); d = ImageDraw.Draw(im)
    d.text((80, 80), f'{label}: What is 2 + 2 ?', fill='black')
    for i, t in enumerate(['(A) 3', '(B) 4', '(C) 5', '(D) 6']):
        d.text((100, 220 + i * 90), t, fill='black')
    im.save(path); return str(path)


def cleanup():
    db("DELETE FROM pcq_questions WHERE subject LIKE %s OR question_text LIKE %s", (f'{TAG}%', f'{TAG}%'))
    db("DELETE FROM questions WHERE subject LIKE %s OR question_text LIKE %s", (f'{TAG}%', f'{TAG}%'))
    db("DELETE FROM practice_questions WHERE title LIKE %s", (f'{TAG}%',))


cleanup()
selftest_mocktest.remove(db)
fx = selftest_mocktest.setup(db)
imgs = []
CODE = fx['code']

s = requests.Session()
def csrf(html):
    m = re.search(r'name="csrf-token"[^>]*content="([^"]+)"', html)
    return m.group(1) if m else ''
tok = csrf(s.get(ADMIN + '/admin_login').text)
s.post(ADMIN + '/admin_login', data={'email': ADMIN_EMAIL, '_csrf_token': tok})
s.post(ADMIN + '/admin_login', data={'password': ADMIN_PASSWORD, '_csrf_token': tok})
page = s.get(ADMIN + '/manage-practice-quiz').text
assert 'qzSaveBtn' in page, 'admin login failed'
H = {'X-CSRFToken': csrf(page) or tok}
def api(method, path, **kw):
    return getattr(s, method)(ADMIN + path, headers=H, timeout=60, **kw)

QCOLS = ['subject', 'question', 'option_a', 'option_b', 'option_c', 'option_d', 'correct', 'explanation', 'access']
PCOLS = ['question_id', 'question_type', 'year', 'paper_set', 'subject', 'topic', 'question_text',
         'option_a', 'option_b', 'option_c', 'option_d', 'correct_option', 'answer_text', 'explanation_link']

try:
    print('\n== quiz bank (API) ==')
    qz = {'subject': f'{TAG}QZ', 'question_text': f'{TAG} quiz one', 'option_a': '1', 'option_b': '2', 'option_c': '3',
          'option_d': '4', 'correct_option': 'A', 'explanation': 'x', 'is_paid': 0}
    r = api('post', '/api/practice-quiz/questions', json=qz)
    check('a quiz question is added by hand', r.status_code in (200, 201), r.text[:80])
    r = api('post', '/api/practice-quiz/questions', json=dict(qz, question_text=f'<p>{TAG}   QUIZ one </p>'))
    n = db("SELECT COUNT(*) n FROM pcq_questions WHERE subject=%s", (f'{TAG}QZ',))[0]['n']
    check('the same question again (spacing/case/tags differ) is refused with 409 and not stored', r.status_code == 409 and n == 1, f'{r.status_code} n={n} {r.text[:90]}')
    check('the refusal names where it already is', 'already in the bank' in r.text and '#' in r.text, r.text[:120])
    r = api('post', '/api/practice-quiz/questions', json=dict(qz, question_text=f'{TAG} quiz one', option_d='5'))
    check('same text with a different option is a different question and is added', r.status_code in (200, 201), r.text[:80])
    ids = [x['id'] for x in db("SELECT id FROM pcq_questions WHERE subject=%s ORDER BY id", (f'{TAG}QZ',))]
    r = api('put', f'/api/practice-quiz/questions/{ids[1]}', json=dict(qz, question_text=f'{TAG} quiz one'))
    check('editing a question into a copy of another one is refused', r.status_code == 409, f'{r.status_code} {r.text[:80]}')
    r = api('put', f'/api/practice-quiz/questions/{ids[1]}', json=dict(qz, question_text=f'{TAG} quiz two', option_d='5'))
    check('editing a question to a new text works', r.status_code == 200, r.text[:80])

    r = api('get', '/api/practice-quiz/bulk/template?fmt=xlsx')
    check('an Excel template downloads', r.status_code == 200 and r.content[:2] == b'PK', str(r.status_code))
    r = api('get', '/api/practice-quiz/bulk/template')
    check('the CSV template still downloads', r.status_code == 200 and r.text.startswith('subject,'), r.text[:40])

    rows = [[f'{TAG}QZ', f'{TAG} sheet q{i}', 'a', 'b', 'c', 'd', 'B', 'why', 'free'] for i in range(1, 4)]
    rows.append([f'{TAG}QZ', f'{TAG} quiz one', '1', '2', '3', '4', 'A', 'x', 'free'])
    rows.append([f'{TAG}QZ', f'{TAG} sheet q1', 'a', 'b', 'c', 'd', 'B', 'why', 'free'])
    f = xlsx(WORK / 'quiz.xlsx', QCOLS, rows)
    r = api('post', '/api/practice-quiz/bulk/upload', files={'file': ('quiz.xlsx', open(f, 'rb'), 'application/octet-stream')})
    d = r.json() if r.headers.get('content-type', '').startswith('application/json') else {}
    n = db("SELECT COUNT(*) n FROM pcq_questions WHERE question_text LIKE %s", (f'{TAG} sheet q%',))[0]['n']
    check('an Excel sheet uploads: 3 new rows stored, the stored one and the in-file repeat skipped', r.status_code == 200 and d.get('imported') == 3 and len(d.get('skipped', [])) == 2 and n == 3,
          f"{r.status_code} imported={d.get('imported')} skipped={len(d.get('skipped', []))} n={n}")
    r = api('post', '/api/practice-quiz/bulk/upload', files={'file': ('quiz.xlsx', open(f, 'rb'), 'application/octet-stream')})
    d = r.json(); n2 = db("SELECT COUNT(*) n FROM pcq_questions WHERE subject=%s", (f'{TAG}QZ',))[0]['n']
    check('uploading the same sheet again adds nothing and says so', r.status_code == 200 and d.get('imported') == 0 and n2 == n + 2 and 'already' in d.get('message', ''), f"{d.get('message')}")
    bad = rows[:1] + [[f'{TAG}QZ', f'{TAG} sheet new', 'a', 'b', 'c', 'd', 'E', '', 'free'], [f'{TAG}QZ', f'{TAG} sheet new2', 'a', 'b', 'c', 'd', 'A', '', 'free']]
    f2 = csvf(WORK / 'quiz_bad.csv', QCOLS, bad)
    r = api('post', '/api/practice-quiz/bulk/upload', files={'file': ('quiz_bad.csv', open(f2, 'rb'), 'text/csv')})
    n3 = db("SELECT COUNT(*) n FROM pcq_questions WHERE question_text LIKE %s", (f'{TAG} sheet new%',))[0]['n']
    check('a CSV with one bad row (answer E) stores nothing at all, even the good rows', r.status_code == 400 and n3 == 0 and 'Row 3' in r.text, f'{r.status_code} n={n3} {r.text[:120]}')
    f3 = csvf(WORK / 'quiz_nl.csv', QCOLS, [[f'{TAG}QZ', f'{TAG} line1\\nline2', 'a', 'b', 'c', 'd', 'A', 'e1\\\\ne2', 'paid']])
    r = api('post', '/api/practice-quiz/bulk/upload', files={'file': ('quiz_nl.csv', open(f3, 'rb'), 'text/csv')})
    row = db("SELECT question_text, explanation, is_paid FROM pcq_questions WHERE question_text LIKE %s", (f'{TAG} line1%',))
    check('\\n in a cell becomes a line break, \\\\n stays literal, access paid is kept', bool(row) and row[0]['question_text'] == f'{TAG} line1\nline2' and row[0]['explanation'] == 'e1\\ne2' and row[0]['is_paid'] == 1, str(row)[:120])
    r = api('post', '/api/practice-quiz/bulk/upload', files={'file': ('quiz.txt', io.BytesIO(b'x'), 'text/plain')})
    check('a .txt upload is refused with a clear message', r.status_code == 400 and '.xlsx' in r.text, r.text[:80])

    print('\n== practice papers (API) ==')
    base = {'paper_code': CODE, 'subject': f'{TAG} subject', 'question_type': 'MCQ', 'question_text': f'{TAG} paper q1',
            'option_a': '1', 'option_b': '2', 'option_c': '3', 'option_d': '4', 'correct_option': 'A', 'topic': 'x', 'year': '2026'}
    r = api('post', '/api/questions/add-manual', json=dict(base, question_id=''))
    d = r.json()
    q1 = db("SELECT * FROM questions WHERE paper_code=%s AND subject=%s", (CODE, f'{TAG} subject'))
    check('a question added with an empty number gets the next number in the paper', r.status_code == 201 and len(q1) == 1 and d.get('question_id') == q1[0]['question_id'], f'{r.status_code} {r.text[:100]}')
    first = q1[0]['question_id']
    r = api('post', '/api/questions/add-manual', json=dict(base, question_id='', question_text=f'{TAG} paper q2'))
    check('the next one gets number + 1 and the reply says the next number', r.status_code == 201 and r.json().get('question_id') == first + 1 and r.json().get('next_question_id') == first + 2, r.text[:100])
    check('no DB id text in the add message', 'DB ID' not in r.text and 'added' in r.text, r.text[:80])
    r = api('post', '/api/questions/add-manual', json=dict(base, question_id='', question_text=f'<p>{TAG}  PAPER q1</p>'))
    check('same content under a new number is refused (409) and names the existing number', r.status_code == 409 and f'#{first}' in r.text, f'{r.status_code} {r.text[:100]}')
    r = api('post', '/api/questions/add-manual', json=dict(base, question_id=first, question_text=f'{TAG} paper other'))
    check('a used number with a different question is refused', r.status_code == 409 and 'already exists' in r.text, r.text[:100])
    for ans, label in (('E', 'MCQ answer E'), ('AB', 'MCQ answer AB'), ('', 'empty answer')):
        r = api('post', '/api/questions/add-manual', json=dict(base, question_id='', question_text=f'{TAG} bad {ans}', correct_option=ans))
        check(f'an MCQ with {label} is refused', r.status_code == 400, f'{r.status_code} {r.text[:80]}')
    r = api('post', '/api/questions/add-manual', json=dict(base, question_id='', question_text=f'{TAG} empty opt', option_b=''))
    check('an MCQ may leave a non-answer option blank', r.status_code == 201, r.text[:80])
    base_b = dict(base, correct_option='B', option_b='')
    r = api('post', '/api/questions/add-manual', json=dict(base_b, question_id='', question_text=f'{TAG} empty opt2'))
    check('the message names the empty option', r.status_code == 400 and 'Option B' in r.text, r.text[:80])
    r = api('post', '/api/questions/add-manual', json=dict(base, question_id='', question_type='MSQ', question_text=f'{TAG} msq', correct_option='c,a'))
    got = db("SELECT correct_option FROM questions WHERE question_text=%s", (f'{TAG} msq',))
    check('an MSQ answer "c,a" is stored as AC', r.status_code == 201 and got and got[0]['correct_option'] == 'AC', f'{r.status_code} {got}')
    r = api('post', '/api/questions/add-manual', json=dict(base, question_id='', question_type='NAT', question_text=f'{TAG} nat', correct_option='abc', option_a='', option_b='', option_c='', option_d=''))
    check('a NAT answer that is not a number is refused', r.status_code == 400, r.text[:80])
    r = api('post', '/api/questions/add-manual', json=dict(base, question_id='', question_type='NAT', question_text=f'{TAG} nat', correct_option='12.5', option_a='', option_b='', option_c='', option_d=''))
    check('a NAT with a numeric answer and no options is accepted', r.status_code == 201, r.text[:80])
    r = api('post', '/api/questions/add-manual', json=dict(base, question_id='abc'))
    check('a non-numeric number is refused', r.status_code == 400, r.text[:80])
    r = api('get', f'/api/papers/next-id?paper_code={CODE}')
    mx = db("SELECT MAX(question_id) m FROM questions WHERE paper_code=%s", (CODE,))[0]['m']
    check('the next-number lookup matches max + 1', r.status_code == 200 and r.json().get('next_question_id') == mx + 1, r.text[:60])

    dbid = q1[0]['id']
    r = api('put', f'/api/questions/update/{dbid}', json=dict(base, question_id=first, correct_option='E'))
    check('editing an MCQ to answer E is refused', r.status_code == 400 and db("SELECT correct_option FROM questions WHERE id=%s", (dbid,))[0]['correct_option'] == 'A', r.text[:80])
    r = api('put', f'/api/questions/update/{dbid}', json=dict(base, question_id=first, question_text=f'{TAG} paper q2'))
    check('editing a question into a copy of another one in the paper is refused', r.status_code == 409, f'{r.status_code} {r.text[:80]}')
    r = api('put', f'/api/questions/update/{dbid}', json=dict(base, question_id=first, question_text=f'{TAG} paper q1 edited', correct_option='b'))
    got = db("SELECT question_text, correct_option FROM questions WHERE id=%s", (dbid,))[0]
    check('a valid edit saves and normalises the answer letter', r.status_code == 200 and got['question_text'] == f'{TAG} paper q1 edited' and got['correct_option'] == 'B', str(got))

    sheet_rows = [
        ['', 'MCQ', 2025, 'Set A', f'{TAG} subject', 't', f'{TAG} sheet s1', 'a', 'b', 'c', 'd', 'A', '', ''],
        ['', 'MCQ', 2025, 'Set A', f'{TAG} subject', 't', f'{TAG} sheet s2', 'a', 'b', 'c', 'd', 'b', '', ''],
        ['', 'MCQ', 2025, 'Set A', f'{TAG} subject', 't', f'{TAG} paper q2', '1', '2', '3', '4', 'A', '', ''],
        ['', 'MCQ', 2025, 'Set A', f'{TAG} subject', 't', f'{TAG} sheet s1', 'a', 'b', 'c', 'd', 'A', '', ''],
    ]
    f = xlsx(WORK / 'paper.xlsx', PCOLS, sheet_rows)
    before = db("SELECT MAX(question_id) m FROM questions WHERE paper_code=%s", (CODE,))[0]['m']
    r = api('post', '/api/questions/upload-csv', data={'paper_code': CODE}, files={'csv_file': ('paper.xlsx', open(f, 'rb'), 'application/octet-stream')})
    d = r.json()
    nums = [x['question_id'] for x in db("SELECT question_id FROM questions WHERE question_text LIKE %s ORDER BY question_id", (f'{TAG} sheet s%',))]
    check('an Excel sheet with empty numbers stores 2 new rows numbered after the last, skipping the stored one and the in-file repeat',
          r.status_code == 200 and d.get('inserted') == 2 and len(d.get('skipped', [])) == 2 and nums == [before + 1, before + 2], f"{r.status_code} {d.get('message')} nums={nums}")
    n_before = db("SELECT COUNT(*) n FROM questions WHERE paper_code=%s", (CODE,))[0]['n']
    r = api('post', '/api/questions/upload-csv', data={'paper_code': CODE}, files={'csv_file': ('paper.xlsx', open(f, 'rb'), 'application/octet-stream')})
    d = r.json(); n_after = db("SELECT COUNT(*) n FROM questions WHERE paper_code=%s", (CODE,))[0]['n']
    check('uploading the same paper sheet again stores nothing and lists each row as already present', r.status_code == 200 and d.get('inserted') == 0 and len(d.get('skipped', [])) == 4 and n_after == n_before, f"{d.get('message')} n={n_before}->{n_after}")
    bad_rows = [
        [before + 10, 'MCQ', 2025, '', f'{TAG} subject', '', f'{TAG} sheet bad ok', 'a', 'b', 'c', 'd', 'A', '', ''],
        [before + 11, 'MCQ', 2025, '', f'{TAG} subject', '', f'{TAG} sheet bad e', 'a', 'b', 'c', 'd', 'E', '', ''],
        [first, 'MCQ', 2025, '', f'{TAG} subject', '', f'{TAG} sheet bad id', 'a', 'b', 'c', 'd', 'A', '', ''],
    ]
    f2 = csvf(WORK / 'paper_bad.csv', PCOLS, bad_rows)
    r = api('post', '/api/questions/upload-csv', data={'paper_code': CODE}, files={'csv_file': ('paper_bad.csv', open(f2, 'rb'), 'text/csv')})
    d = r.json(); n_bad = db("SELECT COUNT(*) n FROM questions WHERE question_text LIKE %s", (f'{TAG} sheet bad%',))[0]['n']
    check('a sheet with a bad answer and a taken number stores nothing, not even the good row', r.status_code == 400 and n_bad == 0 and len(d.get('errors', [])) == 2, f"{r.status_code} {d.get('message')} errors={d.get('errors')}")
    check('the errors say which row and why', any('E' in e['error'] and e['row'] == 3 for e in d.get('errors', [])) and any(str(first) in e['error'] and e['row'] == 4 for e in d.get('errors', [])), str(d.get('errors'))[:200])

    img = question_image(WORK / 'p1.png', f'{TAG} image')
    r = api('post', '/api/question-image/upload', files={'image': ('p1.png', open(img, 'rb'), 'image/png')})
    url = r.json().get('url') or r.json().get('image_url') or r.json().get('path')
    mx = db("SELECT MAX(question_id) m FROM questions WHERE paper_code=%s", (CODE,))[0]['m']
    r = api('post', '/api/practice-questions/add-image', json={'paper_code': CODE, 'subject': f'{TAG} subject', 'question_type': 'MCQ', 'correct_option': 'AB',
                                                               'question_image': url, 'option_regions': {'a': {'x': 0.1, 'y': 0.3, 'w': 0.4, 'h': 0.05}, 'b': {'x': 0.1, 'y': 0.4, 'w': 0.4, 'h': 0.05}}})
    check('an image MCQ with two answers is refused', r.status_code == 400, r.text[:80])
    r = api('post', '/api/practice-questions/add-image', json={'paper_code': CODE, 'subject': f'{TAG} subject', 'question_type': 'MCQ', 'correct_option': 'B',
                                                               'question_image': url, 'option_regions': {'a': {'x': 0.1, 'y': 0.3, 'w': 0.4, 'h': 0.05}, 'b': {'x': 0.1, 'y': 0.4, 'w': 0.4, 'h': 0.05}}})
    got = db("SELECT question_id FROM questions WHERE paper_code=%s AND question_image IS NOT NULL AND subject=%s", (CODE, f'{TAG} subject'))
    check('an image question takes the next number in the paper', r.status_code == 201 and got and got[0]['question_id'] == mx + 1, f'{r.status_code} {got} {r.text[:60]}')
    imgs += [x['question_image'] for x in db("SELECT question_image FROM questions WHERE subject=%s AND question_image IS NOT NULL", (f'{TAG} subject',))]

    r = api('delete', f'/api/questions/delete/{dbid}')
    check('deleting says the question number, not the DB id', r.status_code == 200 and f'#{first}' in r.text and 'DB' not in r.text, r.text[:80])
    r = api('delete', f'/api/questions/delete/{dbid}')
    check('deleting it twice is a clean 404', r.status_code == 404, r.text[:80])

    print('\n== practice formats (API) ==')
    SECTION = f'{TAG} Topic-wise'
    fd = {'code': CODE, 'section': SECTION, 'title': f'{TAG} format', '_csrf_token': H['X-CSRFToken']}
    r = api('post', '/admin/practice_questions', data=fd)
    ok1 = r.status_code in (200, 201) and db("SELECT 1 FROM practice_questions WHERE title=%s", (f'{TAG} format',))
    r = api('post', '/admin/practice_questions', data=dict(fd, title=f'{TAG} FORMAT'))
    n = db("SELECT COUNT(*) n FROM practice_questions WHERE LOWER(title)=%s", (f'{TAG.lower()} format',))[0]['n']
    check('a practice format is added once; the same title again is refused', bool(ok1) and r.status_code == 409 and n == 1, f'{r.status_code} n={n}')

    print('\n== the pages ==')
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
        toast_cls = lambda: pg.locator('.admin-toast').last.get_attribute('class') if pg.locator('.admin-toast').count() else ''
        approve = lambda: (time.sleep(0.4), pg.click('.acf [data-acf="confirm"]'), time.sleep(1.4))
        cancel = lambda: (time.sleep(0.4), pg.click('.acf [data-acf="cancel"]'), time.sleep(0.5))
        icon_ok = lambda sel: pg.evaluate(f"(() => {{ const i = document.querySelector('{sel}'); if (!i) return 'missing'; return getComputedStyle(i, '::before').content; }})()")

        print('-- quiz bank page --')
        pg.goto(f'{ADMIN}/manage-practice-quiz'); time.sleep(1.8)
        for sel, label in (('.fa-file-arrow-up', 'upload'), ('.fa-file-excel', 'excel template'), ('#qzList .fa-pen', 'edit'), ('#qzList .fa-trash', 'delete')):
            c = icon_ok(sel)
            check(f'quiz page: the {label} icon renders', c not in ('missing', 'none', 'normal', '""'), str(c))
        pg.fill('#qzSubject', f'{TAG}QZ'); pg.fill('#qzQuestion', f'{TAG} quiz one'); pg.fill('#qzOptA', '1'); pg.fill('#qzOptB', '2'); pg.fill('#qzOptC', '3'); pg.fill('#qzOptD', '4')
        pg.check('#qzCorrect-A') if pg.locator('#qzCorrect-A').count() else pg.locator('input[name="qzCorrect"][value="A"]').check()
        pg.click('#qzSaveBtn'); time.sleep(1.5)
        check('quiz page: a duplicate typed by hand shows a red error toast (not info)', 'already in the bank' in toast() and 'danger' in toast_cls(), f'{toast_cls()} {toast()[:80]}')
        pg.select_option('#qzFilterSubject', f'{TAG}QZ') if pg.locator(f'#qzFilterSubject option[value="{TAG}QZ"]').count() else None
        time.sleep(1.0)
        first_card = pg.locator('#qzList article').first
        first_card.locator('[data-edit-q]').click(); time.sleep(0.6)
        title = pg.locator('#qzEditorTitle').inner_text()
        check('quiz page: the edit title shows the question text, not a database id', 'Editing:' in title and not re.search(r'#\d+', title), title)
        pg.fill('#qzQuestion', pg.input_value('#qzQuestion') + ' changed'); pg.click('#qzSaveBtn'); time.sleep(0.8)
        check('quiz page: saving an edit asks for approval first', dialog_open() and 'Save changes' in dialog_text(), dialog_text()[:80])
        cancel(); approve_needed = pg.locator('#qzList article').count()
        pg.click('#qzSaveBtn'); time.sleep(0.8); approve()
        check('quiz page: after approval the edit is saved', 'changed' in db("SELECT question_text FROM pcq_questions WHERE subject=%s ORDER BY id LIMIT 1", (f'{TAG}QZ',))[0]['question_text'])
        card = pg.locator('#qzList article').first
        card.locator('[data-tier-q]').click(); time.sleep(0.7)
        check('quiz page: changing Free/Paid asks for approval', dialog_open() and ('Paid' in dialog_text() or 'Free' in dialog_text()), dialog_text()[:80]); cancel()
        card.locator('[data-del-q]').click(); time.sleep(0.7)
        check('quiz page: removing asks in the approval box, not a browser popup', dialog_open() and 'Remove' in dialog_text() and not natives, dialog_text()[:80])
        approve()
        check('quiz page: after approval the question is removed (soft) and a toast confirms', db("SELECT is_active FROM pcq_questions WHERE subject=%s ORDER BY id LIMIT 1", (f'{TAG}QZ',))[0]['is_active'] == 0 and 'removed' in toast().lower(), toast())
        pg.set_input_files('#qzBulkFile', str(WORK / 'quiz.xlsx')); time.sleep(2.0)
        time.sleep(1.5); res = pg.evaluate("document.getElementById('qzBulkResult').textContent"); bb = pg.locator('#qzBulkResult').bounding_box()
        check('quiz page: uploading the sheet again keeps the row-by-row report on the page and skips stored rows', 'already in the bank' in res and 'skipped' in res and bb and bb['height'] > 20, f'{res[:100]} box={bb}')
        check('quiz page: the upload input accepts .xlsx', '.xlsx' in (pg.get_attribute('#qzBulkFile', 'accept') or ''))
        blank = pg.evaluate("Array.from(document.querySelectorAll('i.fas, i.far')).filter(i => { const c = getComputedStyle(i, '::before').content; return c === 'none' || c === 'normal' || c === '\"\"'; }).map(i => i.className)")
        check('quiz page: every icon on the page renders', not blank, str(blank)[:200])
        check('quiz page: no JavaScript errors', not errs, str(errs)[:200])

        print('-- practice coding page --')
        pg.goto(f'{ADMIN}/manage-practice-coding'); time.sleep(1.8)
        c = icon_ok('.fa-file-arrow-up')
        check('practice coding page: the upload icon renders', c not in ('missing', 'none', 'normal', '""'), str(c))
        blank = pg.evaluate("Array.from(document.querySelectorAll('i.fas, i.far')).filter(i => { const c = getComputedStyle(i, '::before').content; return c === 'none' || c === 'normal' || c === '\"\"'; }).map(i => i.className)")
        check('practice coding page: every icon on the page renders', not blank, str(blank)[:200])
        check('practice coding page: no JavaScript errors', not errs, str(errs)[:200])

        print('-- practice papers page --')
        pg.goto(f'{ADMIN}/manage-practice-papers'); time.sleep(2.0)
        pg.evaluate("window.ppShowView('manual')"); time.sleep(0.5)
        pg.select_option('#manualPaperCode', CODE); time.sleep(1.0)
        pg.fill('#manualSubject', f'{TAG} subject'); pg.click('#setManualContextBtn'); time.sleep(1.2)
        ph = pg.get_attribute('#manualQuestionId', 'placeholder') or ''
        req = pg.evaluate("document.getElementById('manualQuestionId').required")
        mx = db("SELECT MAX(question_id) m FROM questions WHERE paper_code=%s", (CODE,))[0]['m']
        check('papers page: the number field is optional and shows the next number', not req and ph == f'next: {mx + 1}', f'required={req} placeholder={ph!r}')
        pg.select_option('#manualQuestionType', 'MCQ')
        for eid, txt in (('manualQuestionText', f'{TAG} typed on page'), ('manualOptionA', 'a'), ('manualOptionB', 'b'), ('manualOptionC', 'c'), ('manualOptionD', 'd')):
            pg.locator(f'#{eid} .ql-editor').fill(txt)
        pg.fill('#manualCorrectOption', 'A') if pg.locator('#manualCorrectOption').count() else pg.select_option('#manualCorrectOption', 'A')
        pg.click('#manualQuestionForm button[type="submit"]'); time.sleep(1.6)
        got = db("SELECT question_id FROM questions WHERE question_text LIKE %s", (f'%{TAG} typed on page%',))
        check('papers page: saving with the number empty stores the next number and the message has no DB id', got and got[0]['question_id'] == mx + 1 and 'DB ID' not in pg.locator('#manualAddMessage').inner_text(), f'{got} {pg.locator("#manualAddMessage").inner_text()[:80]}')
        ph2 = pg.get_attribute('#manualQuestionId', 'placeholder') or ''
        check('papers page: the placeholder moves on to the next number', ph2 == f'next: {mx + 2}', ph2)

        pg.evaluate("window.ppShowView('search')"); time.sleep(0.5)
        pg.select_option('#searchPaperCode', CODE); time.sleep(1.0)
        pg.fill('#searchSubject', f'{TAG} subject') if pg.locator('input#searchSubject').count() else pg.select_option('#searchSubject', f'{TAG} subject')
        pg.click('#searchBtn'); time.sleep(1.8)
        body = pg.locator('#questionDisplayArea').inner_text()
        check('papers page: search results show question numbers without DB ids', 'Question #' in body and 'DB ID' not in body, body[:120])
        pg.locator('.edit-btn').first.click(); time.sleep(1.0)
        pg.locator('#editQuestionText .ql-editor').fill(f'{TAG} edited on page')
        pg.click('#saveQuestionChangesBtn'); time.sleep(0.8)
        check('papers page: saving an edit asks for approval and lists what changes', dialog_open() and 'Question text' in dialog_text(), dialog_text()[:120])
        approve()
        check('papers page: the edit is saved after approval', bool(db("SELECT 1 FROM questions WHERE question_text LIKE %s", (f'%{TAG} edited on page%',))) and 'updated' in toast().lower(), toast())
        time.sleep(1.0)
        pg.locator('.delete-btn').first.click(); time.sleep(0.8)
        check('papers page: delete asks in the approval box with the question number', dialog_open() and 'Delete question #' in dialog_text() and not natives, dialog_text()[:100])
        cancel()
        n_before = db("SELECT COUNT(*) n FROM questions WHERE paper_code=%s", (CODE,))[0]['n']
        check('papers page: cancelling keeps the question', db("SELECT COUNT(*) n FROM questions WHERE paper_code=%s", (CODE,))[0]['n'] == n_before)
        pg.locator('.delete-btn').first.click(); time.sleep(0.8); approve()
        check('papers page: approving deletes it and a toast confirms', db("SELECT COUNT(*) n FROM questions WHERE paper_code=%s", (CODE,))[0]['n'] == n_before - 1 and 'deleted' in toast().lower(), toast())

        pg.evaluate("window.ppShowView('csv')"); time.sleep(0.5)
        pg.select_option('#csvPaperCode', CODE)
        pg.set_input_files('#csvFile', str(WORK / 'paper.xlsx')); pg.click('#uploadCsvForm button[type="submit"]'); time.sleep(2.0)
        res = pg.locator('#csvUploadMessage').inner_text()
        check('papers page: re-uploading the sheet shows the skipped rows and adds nothing', 'skipped' in res.lower() and 'already' in res.lower(), res[:140])
        pg.set_input_files('#csvFile', str(WORK / 'paper_bad.csv')); pg.click('#uploadCsvForm button[type="submit"]'); time.sleep(2.0)
        res = pg.locator('#csvUploadMessage').inner_text()
        check('papers page: a bad sheet shows the problem row and says nothing was saved', 'Nothing was saved' in res and 'Row 3' in res and 'E' in res, res[:160])

        print('-- papers image tool --')
        pg.evaluate("window.ppShowView('image')"); time.sleep(0.6)
        pg.select_option('#piqPaperCode', CODE); pg.fill('#piqSubject', f'{TAG} subject')
        pg.set_input_files('#piqFile', img); time.sleep(1.4)
        box = pg.locator('#piqImage').bounding_box()
        wrap = pg.locator('#piqCanvasWrap').bounding_box()
        check('image tool: the image is shown inside its panel', box and box['height'] > 100 and box['width'] <= wrap['width'] + 1 and box['height'] <= 0.74 * 960, str(box))
        def drag(x0, y0, x1, y1):
            bb = pg.locator('#piqImage').bounding_box()
            pg.mouse.move(bb['x'] + x0 * bb['width'], bb['y'] + y0 * bb['height']); pg.mouse.down()
            pg.mouse.move(bb['x'] + x1 * bb['width'], bb['y'] + y1 * bb['height'], steps=8); pg.mouse.up(); time.sleep(0.4)
        regions = lambda: pg.evaluate("Array.from(document.querySelectorAll('#piqStage .piq-region')).map(r => r.querySelector('.piq-region__tag').textContent)")
        for i in range(4):
            drag(0.08, (215 + i * 90) / 700, 0.5, (250 + i * 90) / 700)
        check('image tool: dragging marks A to D, moving to the next letter each time', regions() == ['A', 'B', 'C', 'D'], str(regions()))
        before_b = pg.evaluate("document.querySelectorAll('#piqStage .piq-region')[1].style.top")
        pg.click('#piqAutoTrimBtn'); time.sleep(0.8)
        after_b = pg.evaluate("document.querySelectorAll('#piqStage .piq-region')[1].style.top")
        check('image tool: Auto-trim keeps the marked options and moves them with the image', regions() == ['A', 'B', 'C', 'D'] and before_b != after_b, f'{before_b} -> {after_b}')
        pg.click('#piqRotateBtn'); time.sleep(0.6)
        check('image tool: Rotate keeps the marked options', regions() == ['A', 'B', 'C', 'D'])
        pg.click('#piqUndoBtn'); time.sleep(0.5); pg.click('#piqUndoBtn'); time.sleep(0.5)
        check('image tool: Undo steps back through rotate and trim', regions() == ['A', 'B', 'C', 'D'] and pg.evaluate("document.querySelectorAll('#piqStage .piq-region')[1].style.top") == before_b)
        pg.click('#piqToolGroup [data-tool="crop"]'); drag(0.02, 0.02, 0.9, 0.95); time.sleep(0.5)
        check('image tool: Crop keeps the marked options', regions() == ['A', 'B', 'C', 'D'], str(regions()))
        pg.click('#piqToolGroup [data-tool="hide"]'); drag(0.6, 0.1, 0.8, 0.2); time.sleep(0.4)
        check('image tool: Hide applies on drag end and keeps the marks', regions() == ['A', 'B', 'C', 'D'])
        pg.click('#piqClearRegions'); time.sleep(0.3); pg.click('#piqUndoBtn'); time.sleep(0.4)
        check('image tool: Undo restores cleared option areas', regions() == ['A', 'B', 'C', 'D'])
        pg.locator('#piqStatus li[data-letter="b"]').click(); time.sleep(0.3)
        check('image tool: clicking an option row sets the answer', pg.input_value('#piqAnswer') == 'B' and 'correct' in pg.locator('#piqStatus li[data-letter="b"]').inner_text())
        pg.locator('#piqStage .piq-region__del[data-letter="d"]').click(force=True); time.sleep(0.3)
        check('image tool: the x on a mark removes just that option', regions() == ['A', 'B', 'C'], str(regions()))
        mx = db("SELECT MAX(question_id) m FROM questions WHERE paper_code=%s", (CODE,))[0]['m']
        pg.click('#piqSaveBtn'); time.sleep(3.0)
        got = db("SELECT question_id, correct_option, option_regions FROM questions WHERE paper_code=%s AND question_id=%s", (CODE, mx + 1))
        check('image tool: Save stores the question with the next number, answer B and three areas', got and got[0]['correct_option'] == 'B' and len(json.loads(got[0]['option_regions'])) == 3, f'{got} {pg.locator("#piqMessage").inner_text()[:80]}')
        imgs += [x['question_image'] for x in db("SELECT question_image FROM questions WHERE subject=%s AND question_image IS NOT NULL", (f'{TAG} subject',))]
        pg.evaluate("window.ppShowView('search')"); time.sleep(0.4); pg.click('#searchBtn'); time.sleep(1.8)
        for _ in range(20):
            if pg.locator('#questionDisplayArea strong').first.inner_text().strip() == f'Question #{mx + 1}': break
            pg.click('#nextQuestionBtn'); time.sleep(0.3)
        pg.locator('#questionDisplayArea .edit-btn').click(); time.sleep(1.5)
        badge = pg.locator('#piqQueueBadge').inner_text() if pg.locator('#piqQueueBadge').count() else ''
        check('image tool: editing an image question from search opens the tool with its number, not the DB id', f'#{mx + 1}' in badge and regions() == ['A', 'B', 'C'], f'{badge} {regions()}')
        pg.click('#piqSaveBtn'); time.sleep(0.8)
        check('image tool: saving an edit asks for approval', dialog_open() and 'Save changes' in dialog_text(), dialog_text()[:80])
        approve(); time.sleep(2.0)
        check('image tool: the edit saved and the page moved to search', pg.evaluate("document.querySelector('#ppView-search').classList.contains('is-active')") and 'updated' in pg.locator('#piqMessage').inner_text().lower() or 'updated' in toast().lower())

        pg.evaluate("window.ppShowView('format')"); time.sleep(0.6)
        pg.select_option('#ppView-format select#code', CODE); time.sleep(1.4)
        row = pg.locator(f'#questions-table-body tr:has-text("{TAG} format")')
        if row.count():
            row.locator('.delete-btn').first.click(); time.sleep(0.7)
            check('format list: delete asks in the approval box', dialog_open() and 'Delete the format' in dialog_text() and not natives, dialog_text()[:80]); approve()
            check('format list: the format is deleted after approval', not db("SELECT 1 FROM practice_questions WHERE title=%s", (f'{TAG} format',)))
        else:
            check('format list: the SELFTEST format row is visible', False, pg.inner_text('#ppView-format')[:200])
        check('papers page: no browser popups were used anywhere', not natives, str(natives))
        blank = pg.evaluate("Array.from(document.querySelectorAll('i.fas, i.far')).filter(i => { const c = getComputedStyle(i, '::before').content; return c === 'none' || c === 'normal' || c === '\"\"'; }).map(i => i.className)")
        check('papers page: every icon on the page renders', not blank, str(blank)[:200])
        check('papers page: no JavaScript errors', not errs, str(errs)[:300])
        b.close()
finally:
    cleanup()
    for u in set(imgs if 'imgs' in dir() else []):
        rel = (u or '').split('/static/uploads/', 1)
        pth = os.path.join(f'{ROOT}/admin_app/uploads', rel[1]) if len(rel) == 2 else ''
        if pth and os.path.isfile(pth):
            os.remove(pth)
        if len(rel) == 2:
            db("DELETE FROM shared_file_chunks WHERE path=%s", (rel[1],))
            db("DELETE FROM shared_files WHERE path=%s", (rel[1],))
            try: os.remove(os.path.join(f'{ROOT}/user_app/uploads', rel[1]))
            except OSError: pass
    selftest_mocktest.remove(db)

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
