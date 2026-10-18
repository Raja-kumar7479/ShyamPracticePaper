import os, re, sys, threading, time
import mysql.connector, requests
from dotenv import dotenv_values

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
ADMIN = 'http://127.0.0.1:5001'
USER = os.environ.get('SPP_USER_BASE', 'http://127.0.0.1:5002')
ADMIN_EMAIL, ADMIN_PASSWORD = 'rajakumarvijeta7087@gmail.com', 'Raja@7479'
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
os.environ['SQL_SANDBOX_PARALLEL'] = '2'
os.environ['SQL_SANDBOX_WAIT'] = '1'
os.chdir(f'{ROOT}/user_app'); sys.path.insert(0, f'{ROOT}/user_app')
import logging; logging.disable(logging.CRITICAL)
import app as app_module
from config import Config
from routes.exam_platform.placement_exam_portal.coding_portal.services import sql_executor
from routes.exam_platform.placement_exam_portal.coding_portal.routes import test as test_routes
from routes.exam_platform.placement_exam_portal.coding_portal import models

SCHEMA = ("CREATE TABLE emp (id INT PRIMARY KEY, name VARCHAR(30), salary INT);\n"
          "INSERT INTO emp VALUES (1,'Asha',500),(2,'Ravi',700),(3,'Meena',900);")
SCHEMA2 = SCHEMA + "\nINSERT INTO emp VALUES (4,'Kiran',1000);"
SOLUTION = "SELECT name FROM emp WHERE salary > 600 ORDER BY name"
RIGHT = "select name from emp where salary >= 700"
WRONG = "SELECT name FROM emp"
BROKEN = "SELECT nothing FROM missing_table"

admin_calls = {'n': 0}
sandbox_calls = {'n': 0}
real_admin = sql_executor._admin_conn
real_sandbox = sql_executor._sandbox_conn


def counting_admin(*a, **k):
    admin_calls['n'] += 1
    return real_admin(*a, **k)


def counting_sandbox(*a, **k):
    sandbox_calls['n'] += 1
    return real_sandbox(*a, **k)


sql_executor._admin_conn = counting_admin
sql_executor._sandbox_conn = counting_sandbox


def outcome(qid, schema, query):
    try:
        return 'ok', sql_executor.run_query(qid, schema, query)
    except sql_executor.SqlUnavailable as e:
        return 'unavailable', str(e)
    except sql_executor.SqlError as e:
        return 'error', str(e)


def hold_slots():
    sql_executor._slots.acquire(); sql_executor._slots.acquire()


def free_slots():
    sql_executor._slots.release(); sql_executor._slots.release()


