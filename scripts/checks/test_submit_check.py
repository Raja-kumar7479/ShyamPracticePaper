import hashlib, hmac, os, re, sys, time
import mysql.connector, requests
from dotenv import dotenv_values
from playwright.sync_api import sync_playwright

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
USER = os.environ.get('SPP_USER_BASE', 'http://127.0.0.1:5002')
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


os.environ['PENDING_GRADER_JOB'] = '0'
os.chdir(f'{ROOT}/user_app'); sys.path.insert(0, f'{ROOT}/user_app')
import logging; logging.disable(logging.CRITICAL)
import app as app_module
from routes.exam_platform.competitive_exam_platform.utils import utils_test_token as tokens

selftest_mocktest.remove(db)
fx = selftest_mocktest.setup(db)
STU, CODE, KEY, SID = fx['student'], fx['code'], fx['mock_key'], fx['mock_sid']
UNIQUE = STU['unique_code']
EMAIL = STU['email']
PATH = f"{SID}/{KEY}/{CODE}/{UNIQUE}"


def reset_attempts():
    for t in ('test_attempt_details', 'test_result', 'test_feedback', 'user_test_log'):
        db(f"DELETE FROM {t} WHERE email=%s AND test_key=%s", (EMAIL, KEY))


def result_rows():
    return db("SELECT attempted_questions_count a, correctly_answered_questions_count c, net_score s, attempt_number n "
              "FROM test_result WHERE email=%s AND test_key=%s", (EMAIL, KEY))


def detail_rows():
    return db("SELECT question_id, user_selected_option, time_spent_on_question_seconds t FROM test_attempt_details "
              "WHERE email=%s AND test_key=%s", (EMAIL, KEY))


def status():
    row = db("SELECT status FROM user_test_log WHERE email=%s AND test_key=%s ORDER BY attempt_number DESC LIMIT 1", (EMAIL, KEY))
    return row[0]['status'] if row else None


