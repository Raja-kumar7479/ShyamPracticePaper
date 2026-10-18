import os, re, subprocess, sys, time
import mysql.connector, requests
from dotenv import dotenv_values

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
ADMIN = 'http://127.0.0.1:5001'
ADMIN_EMAIL, ADMIN_PASSWORD = 'rajakumarvijeta7087@gmail.com', 'Raja@7479'
REDIS = os.environ.get('SPP_TEST_REDIS', 'redis://127.0.0.1:6390/0')
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


import redis
try:
    rc = redis.from_url(REDIS, socket_connect_timeout=2); rc.ping(); HAVE_REDIS = True
except Exception:
    HAVE_REDIS = False

os.environ['REDIS_URL'] = REDIS
os.environ['JUDGE_MODE'] = 'queue' if HAVE_REDIS else 'local'
os.environ['JUDGE_QUEUE_WAIT'] = '6'
os.environ['JUDGE_QUEUE_MAX'] = '3'
os.environ['PENDING_GRADER_JOB'] = '0'
os.chdir(f'{ROOT}/user_app'); sys.path.insert(0, f'{ROOT}/user_app')
import logging; logging.disable(logging.CRITICAL)
import app as app_module
from routes.exam_platform.placement_exam_portal.coding_portal.services import code_executor, judge_queue
from routes.exam_platform.placement_exam_portal.practice_coding.services import code_executor as practice_executor
from routes.exam_platform.placement_exam_portal.coding_portal.routes import test as test_routes
from routes.exam_platform.placement_exam_portal.coding_portal import models