made = []
selftest_mocktest.remove(db)
fx = selftest_mocktest.setup(db)
try:
    s = requests.Session()
    tok = re.search(r'name="csrf-token"[^>]*content="([^"]+)"', s.get(f'{ADMIN}/admin_login').text).group(1)
    s.post(f'{ADMIN}/admin_login', data={'email': ADMIN_EMAIL, '_csrf_token': tok})
    s.post(f'{ADMIN}/admin_login', data={'password': ADMIN_PASSWORD, '_csrf_token': tok})
    H = {'X-CSRFToken': re.search(r'name="csrf-token"[^>]*content="([^"]+)"', s.get(f'{ADMIN}/manage-tests').text).group(1)}
    D = fx['coding_id']; T = s.get(f'{ADMIN}/api/coding-panel/{D}', headers=H).json()['test']['id']
    sec = s.post(f'{ADMIN}/api/coding-panel/{D}/sections', headers=H, json={'title': 'SELFTEST sql', 'section_type': 'sql', 'duration_min': 20}).json()['section_id']

    def add_question(title, solution=SOLUTION):
        r = s.post(f'{ADMIN}/api/coding-panel/sections/{sec}/questions', headers=H, json={
            'title': title, 'statement_html': 'Names with salary above 600', 'difficulty': 'Easy', 'marks': 10,
            'sandbox_schema_sql': SCHEMA, 'solution_query': solution})
        qid = r.json()['question_id']; made.append(qid); return qid

    q = add_question('SELFTEST sql names')
    q2 = add_question('SELFTEST sql second')
    qbad = add_question('SELFTEST sql broken', solution=BROKEN)
    sbx = sql_executor.sandbox_db_name(q)

    print('\n== SQL questions: the sandbox ==')
    kind, res = outcome(q, SCHEMA, 'SELECT * FROM emp ORDER BY id')
    check('a query runs against the question tables', kind == 'ok' and res['row_count'] == 3 and res['columns'] == ['id', 'name', 'salary'], str(res)[:90])
    before = admin_calls['n']
    for _ in range(5):
        outcome(q, SCHEMA, 'SELECT COUNT(*) FROM emp')
    check('after the first run a query opens no administrator connection', admin_calls['n'] == before, f"extra={admin_calls['n'] - before}")
    kind, res = outcome(q, SCHEMA, 'SELECT CURRENT_USER()')
    who = res['rows'][0][0] if kind == 'ok' else res
    check('student queries run as the read-only sandbox account', str(who).startswith(Config.SQL_SANDBOX_USER + '@'), str(who))
    kind, res = outcome(q, SCHEMA, f"SELECT COUNT(*) FROM `{v['DATABASE_NAME']}`.auth")
    check('that account cannot read the application database', kind == 'error' and 'denied' in res.lower(), f'{kind} {str(res)[:70]}')
    kind, res = outcome(q, SCHEMA, "SELECT user FROM `mysql`.user")
    check('a quoted reference to the mysql schema is refused', kind == 'error', f'{kind} {str(res)[:70]}')
    kind, res = outcome(q, SCHEMA, "SELECT GET_LOCK('spp_pending_grader', 5)")
    check('a student query cannot take server locks', kind == 'error' and 'not permitted' in res, f'{kind} {str(res)[:70]}')
    kind, res = outcome(q, SCHEMA, "SELECT 1; DROP TABLE emp")
    check('two statements in one query are refused', kind == 'error', f'{kind} {str(res)[:70]}')
    kind, res = outcome(q, SCHEMA, "UPDATE emp SET salary = 0")
    check('a write statement is refused', kind == 'error', f'{kind} {str(res)[:70]}')

    def denied(db_name):
        raise mysql.connector.Error(msg='Access denied (simulated)', errno=1045)
    sql_executor._sandbox_conn = denied
    kind, res = outcome(q, SCHEMA, 'SELECT * FROM emp')
    sql_executor._sandbox_conn = counting_sandbox
    check('if the read-only account cannot sign in the query is refused, never run on the application account', kind == 'unavailable', f'{kind} {str(res)[:70]}')
    kind, res = outcome(q, SCHEMA, 'SELECT * FROM emp')
    check('and it recovers on the next query', kind == 'ok' and res['row_count'] == 3, f'{kind}')

    hold_slots()
    t = time.time(); kind, res = outcome(q, SCHEMA, 'SELECT * FROM emp'); took = time.time() - t
    free_slots()
    check('when every slot is taken the student is told to retry, within the wait time', kind == 'unavailable' and 'busy' in res.lower() and took < 3, f'{kind} {took:.1f}s')

    db(f"DROP DATABASE IF EXISTS `{sbx}`")
    kind, res = outcome(q, SCHEMA, 'SELECT COUNT(*) FROM emp')
    check('a sandbox database that disappeared is rebuilt on the next query', kind == 'ok' and res['rows'][0][0] == 3, f'{kind} {str(res)[:70]}')

    db(f"DROP DATABASE IF EXISTS `{sbx}`")
    sql_executor._ready.clear()
    Config.SQL_SANDBOX_WAIT = 30
    out = []
    def one(): out.append(outcome(q, SCHEMA, 'SELECT COUNT(*) FROM emp'))
    ts = [threading.Thread(target=one) for _ in range(12)]
    for x in ts: x.start()
    for x in ts: x.join()
    Config.SQL_SANDBOX_WAIT = 1
    counts = [r[1]['rows'][0][0] for r in out if r[0] == 'ok']
    check('twelve students hitting a missing sandbox at once: built once, every query answered, rows not duplicated', len(counts) == 12 and set(counts) == {3}, f'ok={len(counts)} counts={sorted(set(counts))} other={[r for r in out if r[0] != "ok"][:2]}')

    kind, res = outcome(q, SCHEMA2, 'SELECT COUNT(*) FROM emp')
    check('when the admin changes the tables the sandbox is rebuilt', kind == 'ok' and res['rows'][0][0] == 4, f'{kind} {str(res)[:70]}')
    kind, res = outcome(q, SCHEMA, 'SELECT COUNT(*) FROM emp')
    check('and rebuilt again when changed back', kind == 'ok' and res['rows'][0][0] == 3, f'{kind}')

    print('\n== SQL questions: checking an answer ==')
    sql_executor._expected.clear()
    before = sandbox_calls['n']
    a = sql_executor.check_query(q, SCHEMA, RIGHT, SOLUTION)
    b = sql_executor.check_query(q, SCHEMA, WRONG, SOLUTION)
    c = sql_executor.check_query(q, SCHEMA, SOLUTION, SOLUTION)
    check('a right answer is accepted and a wrong one is rejected with the reason', a['correct'] and c['correct'] and not b['correct'] and 'differ' in b['reason'], b['reason'])
    check('the reference answer is run once and reused, not once per student', sandbox_calls['n'] - before == 4, f"connections={sandbox_calls['n'] - before}")
    try:
        sql_executor.check_query(q, SCHEMA, 'SELECT nme FROM emp', SOLUTION); kind = 'ok'
    except sql_executor.SqlUnavailable: kind = 'unavailable'
    except sql_executor.SqlError: kind = 'error'
    check('a mistake in the student query is reported as the student\'s error', kind == 'error', kind)
    try:
        sql_executor.check_query(qbad, SCHEMA, SOLUTION, BROKEN); kind = 'ok'
    except sql_executor.SqlQuestionBroken: kind = 'broken'
    except sql_executor.SqlError: kind = 'error'
    check('a broken reference answer is reported as a fault of the question, not a wrong answer', kind == 'broken', kind)

    print('\n== SQL questions: grading at exam close ==')
    email = fx['student']['email']
    uid = db("SELECT id FROM auth WHERE email=%s", (email,))[0]['id']
    db("INSERT INTO cp_attempts (test_id, user_id, status) VALUES (%s, %s, 'in_progress')", (T, uid))
    att = db("SELECT id FROM cp_attempts WHERE test_id=%s AND user_id=%s", (T, uid))[0]['id']
    for qid, code in ((q, RIGHT), (q2, WRONG), (qbad, RIGHT)):
        db("INSERT INTO cp_answers (attempt_id, question_id, language, code, is_attempted) VALUES (%s,%s,NULL,%s,1)", (att, qid, code))

    def subs():
        return {r['question_id']: r for r in db("SELECT question_id, verdict, score, language FROM cp_submissions WHERE attempt_id=%s", (att,))}

    hold_slots()
    with app_module.app.app_context():
        deferred = test_routes._grade_unsubmitted(att, email)
    free_slots()
    check('when the SQL judge is busy at exam close nothing is stored as a zero', deferred == 3 and not subs(), f'deferred={deferred} {subs()}')

    with app_module.app.app_context():
        deferred = test_routes._grade_unsubmitted(att, email)
    got = subs()
    check('a saved SQL answer that was never checked is graded at exam close', got.get(q, {}).get('verdict') == 'AC' and got[q]['score'] == 10 and got[q]['language'] == 'sql', str(got.get(q)))
    check('a wrong saved answer gets zero', got.get(q2, {}).get('verdict') == 'WA' and got[q2]['score'] == 0, str(got.get(q2)))
    check('an answer to a question with a broken reference is left ungraded, not marked wrong', deferred == 1 and qbad not in got, f'deferred={deferred}')

    db("DELETE FROM cp_submissions WHERE attempt_id=%s", (att,))
    db("UPDATE cp_attempts SET status='submitted', submitted_at=NOW() WHERE id=%s", (att,))
    test_routes._grader_skip.clear()
    with app_module.app.app_context():
        graded = test_routes.run_pending_grader()
    got = subs()
    check('the background grader marks deferred SQL answers', graded == 2 and got.get(q, {}).get('verdict') == 'AC' and got.get(q2, {}).get('verdict') == 'WA', f'graded={graded} {got}')
    before = sandbox_calls['n']
    with app_module.app.app_context():
        again = test_routes.run_pending_grader()
    check('the broken question does not block the queue and is not retried every cycle', again == 0 and sandbox_calls['n'] == before and qbad not in subs(), f"again={again} connections={sandbox_calls['n'] - before}")
    db("UPDATE cp_questions SET solution_query=NULL WHERE id=%s", (qbad,))
    with app_module.app.app_context():
        pending = [r['question_id'] for r in models.pending_auto_grades(50)]
    check('an answer that can never be graded (no reference answer) is not queued at all', qbad not in pending, str(pending))
    db("UPDATE cp_questions SET solution_query=%s WHERE id=%s", (BROKEN, qbad))

    print('\n== SQL questions: through the student API ==')
    db("DELETE FROM cp_submissions WHERE attempt_id=%s", (att,))
    db("UPDATE cp_attempts SET status='in_progress', submitted_at=NULL WHERE id=%s", (att,))
    u = requests.Session()
    page = u.get(USER + '/user_login', timeout=30).text
    ctok = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    u.post(USER + '/user_login', data={'email': email, 'csrf_token': ctok}, timeout=30)
    u.post(USER + '/user_login', data={'password': fx['student']['password'], 'csrf_token': ctok}, timeout=30)
    token = ctok
    for path in ('/profile', '/'):
        html = u.get(USER + path, timeout=30).text
        m = re.search(r'name="csrf-token"[^>]*content="([^"]+)"', html) or re.search(r'name="csrf_token" value="([^"]+)"', html)
        if m:
            token = m.group(1); break
    UH = {'X-CSRFToken': token, 'Accept': 'application/json', 'Origin': USER}
    r = u.post(f'{USER}/api/coding-portal/sql/{att}/run', headers=UH, json={'question_id': q, 'query': 'SELECT * FROM emp'}, timeout=60)
    check('Run Query answers with the rows', r.status_code == 200 and r.json()['result']['row_count'] == 3, f'{r.status_code} {r.text[:90]}')
    r = u.post(f'{USER}/api/coding-portal/sql/{att}/run', headers=UH, json={'question_id': q, 'query': "SELECT user FROM `mysql`.user"}, timeout=60)
    check('a forbidden query is answered 400 with the reason', r.status_code == 400 and 'not permitted' in r.text, f'{r.status_code} {r.text[:90]}')
    r = u.post(f'{USER}/api/coding-portal/sql/{att}/check', headers=UH, json={'question_id': q, 'query': RIGHT}, timeout=60)
    got = subs()
    check('Submit marks a right answer and stores it', r.status_code == 200 and r.json()['correct'] and r.json()['score'] == 10 and got.get(q, {}).get('verdict') == 'AC', f'{r.status_code} {r.text[:90]}')
    r = u.post(f'{USER}/api/coding-portal/sql/{att}/check', headers=UH, json={'question_id': qbad, 'query': RIGHT}, timeout=60)
    check('Submit on a question with a broken reference answers "try again" (503) and stores nothing', r.status_code == 503 and r.json().get('busy') is True and qbad not in subs(), f'{r.status_code} {r.text[:110]}')