try:
    db("INSERT INTO test_questions (test_id, test_key, test_description_id, section_id, section_name, question_number, question_type,"
       " question_text, option_a, option_b, option_c, option_d, correct_option, correct_marks, negative_marks, question_level, answer_text)"
       " VALUES " + ', '.join(["(%s,%s,%s,'1','General',%s,'MCQ',%s,'<p>first</p>','<p>second</p>','<p>third</p>','<p>fourth</p>','A',2,0.5,'Easy','SELFTEST-SECRET-EXPLANATION')"] * 6),
       tuple(x for n in range(1, 7) for x in (SID, KEY, fx['mock_id'], n, f'<p>SELFTEST submit question {n}</p>')))
    Q = [r['id'] for r in db("SELECT id FROM test_questions WHERE test_key=%s ORDER BY question_number", (KEY,))]

    u = requests.Session()
    page = u.get(USER + '/user_login', timeout=30).text
    ctok = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    u.post(USER + '/user_login', data={'email': EMAIL, 'csrf_token': ctok}, timeout=30)
    u.post(USER + '/user_login', data={'password': STU['password'], 'csrf_token': ctok}, timeout=30)

    def begin():
        u.post(f"{USER}/test-login/{PATH}", data={'test_key': KEY}, headers={'X-Requested-With': 'XMLHttpRequest'}, timeout=30)
        u.get(f"{USER}/paper-instruction/{PATH}", timeout=30)
        r = u.post(f"{USER}/process-readiness/{PATH}", data={'readiness_checkbox': 'on'}, timeout=30)
        return r.status_code == 200 and '/start-test/' in r.url

    def submit(answers, **extra):
        body = dict({'test_key': KEY, 'total_time_taken': 120, 'device_info': 'SELFTEST', 'answers': answers}, **extra)
        return u.post(f"{USER}/submit-test-action/{PATH}", json=body, timeout=60)

    def answer(qid, option='a', state='answered', spent=5):
        return {'question_id': qid, 'status_from_client': state, 'selected_option': option, 'written_answer': None, 'time_spent_on_question': spent}

    print('\n== the question paper ==')
    check('the student starts the test', begin() and status() == 'in_progress', str(status()))
    r = u.get(f"{USER}/fetch-questions/{PATH}", timeout=30)
    check('the paper loads with every question', r.status_code == 200 and len(r.json()) == 6, f'{r.status_code}')
    check('the paper never carries the answer key or the explanations', 'correct_option' not in r.text and 'SELFTEST-SECRET-EXPLANATION' not in r.text and 'answer_text' not in r.text)
    r2 = u.get(f"{USER}/fetch-questions/{PATH}", timeout=30)
    check('a second load gives the same paper', r2.status_code == 200 and r2.text == r.text)

    print('\n== a submission with damaged entries is still saved ==')
    messy = [answer(Q[0], 'a'), answer(Q[1], 'b'), answer(Q[1], 'a'), answer(str(Q[2]), 'a'), answer(99999999, 'a'), 'garbage', None,
             answer(Q[3], 'abcdefghijklmnopqrstuvwxyz', spent='abc'), answer(Q[4], None, state='not_answered'), {'no_id': 1}]
    r = submit(messy, total_time_taken='soon')
    res = result_rows(); det = detail_rows()
    check('the submission is accepted', r.status_code == 200 and 'redirect_url' in r.json(), f'{r.status_code} {r.text[:120]}')
    check('unknown and broken entries are ignored, a repeated question counts once (last answer wins)',
          len(res) == 1 and res[0]['a'] == 4 and res[0]['c'] == 3 and abs(res[0]['s'] - 5.5) < 0.001, str(res))
    ids = sorted(d['question_id'] for d in det)
    check('one answer row per question, none duplicated', ids == sorted(Q[:5]), str(ids))
    long_row = [d for d in det if d['question_id'] == Q[3]]
    check('an over-long option and a non-numeric time are stored safely instead of failing the whole submission',
          long_row and len(long_row[0]['user_selected_option']) <= 10 and long_row[0]['t'] == 0, str(long_row))
    check('the attempt is marked completed', status() == 'completed', str(status()))
    first_url = r.json().get('redirect_url') if r.status_code == 200 else None

    print('\n== the same submission sent again (the answer was lost on the way) ==')
    r = submit([answer(Q[0], 'b')])
    check('the repeat is answered as a success with the same next page', r.status_code == 200 and r.json().get('redirect_url') == first_url, f'{r.status_code} {r.text[:120]}')
    res2 = result_rows()
    check('nothing is stored twice and the first result is unchanged', len(res2) == 1 and res2 == res and len(detail_rows()) == 5, str(res2))

    print('\n== refused submissions ==')
    reset_attempts()
    check('a fresh attempt starts', begin() and status() == 'in_progress', str(status()))
    r = u.post(f"{USER}/submit-test-action/{PATH}", data='[1, 2]', headers={'Content-Type': 'application/json'}, timeout=30)
    check('a body that is not a submission is refused with 400 and the attempt stays open', r.status_code == 400 and status() == 'in_progress' and not result_rows(), f'{r.status_code} {status()}')
    db("UPDATE user_test_log SET status='terminated' WHERE email=%s AND test_key=%s", (EMAIL, KEY))
    r = submit([answer(Q[0], 'a')])
    check('a submission for a terminated attempt is refused with 409, so the browser does not keep retrying', r.status_code == 409 and not result_rows(), f'{r.status_code} {r.text[:100]}')

    print('\n== time is up: a submission a little late is still accepted ==')
    with app_module.app.app_context():
        secret = app_module.app.config.get('TEST_TOKEN_SECRET')

        def token_issued(seconds_ago, duration=3600):
            stamp = int(time.time()) - seconds_ago
            data = f"{EMAIL}:{KEY}:{stamp}:{'0' * 32}:{duration}"
            return f"{data}:{hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()}"

        late = token_issued(3600 + 120)
        very_late = token_issued(3600 + 400)
        check('two minutes after time-up: heartbeats stop being accepted', tokens.validate_test_token(late, EMAIL, KEY) is False)
        check('two minutes after time-up: the final submission is still accepted', tokens.validate_test_token(late, EMAIL, KEY, grace_seconds=tokens.SUBMIT_GRACE_SECONDS) is True)
        check('long after time-up: the final submission is refused', tokens.validate_test_token(very_late, EMAIL, KEY, grace_seconds=tokens.SUBMIT_GRACE_SECONDS) is False)
        check('a token for another student is refused', tokens.validate_test_token(late, 'someone.else@example.com', KEY, grace_seconds=tokens.SUBMIT_GRACE_SECONDS) is False)

    print('\n== in the browser: a failing server at submit time ==')
    reset_attempts()
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome', headless=True)
        ctx = b.new_context(viewport={'width': 1440, 'height': 960}); ctx.set_default_timeout(25000)
        pg = ctx.new_page()
        pg.goto(f'{USER}/user_login'); time.sleep(1.0)
        pg.fill('input[name="email"]', EMAIL); pg.keyboard.press('Enter'); time.sleep(1.5)
        pg.fill('input[name="password"]', STU['password']); pg.keyboard.press('Enter'); time.sleep(2.0)
        pg.goto(f"{USER}/open/mock_test/{SID}/{CODE}/{UNIQUE}"); time.sleep(1.8)
        href = pg.locator('a:has-text("Start Test")').first.get_attribute('href') or ''
        pg.goto(href if href.startswith('http') else USER + href); time.sleep(1.5)
        with ctx.expect_page() as popup_info:
            pg.click('#test-login-form .sign-in-box')
        ex = popup_info.value; ex.set_default_timeout(25000)
        errs = []; ex.on('pageerror', lambda e: errs.append(str(e)[:200]))
        ex.wait_for_load_state(); time.sleep(1.5)
        ex.click('button:has-text("Next")'); time.sleep(1.5)
        ex.check('#readiness_checkbox'); ex.click('#ready_to_begin_button'); time.sleep(4.5)
        check('the test window opened with the questions', '/start-test/' in ex.evaluate('location.href') and ex.locator('#question-box-container').count() == 1)
        seen = {'n': 0, 'codes': []}

        def flaky(route):
            seen['n'] += 1
            if seen['n'] <= 2:
                seen['codes'].append(503)
                route.fulfill(status=503, content_type='application/json', body='{"error": "The server is busy."}')
            else:
                seen['codes'].append('passed on')
                route.continue_()

        ex.route('**/submit-test-action/**', flaky)
        ex.click('#submit-test-btn'); time.sleep(0.6)
        ex.click('button:has-text("OK")')
        time.sleep(1.2)
        toast = ex.evaluate("(() => { const t = document.querySelector('.spp-exam-toast'); if (!t) return null; const r = t.getBoundingClientRect(); return {text: t.textContent, left: r.left, top: r.top}; })()")
        check('after a failed send the student is told the answers are safe and are being sent again', bool(toast) and 'Sending them again' in toast['text'] and seen['n'] >= 1, f"requests so far={seen['n']} {toast}")
        check('that message sits at the top-left like every other flash message', bool(toast) and toast['left'] <= 20 and toast['top'] <= 20, str(toast))
        check('the attempt is not lost while the server is failing', status() == 'in_progress' and not result_rows(), str(status()))
        landed = False
        for _ in range(40):
            time.sleep(0.5)
            if '/test_feedback/' in ex.evaluate('location.href'):
                landed = True
                break
        check('the window keeps retrying by itself and the test is submitted on the third try', landed and seen['n'] == 3, f"requests={seen['n']} {seen['codes']} url={ex.evaluate('location.href')[-60:]}")
        check('exactly one result is stored', len(result_rows()) == 1 and status() == 'completed', f'{result_rows()} {status()}')
        check('no JavaScript errors in the test window', not errs, str(errs)[:200])
        try:
            ex.evaluate("window.sppExamLeaving = true"); ex.close()
        except Exception:
            pass
        b.close()
finally:
    reset_attempts()
    selftest_mocktest.remove(db)
    check('the SELFTEST rows are removed', not db("SELECT 1 FROM test_questions WHERE test_key=%s", (KEY,)) and not db("SELECT 1 FROM test_result WHERE email=%s", (EMAIL,)))

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