CASE = [{'input_text': '2 3\n', 'expected_output': '5'}]
SUM = "a, b = map(int, input().split())\nprint(a + b)\n"
worker = None
selftest_mocktest.remove(db)
fx = selftest_mocktest.setup(db)
try:
    print('\n== judge on separate hosts (Redis queue) ==')
    if not HAVE_REDIS:
        check('Redis is reachable for the queue test', False, f'start one at {REDIS}')
    else:
        rc.delete(judge_queue.JOBS, judge_queue.WORKERS)
        check('queue mode is active', judge_queue.enabled())
        t = time.time(); r = code_executor.execute(SUM, 'python', CASE)
        check('with no judge worker running, a run is refused at once instead of hanging', r.error and not r.cases and time.time() - t < 3, f'{(r.error or "")[:60]} in {time.time() - t:.1f}s')
        rc.delete(judge_queue.JOBS)
        worker_log = open(f'{ROOT}/scripts/checks/__pycache__/judge_worker_selftest.log', 'w')
        worker = subprocess.Popen([sys.executable, f'{ROOT}/user_app/judge_worker.py'], env=dict(os.environ, JUDGE_MAX_PARALLEL='2'),
                                  stdout=subprocess.DEVNULL, stderr=worker_log)
        for _ in range(40):
            if judge_queue.live_workers(rc): break
            time.sleep(0.5)
        check('a judge worker registers itself', judge_queue.live_workers(rc) == 1)
        r = code_executor.execute(SUM, 'python', CASE)
        check('an exam run goes through the queue and comes back PASS', r.compiled and r.cases and r.cases[0].status == 'PASS', r.error or (r.cases[0].status if r.cases else ''))
        r = practice_executor.execute(SUM, 'python', CASE)
        check('a practice run goes through the same queue', r.cases and r.cases[0].status == 'PASS', r.error or '')
        r = code_executor.execute("int main(){ return 1 }", 'c', CASE)
        check('a compile error survives the round trip', not r.compiled and 'error' in (r.error or '').lower(), (r.error or '')[:50])
        r = code_executor.execute("while True:\n    pass\n", 'python', CASE, time_limit=2)
        check('a time limit verdict survives the round trip', r.cases and r.cases[0].status == 'TLE')
        stats = judge_queue.stats()
        check('the health numbers show the queue and the live worker', stats['mode'] == 'queue' and stats['judge_workers'] == 1 and stats['waiting'] == 0, str(stats))
        import threading
        out = []
        def one(): out.append(code_executor.execute("import time\ntime.sleep(1)\nprint(5)\n", 'python', CASE))
        ts = [threading.Thread(target=one) for _ in range(8)]
        for x in ts: x.start()
        for x in ts: x.join()
        passed = sum(1 for r in out if r.cases and r.cases[0].status == 'PASS'); busy = sum(1 for r in out if r.error and not r.cases)
        check('eight runs at once: every one is either judged or told to retry, none is lost or wrong', passed + busy == 8 and passed >= 2, f'passed={passed} busy={busy}')
        time.sleep(12)
        worker_log.flush()
        logged = open(worker_log.name).read()
        check('an idle judge worker waits quietly: no errors in its log while no job arrives', '[ERROR]' not in logged and 'lost redis' not in logged and 'Traceback' not in logged, f"errors={logged.count('[ERROR]')} bytes={len(logged)}")
        t = time.time(); r = code_executor.execute(SUM, 'python', CASE)
        check('after idling, a job is picked up at once', r.cases and r.cases[0].status == 'PASS' and time.time() - t < 6, f'{time.time() - t:.1f}s')
        worker.terminate(); worker.wait(timeout=15); worker = None
        worker_log.close()
        rc.delete(judge_queue.JOBS, judge_queue.WORKERS)

    print('\n== grading at exam close when the judge is busy ==')
    s = requests.Session()
    tok = re.search(r'name="csrf-token"[^>]*content="([^"]+)"', s.get(f'{ADMIN}/admin_login').text).group(1)
    s.post(f'{ADMIN}/admin_login', data={'email': ADMIN_EMAIL, '_csrf_token': tok})
    s.post(f'{ADMIN}/admin_login', data={'password': ADMIN_PASSWORD, '_csrf_token': tok})
    H = {'X-CSRFToken': re.search(r'name="csrf-token"[^>]*content="([^"]+)"', s.get(f'{ADMIN}/manage-tests').text).group(1)}
    D = fx['coding_id']; T = s.get(f'{ADMIN}/api/coding-panel/{D}', headers=H).json()['test']['id']
    sec = s.post(f'{ADMIN}/api/coding-panel/{D}/sections', headers=H, json={'title': 'SELFTEST coding', 'section_type': 'coding', 'duration_min': 20}).json()['section_id']
    q = s.post(f'{ADMIN}/api/coding-panel/sections/{sec}/questions', headers=H, json={'title': 'SELFTEST sum', 'statement_html': 'sum', 'difficulty': 'Easy', 'marks': 10,
               'allowed_languages': ['python'], 'time_limit_sec': 5, 'memory_limit': '256m', 'testcases': [{'input_text': '2 3', 'expected_output': '5', 'is_hidden': False}]}).json()['question_id']
    uid = db("SELECT id FROM auth WHERE email=%s", (fx['student']['email'],))[0]['id']
    db("INSERT INTO cp_attempts (test_id, user_id, status) VALUES (%s, %s, 'in_progress')", (T, uid))
    att = db("SELECT id FROM cp_attempts WHERE test_id=%s AND user_id=%s", (T, uid))[0]['id']
    db("INSERT INTO cp_answers (attempt_id, question_id, language, code, is_attempted) VALUES (%s,%s,'python',%s,1)", (att, q, SUM))
    os.environ['JUDGE_MODE'] = 'local'; judge_queue.MODE = 'local'
    real = code_executor.execute
    code_executor.execute = lambda *a, **k: code_executor.RunResult(compiled=True, error='The judge is busy right now.')
    with app_module.app.app_context():
        deferred = test_routes._grade_unsubmitted(att, fx['student']['email'])
    code_executor.execute = real
    check('when the judge is busy at exam close, the answer is left for later instead of being stored as a zero',
          deferred == 1 and not db("SELECT 1 FROM cp_submissions WHERE attempt_id=%s", (att,)), f'deferred={deferred}')
    db("UPDATE cp_attempts SET status='submitted', submitted_at=NOW() WHERE id=%s", (att,))
    with app_module.app.app_context():
        graded = test_routes.run_pending_grader()
    sub = db("SELECT verdict, score, passed, total FROM cp_submissions WHERE attempt_id=%s", (att,))
    check('the background grader then marks it with the real judge and the full score', graded == 1 and sub and sub[0]['verdict'] == 'AC' and sub[0]['score'] == 10, f'graded={graded} {sub}')
    with app_module.app.app_context():
        again = test_routes.run_pending_grader()
    check('and it is not graded twice', again == 0 and len(db("SELECT 1 FROM cp_submissions WHERE attempt_id=%s", (att,))) == 1, str(again))
finally:
    if worker is not None:
        worker.terminate()
    db("DELETE FROM cp_submissions WHERE attempt_id IN (SELECT id FROM cp_attempts WHERE test_id IN (SELECT id FROM cp_tests WHERE test_key LIKE 'free_selftest%%'))")
    db("DELETE FROM cp_answers WHERE attempt_id IN (SELECT id FROM cp_attempts WHERE test_id IN (SELECT id FROM cp_tests WHERE test_key LIKE 'free_selftest%%'))")
    db("DELETE FROM cp_attempts WHERE test_id IN (SELECT id FROM cp_tests WHERE test_key LIKE 'free_selftest%%')")
    selftest_mocktest.remove(db)

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
