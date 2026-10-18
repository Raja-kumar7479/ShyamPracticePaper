import argparse, random, re, statistics, sys, threading, time
from collections import defaultdict
import bcrypt, mysql.connector, requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import dotenv_values

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
sys.path.insert(0, f'{ROOT}/scripts/checks')
import selftest_mocktest
v = dotenv_values(f'{ROOT}/user_app/.env')
PASSWORD = 'Selftest@1234'
LOAD_EMAIL = 'selftest.load.{:04d}@example.com'


def db(q, p=(), many=False):
    c = mysql.connector.connect(host=v['DATABASE_HOST'], user=v['DATABASE_USER'], password=v['DATABASE_PASSWORD'],
                                database=v['DATABASE_NAME'], autocommit=True)
    cur = c.cursor(dictionary=True)
    if many: cur.executemany(q, p)
    else: cur.execute(q, p)
    out = cur.fetchall() if cur.with_rows else []
    cur.close(); c.close(); return out


QUESTIONS = 60
RETRY_WAITS = [2, 4, 8, 15, 30, 30]


def remove_results():
    for t in ('test_attempt_details', 'test_result', 'test_feedback', 'user_test_log'):
        try:
            db(f"DELETE FROM {t} WHERE email LIKE 'selftest.load.%@example.com'")
        except mysql.connector.Error:
            pass


def add_questions(fx):
    db("INSERT INTO test_questions (test_id, test_key, test_description_id, section_id, section_name, question_number, question_type,"
       " question_text, option_a, option_b, option_c, option_d, correct_option, correct_marks, negative_marks, question_level)"
       " VALUES (%s,%s,%s,'1','General',%s,'MCQ',%s,'<p>first</p>','<p>second</p>','<p>third</p>','<p>fourth</p>','A',1,0,'Easy')",
       [(fx['mock_sid'], fx['mock_key'], fx['mock_id'], n, f'<p>SELFTEST load question {n} ' + 'with a realistic amount of text. ' * 6 + '</p>')
        for n in range(1, QUESTIONS + 1)], many=True)


def remove_accounts():
    remove_results()
    db("DELETE FROM enrollment WHERE email LIKE 'selftest.load.%@example.com'")
    db("DELETE FROM user_login_attempts WHERE identifier LIKE '%selftest.load.%'")
    db("DELETE FROM auth WHERE email LIKE 'selftest.load.%@example.com'")


def make_accounts(n, code, name):
    remove_accounts()
    pw = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()
    db("INSERT INTO auth (username, email, password, auth_type, is_verified) VALUES (%s, %s, %s, 'manual', 1)",
       [(f'SELFTEST Load {i}', LOAD_EMAIL.format(i), pw) for i in range(n)], many=True)
    db("INSERT INTO enrollment (email, name, code, unique_code, payment_id, enrollment_date) VALUES (%s,%s,%s,%s,'SELFTEST_LOAD',NOW())",
       [(LOAD_EMAIL.format(i), name, code, f'SELFTEST-LOAD-{i:04d}-0000000000000000000000') for i in range(n)], many=True)


class Stats:
    def __init__(self):
        self.lock = threading.Lock()
        self.lat = defaultdict(list)
        self.codes = defaultdict(lambda: defaultdict(int))
        self.silent = 0
        self.errors = defaultdict(int)
        self.details = defaultdict(int)

    def add(self, name, seconds, code):
        with self.lock:
            self.lat[name].append(seconds)
            self.codes[name][code] += 1

    def fail(self, name, detail=''):
        with self.lock:
            self.errors[name] += 1
            if detail:
                self.details[detail] += 1


def timed(stats, name, fn):
    t = time.perf_counter()
    try:
        r = fn()
        stats.add(name, time.perf_counter() - t, r.status_code)
        return r
    except Exception as exc:
        stats.fail(name, f"{name}: {type(exc).__name__} {str(exc)[-90:]}")
        return None