finally:
    sql_executor._admin_conn = real_admin
    sql_executor._sandbox_conn = real_sandbox
    db("DELETE FROM cp_submissions WHERE attempt_id IN (SELECT id FROM cp_attempts WHERE test_id IN (SELECT id FROM cp_tests WHERE test_key LIKE 'free_selftest%%'))")
    db("DELETE FROM cp_answers WHERE attempt_id IN (SELECT id FROM cp_attempts WHERE test_id IN (SELECT id FROM cp_tests WHERE test_key LIKE 'free_selftest%%'))")
    db("DELETE FROM cp_attempts WHERE test_id IN (SELECT id FROM cp_tests WHERE test_key LIKE 'free_selftest%%')")
    for qid in made:
        db(f"DROP DATABASE IF EXISTS `{sql_executor.sandbox_db_name(qid)}`")
        db("DELETE FROM cp_sql_sandboxes WHERE question_id=%s", (qid,))
    selftest_mocktest.remove(db)
    left = [r for r in db("SHOW DATABASES") if any(str(x).startswith(Config.SQL_SANDBOX_PREFIX) and str(x)[len(Config.SQL_SANDBOX_PREFIX):] in {str(i) for i in made} for x in r.values())]
    check('the test sandbox databases are removed', not left, str(left))

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
