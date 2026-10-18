# Running ShyamPracticePaper for a large number of students

This page is for whoever deploys the student app (`user_app`). The student app and the admin app are deployed separately; the only thing they share is the database. It lists what the code already does, what must be set on the server, how to grow past one server, and how to measure capacity before an exam.

## What the code does on its own

- A connection that MySQL dropped (restart, network cut) is replaced at the next use; it is not handed out again.
- One MySQL connection pool per worker. Every module uses it. When the pool is empty a request waits up to `DB_POOL_WAIT` seconds (default 15) for a free connection, then fails with an error. It never opens extra connections. If MySQL cannot be reached when a worker starts, requests fail and the worker tries again every 2 seconds; it no longer falls back to unlimited direct connections.
- Pool size is chosen from the worker count so the whole app stays under about 96 connections: `DB_POOL_SIZE` defaults to `96 / WEB_CONCURRENCY` (capped at 32).
- Several workers. `gunicorn -c gunicorn.conf.py wsgi:app` starts `WEB_CONCURRENCY` gevent workers (default: one per CPU core, at most 8). Set `SPP_ASYNC_MODE=threading` to use threaded workers instead; they measured 20 to 35 percent slower.
- Password checks run outside the event loop, so a login burst does not freeze other requests.
- Rate limits are counted per signed-in student. Only anonymous requests are counted per IP address, so a whole college behind one address is not throttled as one user.
- Writes (`POST`, `PUT`, `DELETE`) that come from another website are refused. The two Razorpay webhooks are exempt.
- One sign-in per account. A new sign-in ends the older session on its next request. While the account has a test running, a new sign-in is refused, so nobody can push a student out of an exam.
- The judge runs each program as a non-root user with no network, a read-only root filesystem, one CPU, a process cap, a 32 MB file cap and a 4 MB output cap. Its parallel slots (`JUDGE_MAX_PARALLEL`) are divided between the workers.
- Submitting a test survives a bad moment. The test window sends the answers again by itself (up to six times over about 90 seconds) when the server or the network fails. The server accepts a repeated submission once and answers the repeat as a success. When time runs out, each browser waits a random 0 to 5 seconds before sending, so a whole hall does not hit the server in the same instant. A submission is accepted up to 5 minutes after time-up.
- Starting a test survives a bad moment too. Start and Resume buttons accept one click and show a spinner. The exam sign-in, "I am ready to begin" and the coding and communication lobbies try a busy server again by themselves (three times, a few seconds apart) before telling the student. For whole pages, nginx shows `user_app/deploy/busy.html` on 502, 503 and 504; that page waits and reloads itself.
- SQL questions run as a separate read-only MySQL account that can see only the question tables. If that account cannot sign in, the query is refused; it is never run with the application's own account. Each worker runs at most `SQL_SANDBOX_PARALLEL` student queries at once.
- A busy judge never costs a student marks. "Run" and "Submit" answer "judge is busy, try again" and store nothing. When a test is submitted and the judge cannot grade an answer, the answer is kept as pending and a background job grades it later.

## What you must set on the server

| Setting | Value | Why |
|---|---|---|
| `APP_ENV` | `production` | Secure cookies, real client IP behind the proxy |
| `REDIS_URL` | a reachable Redis | Shared sessions, shared rate limits, Socket.IO across workers, judge queue |
| `WEB_CONCURRENCY` | number of CPU cores | One worker uses one core |
| `WEBSITE_URL` | the public https address | Emailed links and the cross-site check |
| `RAZORPAY_WEBHOOK_SECRET` | from the Razorpay dashboard | Without it the webhooks answer 404 |
| `DATABASE_USER` | a limited MySQL user, not root | Least privilege |
| `MAIL_SERVER` | a bulk email service | A personal Gmail account stops at a few hundred emails per day |
| `FORWARDED_ALLOW_IPS` | the proxy address | So gunicorn trusts the proxy headers |

Ready-made files are in `user_app/deploy/` (the admin app has its own in `admin_app/deploy/`). Replace the domain, paths and passwords before using them.

| File | Use |
|---|---|
| `nginx.conf` | https, compression, static files, Socket.IO upgrade, proxy headers, the busy page |
| `busy.html` | The "please wait" page nginx shows when the app servers cannot answer; it retries by itself |
| `mysql-scale.cnf` | `max_connections`, buffer pool, slow query log |
| `create_app_db_user.sql` | A limited MySQL user with exactly the rights the app needs |
| `spp-student.service` | systemd unit for the student app |
| `spp-judge-worker.service` | systemd unit for a judge worker |

MySQL:

- `max_connections` must be above `WEB_CONCURRENCY x (DB_POOL_SIZE + SQL_SANDBOX_PARALLEL)` for every app server, plus the admin app, plus 20 spare. The MySQL default of 151 fits one app server.
- `log_bin_trust_function_creators = 1` is required when the app connects as a limited user, because the app creates its own triggers. The settings file has it.
- Set `innodb_buffer_pool_size` to about half of the database server's memory. The file ships with 8G.
- The limited user needs rights on the `sbx_q%` databases and `CREATE USER`, because SQL coding questions build a small sandbox database per question.
- A brand-new empty database is built by the app at its first start (tables, then every migration). `scripts/checks/db_user_privileges_check.py` proves the limited user can do all of this, and `scripts/checks/fresh_bootstrap_check.py` proves a new database comes out identical to the running one.

Judge image, built once per judge host:

```
cd user_app
docker build -f docker/Dockerfile.judge -t codejudge-runner:latest docker
```

`GET /practice-coding/api/judge/health` answers 503 when Docker is down, the image is missing, the queue is full, or (in queue mode) no judge worker is alive.

## More than one server

Everything shared between app servers lives in MySQL, Redis or the uploads folder, so app servers can be added behind a load balancer.

1. Point every app server at the same MySQL and the same Redis.
2. Files the admin uploads need no shared disk: they travel through the database and each student server copies them on first use. Student recordings do need one: point `UPLOAD_BASE` of every student server at the same disk.
3. Use sticky sessions (ip hash) on the load balancer for `/socket.io/`.
4. Move the judge off the web servers: set `JUDGE_MODE=queue` on the app servers, and on each judge host run `python judge_worker.py` with the same `REDIS_URL`. Each worker runs `JUDGE_MAX_PARALLEL` programs at a time. Add judge hosts to add capacity; the web servers then need no Docker.
5. Leave `PENDING_GRADER_JOB=1`. Only one server grades at a time; they take turns through a database lock.

## Capacity

Measured on a 10-core laptop that also ran MySQL and the load generator.

| Run | Before the fixes (1 worker) | After (6 workers, Redis) |
|---|---|---|
| 200 students clicking with no pause | 120 requests per second, dashboard median 4.0 s | 850 to 870 requests per second, dashboard median 0.3 s |
| Errors in that run | 1,067 hidden behind "200 OK", 544 connections refused by MySQL | 0 |
| Logins per second | 4 | 35 |
| MySQL connections at peak | 152 (the server limit) | under 100 for this app |
| 500 students starting and sitting a test together | not possible | 0 server errors, heartbeat median 16 ms |
| 1,000 students clicking every 2 seconds | not possible | 0 errors, most pages under 20 ms, dashboard 0.36 s |
| 500 students submitting a 60-question test in the same instant | not measured | all 500 results and 30,000 answer rows stored, slowest 1.2 s, 0 errors |
| 1,500 students submitting within 5 seconds (what the browser now does at time-up) | not measured | all 1,500 results and 90,000 answer rows stored, median 20 ms, 0 errors |

A student in a test sends about one request every 7 seconds (heartbeat, window claim, answers), so one server of this size carries roughly 5,000 students in a test. One lakh students at the same moment therefore needs about 20 such app servers behind a load balancer, a MySQL server sized for them, and a separate pool of judge hosts for coding exams. A login costs about 0.25 s of CPU, so one 10-core server signs in about 35 students per second; spread the start of a very large exam over a few minutes or add servers.

A coding run takes 1 to 3 seconds of one CPU core. A judge host with 16 cores therefore finishes about 8 runs per second. Size the judge pool from how many students will press Run in the same minute.

These are estimates from a laptop. Measure on the real server before an exam.

## Measuring

```
python scripts/load/load_test.py --base https://your-host --users 500 --duration 60 --scenario browse
python scripts/load/load_test.py --base https://your-host --users 500 --scenario login
python scripts/load/load_test.py --base https://your-host --users 500 --duration 60 --scenario exam --think 5 --submit-spread 5
```

The `exam` run signs every virtual student in, starts a 60-question test, keeps the heartbeat going, and then submits for everyone at once (`--submit-spread 0`, the worst case) or over a few seconds. It ends by counting what was stored, so a lost submission shows up as a number, not a guess.

Start the test instance with `RATELIMIT_ENABLED=0`, because all virtual students come from one address. The tool creates `selftest.load.*` accounts, removes them afterwards, and prints requests per second, latency, error counts and the MySQL connection peak. Raise `--users` in steps until the median passes one second or errors appear. That step is the limit of the server.