def login(base, s, email, stats):
    r = timed(stats, 'login page', lambda: s.get(base + '/user_login', timeout=60))
    if r is None: return False
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    tok = m.group(1) if m else ''
    timed(stats, 'login email step', lambda: s.post(base + '/user_login', data={'email': email, 'csrf_token': tok}, timeout=60))
    r = timed(stats, 'login password step', lambda: s.post(base + '/user_login', data={'password': PASSWORD, 'csrf_token': tok}, timeout=60, allow_redirects=False))
    return bool(r is not None and r.status_code in (301, 302) and 'user_login' not in (r.headers.get('Location') or ''))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:5003')
    ap.add_argument('--users', type=int, default=50)
    ap.add_argument('--duration', type=int, default=20)
    ap.add_argument('--scenario', default='browse', choices=['browse', 'login', 'anonymous', 'exam'])
    ap.add_argument('--think', type=float, default=0.0)
    ap.add_argument('--keep', action='store_true')
    ap.add_argument('--log', default='')
    ap.add_argument('--submit-spread', type=float, default=0.0)
    args = ap.parse_args()

    selftest_mocktest.remove(db)
    fx = selftest_mocktest.setup(db)
    make_accounts(args.users, fx['code'], fx['student']['name'])
    if args.scenario == 'exam':
        add_questions(fx)
    stats = Stats()
    started_count = {'n': 0}
    peak = {'threads': 0, 'max_used': 0}
    stop_monitor = threading.Event()

    def monitor():
        c = mysql.connector.connect(host=v['DATABASE_HOST'], user=v['DATABASE_USER'], password=v['DATABASE_PASSWORD'], database=v['DATABASE_NAME'], autocommit=True)
        cur = c.cursor()
        while not stop_monitor.is_set():
            try:
                cur.execute("SHOW STATUS LIKE 'Threads_connected'"); peak['threads'] = max(peak['threads'], int(cur.fetchone()[1]))
            except Exception:
                pass
            time.sleep(0.25)
        cur.execute("SHOW STATUS LIKE 'Aborted_connects'"); peak['aborted'] = int(cur.fetchone()[1])
        cur.execute("SHOW STATUS LIKE 'Connection_errors_max_connections'"); peak['refused'] = int(cur.fetchone()[1])
        cur.close(); c.close()

    log_start = 0
    if args.log:
        try: log_start = __import__('os').path.getsize(args.log)
        except OSError: log_start = 0
    before = db("SHOW STATUS LIKE 'Connection_errors_max_connections'")[0]['Value']
    conns_before = int(db("SHOW STATUS LIKE 'Connections'")[0]['Value'])
    mon = threading.Thread(target=monitor, daemon=True); mon.start()
    ready = threading.Semaphore(0); go = threading.Event()
    t_login = time.time()
    stop_holder = {'at': 0.0}

    def run_worker(i):
        s_stats = stats
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=Retry(total=2, connect=2, read=0, status=0, backoff_factor=0.05, allowed_methods=None)))
        s.mount('https://', HTTPAdapter(max_retries=Retry(total=2, connect=2, read=0, status=0, backoff_factor=0.05, allowed_methods=None)))
        email = LOAD_EMAIL.format(i)
        unique = f'SELFTEST-LOAD-{i:04d}-0000000000000000000000'
        ok = True
        if args.scenario != 'anonymous':
            ok = login(args.base, s, email, s_stats)
            if not ok: s_stats.fail('login failed')
        ready.release()
        go.wait()
        if args.scenario == 'login' or not ok:
            return
        if args.think:
            time.sleep(random.uniform(0, args.think))
        if args.scenario == 'exam':
            code, key, sid = fx['code'], fx['mock_key'], fx['mock_sid']
            r = timed(s_stats, 'exam sign-in', lambda: s.post(f"{args.base}/test-login/{sid}/{key}/{code}/{unique}", data={'test_key': key}, headers={'X-Requested-With': 'XMLHttpRequest'}, timeout=60))
            timed(s_stats, 'exam instructions', lambda: s.get(f"{args.base}/paper-instruction/{sid}/{key}/{code}/{unique}", timeout=60))
            r = timed(s_stats, 'exam start', lambda: s.post(f"{args.base}/process-readiness/{sid}/{key}/{code}/{unique}", data={'readiness_checkbox': 'on'}, timeout=60))
            started = r is not None and '/start-test/' in r.url and r.status_code == 200
            if not started:
                s_stats.fail('exam did not start')
                return
            with s_stats.lock:
                started_count['n'] += 1
            r = timed(s_stats, 'exam questions', lambda: s.get(f"{args.base}/fetch-questions/{sid}/{key}/{code}/{unique}", timeout=60))
            try:
                question_ids = [q['id'] for q in r.json()]
            except Exception:
                question_ids = []
                s_stats.fail('questions did not load')
            while time.time() < stop_holder['at']:
                timed(s_stats, 'exam heartbeat', lambda: s.post(f"{args.base}/test-heartbeat/{key}", headers={'X-Requested-With': 'XMLHttpRequest'}, timeout=60))
                timed(s_stats, 'exam window claim', lambda: s.post(args.base + '/api/exam-window/claim', json={'test_key': key, 'tab_id': f'load{i}'}, timeout=60))
                if args.think: time.sleep(args.think)
            storm_at = stop_holder['at'] + args.think + 1.0 + random.uniform(0, args.submit_spread)
            time.sleep(max(0.0, storm_at - time.time()))
            body = {'test_key': key, 'total_time_taken': int(args.duration), 'device_info': 'SELFTEST load',
                    'answers': [{'question_id': q, 'status_from_client': 'answered', 'selected_option': 'a' if n % 2 else 'b',
                                 'written_answer': None, 'time_spent_on_question': 5} for n, q in enumerate(question_ids)]}
            for attempt in range(len(RETRY_WAITS) + 1):
                r = timed(s_stats, 'exam submit', lambda: s.post(f"{args.base}/submit-test-action/{sid}/{key}/{code}/{unique}", json=body, timeout=90))
                if r is not None and r.status_code == 200:
                    break
                if r is not None and r.status_code < 500 and r.status_code not in (408, 429):
                    s_stats.fail('submit rejected', f"submit rejected: {r.status_code} {r.text[:60]}")
                    break
                if attempt == len(RETRY_WAITS):
                    s_stats.fail('submit gave up')
                    break
                time.sleep(RETRY_WAITS[attempt] + random.uniform(0, 1.5))
            return
        pages = [('home', '/')] if args.scenario == 'anonymous' else [
            ('course dashboard', f"/courses/{fx['code']}/{unique}"), ('profile', '/profile'),
            ('mock test list', f"/open/mock_test/SELFTESTMOCK/{fx['code']}/{unique}"), ('home', '/'),
            ('exam window claim', None)]
        k = 0
        while time.time() < stop_holder['at']:
            name, path = pages[k % len(pages)]; k += 1
            if path is None:
                timed(s_stats, name, lambda: s.post(args.base + '/api/exam-window/claim', json={'test_key': 'free_selftest0000000001', 'tab_id': f'load{i}'}, timeout=60))
                continue
            timed(s_stats, name, lambda: s.get(args.base + path, timeout=60))
            if args.think: time.sleep(args.think)

    def guarded(i):
        released = {'done': False}
        original_release = ready.release
        try:
            run_worker(i)
        except Exception as exc:
            stats.fail('worker crashed', f"worker: {type(exc).__name__} {str(exc)[-90:]}")
        finally:
            ready.release()

    threads = [threading.Thread(target=guarded, args=(i,), daemon=True) for i in range(args.users)]
    for t in threads: t.start()
    waited = 0
    while waited < args.users:
        if ready.acquire(timeout=180):
            waited += 1
        else:
            print(f"warning: only {waited} of {args.users} virtual students got ready in time")
            break
    login_seconds = time.time() - t_login
    t0 = time.time()
    stop_holder['at'] = t0 + args.duration
    go.set()
    join_until = time.time() + args.duration + (240 if args.scenario == 'exam' else 90)
    for t in threads: t.join(timeout=max(0.1, join_until - time.time()))
    elapsed = max(0.001, time.time() - t0)
    stop_monitor.set(); mon.join(timeout=5)
    after = db("SHOW STATUS LIKE 'Connection_errors_max_connections'")[0]['Value']
    conns_after = int(db("SHOW STATUS LIKE 'Connections'")[0]['Value'])

    print(f"\n== {args.scenario}: {args.users} users, {args.duration}s against {args.base} ==")
    if args.scenario != 'anonymous':
        logins = len(stats.lat.get('login password step', []))
        print(f"logins: {logins} in {login_seconds:.1f}s = {logins / max(login_seconds, 0.001):.1f} per second, failed: {stats.errors.get('login failed', 0)}")
    print(f"{'page':22} {'count':>7} {'per sec':>8} {'p50 ms':>8} {'p95 ms':>8} {'max ms':>8}  status")
    total = 0
    for name in sorted(stats.lat):
        lat = sorted(stats.lat[name]); n = len(lat); total += n
        in_loop = name in ('exam heartbeat', 'exam window claim') or not (name.startswith('login') or name.startswith('exam '))
        if name == 'exam submit':
            print(f"{name:22} {n:7d} {'storm':>8} {statistics.median(lat) * 1000:8.0f} {(lat[int(n * 0.95) - 1] if n >= 20 else lat[-1]) * 1000:8.0f} {lat[-1] * 1000:8.0f}  "
                  + ' '.join(f"{c}:{k}" for c, k in sorted(stats.codes[name].items())))
            continue
        rate = (n / elapsed) if in_loop else (n / max(login_seconds, 0.001))
        p95 = lat[int(n * 0.95) - 1] if n >= 20 else lat[-1]
        codes = ' '.join(f"{c}:{k}" for c, k in sorted(stats.codes[name].items()))
        print(f"{name:22} {n:7d} {rate:8.1f} {statistics.median(lat) * 1000:8.0f} {p95 * 1000:8.0f} {lat[-1] * 1000:8.0f}  {codes}")
    bad = sum(k for name in stats.codes for c, k in stats.codes[name].items() if c >= 500)
    logged = ''
    if args.log:
        try:
            with open(args.log, errors='replace') as fh:
                fh.seek(log_start); text = fh.read()
            logged = f"   server log: {text.count('[ERROR]')} errors, {text.count('[CRITICAL]')} critical"
        except OSError:
            logged = ''
    print(f"server errors (5xx): {bad}   network failures: {sum(stats.errors.values())}{logged}")
    for detail, n in sorted(stats.details.items(), key=lambda kv: -kv[1])[:4]:
        print(f"   {n} x {detail}")
    print(f"MySQL: peak connections {peak['threads']}, new connections opened {conns_after - conns_before}, refused for max_connections {int(after) - int(before)}")
    if args.scenario == 'exam':
        saved = db("SELECT COUNT(*) n, COUNT(DISTINCT email) students FROM test_result WHERE email LIKE 'selftest.load.%@example.com' AND test_key=%s", (fx['mock_key'],))[0]
        rows = db("SELECT COUNT(*) n FROM test_attempt_details WHERE email LIKE 'selftest.load.%@example.com' AND test_key=%s", (fx['mock_key'],))[0]['n']
        done = db("SELECT COUNT(*) n FROM user_test_log WHERE email LIKE 'selftest.load.%@example.com' AND test_key=%s AND status='completed'", (fx['mock_key'],))[0]['n']
        wrong = db("SELECT COUNT(*) n FROM test_result WHERE email LIKE 'selftest.load.%@example.com' AND test_key=%s AND (attempted_questions_count<>%s OR net_score<>%s)", (fx['mock_key'], QUESTIONS, QUESTIONS // 2))[0]['n']
        print(f"submissions: {started_count['n']} students started, {saved['students']} results stored ({saved['n']} rows), "
              f"{done} attempts marked completed, {rows} answer rows (expected {started_count['n'] * QUESTIONS}), results with a wrong score: {wrong}")
    if not args.keep:
        remove_accounts()
        selftest_mocktest.remove(db)


if __name__ == '__main__':
    main()
