# Before you deploy: what is still open and how to do it

This page lists everything that is **not done yet** and must be done on the real servers. The code itself is ready; every item below is a setting, an account or a server step that cannot be done from the development Mac.

The examples assume Ubuntu servers, the student app in `/srv/user_app` and the admin app in `/srv/admin_app`. Change the paths and names to yours.

## The short list

| # | What is open | Where | Needs from you |
|---|---|---|---|
| 1 | MySQL still has default settings (151 connections, 128 MB) | database server | nothing |
| 2 | Both apps connect as `root` | database server + both `.env` | a new password |
| 3 | Redis is not installed | student server | nothing |
| 4 | Judge image is not built on the server | student server (or judge machines) | nothing |
| 5 | Production values are missing in `.env` | both apps | your domain names |
| 6 | The student app must be started the production way | student server | nothing |
| 7 | nginx and https are not set up | both servers | domain names pointing to the servers |
| 8 | Razorpay webhook is not created | Razorpay dashboard | dashboard access |
| 9 | Email still goes through Gmail | bulk email account + both `.env` | an account with a bulk email service |
| 10 | Google sign-in points to `127.0.0.1` | Google Cloud console + `.env` | console access |
| 11 | The admin password was shown in a chat and is written in the test scripts | admin app | a new password |
| 12 | No backup is set up | database server + student server | a place to keep backups |
| 13 | No load test has been run on the real server | student server | one hour before launch |

Do them in this order. Steps 1 and 2 are done once, because both apps use the same database.

## What to copy to which server

The two apps are separate. Each server gets one folder only.

| Server | Copy this | Do not copy |
|---|---|---|
| Student server | the whole `user_app/` folder | `.env`, `.venv/`, `logs/`, `__pycache__/` |
| Admin server | the whole `admin_app/` folder | `.env`, `.venv/`, `logs/`, `__pycache__/` |
| Neither | `docs/`, `scripts/`, the top-level `.venv/` | |

`scripts/` is for testing on a developer machine. It contains the admin email and password in plain text, so keep it off the servers.

If you move your current database to the server, the files the admin uploaded (question images, notes, syllabus) come with it: they are stored inside the database. Student recordings are in `user_app/uploads/`; copy that folder only if you want to keep the recordings made so far.

---

## 1. MySQL settings

**Why:** with the default 151 connections the database refuses students once a few hundred are active.

The file is `user_app/deploy/mysql-scale.cnf` (the same file is in `admin_app/deploy/`).

```bash
sudo cp /srv/user_app/deploy/mysql-scale.cnf /etc/mysql/conf.d/spp.cnf
sudo nano /etc/mysql/conf.d/spp.cnf
```

Change one line in it: set `innodb_buffer_pool_size` to about half of the memory of the database server (for example `4G` on an 8 GB server). Then:

```bash
sudo systemctl restart mysql
mysql -u root -p -e "SHOW VARIABLES WHERE Variable_name IN ('max_connections','innodb_buffer_pool_size','slow_query_log')"
```

**Done when:** `max_connections` shows 600 and `slow_query_log` shows ON.

If you later run more than one student server, count about 100 connections plus 8 for every worker, for each student server, then add 30. `max_connections` must be above that total.

## 2. A limited database user instead of root

**Why:** if the app is ever broken into, `root` can destroy every database on the server. The limited user can only touch this project's data.

```bash
mysql -u root -p -e "CREATE DATABASE your_database CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
nano /srv/user_app/deploy/create_app_db_user.sql
```

In that file replace `CHANGE_THIS_PASSWORD` with a strong password and `YOUR_DATABASE_NAME` with your database name (one place each). Then:

```bash
mysql -u root -p < /srv/user_app/deploy/create_app_db_user.sql
mysql -u spp_app -p -e "SELECT 1"
```

Skip the `CREATE DATABASE` line if you are restoring an existing database.

If the apps are on other machines than the database, also open MySQL to those two machines only (`bind-address` in the MySQL config and the firewall).

**Done when:** the last command prints `1`. The user name `spp_app` and its password go into both `.env` files in step 5.

## 3. Redis (student server)

**Why:** without Redis the student app can run only one worker, which is the small mode it runs in today.

```bash
sudo apt install -y redis-server
sudo systemctl enable --now redis-server
redis-cli ping
```

**Done when:** the last command prints `PONG`.

## 4. Python, the virtual environment and the judge image (student server)

**Why:** the fast server engine is installed only inside the virtual environment, and coding questions need the judge image.

```bash
sudo useradd --system --create-home spp
sudo chown -R spp /srv/user_app

cd /srv/user_app
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

sudo apt install -y docker.io
sudo usermod -aG docker spp
docker build -f docker/Dockerfile.judge -t codejudge-runner:latest docker
docker run --rm codejudge-runner:latest id
```

The first two lines create the `spp` user that the service files run as. Do the same two lines with `/srv/admin_app` on the admin server.

Use Python 3.12, as `runtime.txt` says. All testing so far was on Python 3.14, so watch the first start for errors.

**Done when:** the last command prints `uid=10001(runner)`.

## 5. The `.env` files

**Why:** the production switches are not set, so cookies are not marked secure, emailed links point to the wrong address and the payment webhook answers 404.

Make each file from its example:

```bash
cd /srv/user_app  && cp .env.example .env && nano .env
cd /srv/admin_app && cp .env.example .env && nano .env
```

Make a random value for each secret key with:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Student app (`/srv/user_app/.env`)

| Name | Set it to |
|---|---|
| `APP_ENV` | `production` |
| `WEBSITE_URL` | your public address, for example `https://www.your-domain.com` |
| `SECRET_KEY`, `CSRF_SESSION_KEY`, `TEST_TOKEN_SECRET` | a new random value each |
| `ENROLL_SECRET_KEY`, `DOWNLOAD_SECRET_KEY` | the same values as in the admin app's `.env` |
| `DATABASE_HOST`, `DATABASE_NAME` | your database server and database name |
| `DATABASE_USER`, `DATABASE_PASSWORD` | `spp_app` and the password from step 2 |
| `REDIS_URL` | `redis://localhost:6379/0` |
| `WEB_CONCURRENCY` | the number of CPU cores of the server |
| `DB_POOL_SIZE` | remove this line (the app then picks a safe size) |
| `RAZORPAY_KEY_ID`, `RAZORPAY_SECRET` | your live Razorpay keys |
| `RAZORPAY_WEBHOOK_SECRET` | the secret you choose in step 8 |
| `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD` | from step 9 |
| `CLIENT_ID`, `CLIENT_SECRET`, `REDIRECT_URI` | from step 10 |
| `SQL_SANDBOX_PASS` | a new random value |

### Admin app (`/srv/admin_app/.env`)

| Name | Set it to |
|---|---|
| `APP_ENV` | `production` |
| `SECRET_KEY`, `CSRF_SESSION_KEY`, `TEST_TOKEN_SECRET` | a new random value each |
| `ENROLL_SECRET_KEY`, `DOWNLOAD_SECRET_KEY` | the same values as in the student app's `.env` |
| `DATABASE_HOST`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD` | exactly the same four values as the student app |
| `RAZORPAY_KEY_ID`, `RAZORPAY_SECRET` | your live Razorpay keys |
| `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD` | from step 9 |

The database values are the only thing the two apps share. `ENROLL_SECRET_KEY` and `DOWNLOAD_SECRET_KEY` are equal in both apps on the development Mac today; keep them equal on the servers.

**Done when:** no line in either file still says `your-...` or `change-me`.

## 6. Start the apps as services

**Why:** `python app.py` is the development way. It runs one process and cannot use the fast engine.

### Student server

```bash
sudo cp /srv/user_app/deploy/spp-student.service /etc/systemd/system/
sudo nano /etc/systemd/system/spp-student.service
sudo systemctl daemon-reload
sudo systemctl enable --now spp-student
curl -s http://127.0.0.1:5002/healthz
sudo journalctl -u spp-student -n 40
```

In the service file check the `User=` line and the three `/srv/user_app` paths.

**Done when:** the health line shows `"database":"ok"` and `"redis":"ok"`, and the log does not contain the sentence "gevent is not installed".

The first start creates every table in an empty database. This takes a few seconds.

### Admin server

```bash
cd /srv/admin_app
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
sudo cp deploy/spp-admin.service /etc/systemd/system/
sudo nano /etc/systemd/system/spp-admin.service
sudo systemctl daemon-reload
sudo systemctl enable --now spp-admin
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5001/admin_login
```

**Done when:** the last command prints `200`.

## 7. nginx and https

**Why:** nginx gives https, serves static files quickly and shows the "please wait" page when the app is overloaded.

Point your domain names at the servers first. Then, on the student server:

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo certbot certonly --nginx -d your-domain.com -d www.your-domain.com
sudo cp /srv/user_app/deploy/nginx.conf /etc/nginx/conf.d/spp-student.conf
sudo nano /etc/nginx/conf.d/spp-student.conf
sudo nginx -t && sudo systemctl reload nginx
```

Get the certificate first (second line), because the nginx file refers to it.

In the nginx file replace every `example.com` with your domain (six places) and check the two `/srv/user_app` paths.

On the admin server do the same with `/srv/admin_app/deploy/nginx.conf`, saved as `/etc/nginx/conf.d/spp-admin.conf`, and the admin domain (for example `admin.your-domain.com`).

**Done when:** `https://your-domain.com/healthz` answers in a browser and `https://admin.your-domain.com/admin_login` shows the admin login.

## 8. Razorpay webhook

**Why:** if a student's browser closes right after paying, only the webhook tells the site that the payment succeeded. Without it that student pays and gets nothing until someone fixes it by hand.

In the Razorpay dashboard: Settings, Webhooks, Add new webhook.

| Field | Value |
|---|---|
| Webhook URL | `https://your-domain.com/api/purchase/webhook` |
| Secret | a random value you make up; put the same value in `RAZORPAY_WEBHOOK_SECRET` in `/srv/user_app/.env` |
| Active events | `payment.captured`, `order.paid`, `payment.failed` |

Then restart the student app:

```bash
sudo systemctl restart spp-student
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://your-domain.com/api/purchase/webhook
```

**Done when:** the last command prints `400` (it refuses an unsigned call). `404` means the secret is not set.

One webhook is enough; it covers both course purchases and premium subscriptions.

## 9. Bulk email service

**Why:** a personal Gmail account stops after a few hundred emails a day. Sign-up codes and password resets would then fail for everyone.

1. Open an account with a bulk email service that offers SMTP (for example Amazon SES, Brevo or SendGrid).
2. Verify your sending domain there. They give you DNS records (SPF and DKIM) to add at your domain provider.
3. Put the SMTP details they give you into both `.env` files:

```
MAIL_SERVER=their-smtp-host
MAIL_PORT=587
MAIL_USERNAME=their-smtp-user
MAIL_PASSWORD=their-smtp-password
MAIL_USE_TLS=true
EMAIL_MSGID_DOMAIN=your-domain.com
```

4. Restart both apps and sign up with a new email address.

**Done when:** the sign-up code arrives in the inbox, not in spam.

## 10. Google sign-in

**Why:** the redirect address still says `127.0.0.1`, so "Sign in with Google" fails on the real site.

1. In Google Cloud console open APIs and Services, Credentials, your OAuth client.
2. Under "Authorized redirect URIs" add `https://your-domain.com/callback`.
3. Download the client file and save it on the student server as `/srv/user_app/routes/auth/login/google_signup_login/client_secret.json`. This file is not in git, so it must be copied by hand.
4. In `/srv/user_app/.env` set `REDIRECT_URI=https://your-domain.com/callback` and the matching `CLIENT_ID` and `CLIENT_SECRET`.
5. Restart the student app.

**Done when:** "Sign in with Google" on the real site logs you in.

## 11. Change the admin password

**Why:** the current admin password was pasted into a chat and is written in the files under `scripts/checks/`.

Open the admin login on the real site, use the password reset there, and set a new password. After that the test scripts on the development Mac will no longer be able to log in with the old one; update the password at the top of those scripts only if you still want to run them.

**Done when:** the old password no longer works on the real site.

## 12. Backups

**Why:** the database holds every result, payment and uploaded question image. Nothing copies it anywhere today.

On the database server, a nightly copy:

```bash
sudo mkdir -p /var/backups/spp
sudo crontab -e
```

Add this line (one line):

```
30 2 * * * mysqldump --single-transaction -u root -pYOUR_ROOT_PASSWORD your_database | gzip > /var/backups/spp/db-$(date +\%F).sql.gz
```

On the student server, also copy `/srv/user_app/uploads/` (student recordings) to another disk or machine every night. The admin's uploaded files do not need a separate backup, because they are inside the database.

**Done when:** a file appears in `/var/backups/spp/` the next morning, and you have restored it once into a test database to see that it works.

## 13. Load test on the real server

**Why:** every capacity number so far was measured on a laptop. The real limit of your server is unknown until you test it.

Do this before the site is public, from a second machine that has the project's `scripts/` folder:

1. On the student server add `RATELIMIT_ENABLED=0` to `.env` and restart. All test students come from one address and would otherwise be blocked.
2. Run, raising `--users` each time (200, 500, 1000, 2000):

```bash
python scripts/load/load_test.py --base https://your-domain.com --users 500 --duration 60 --scenario browse --think 2
python scripts/load/load_test.py --base https://your-domain.com --users 500 --duration 60 --scenario exam --think 5 --submit-spread 5
```

3. Stop raising when the middle response time passes one second or errors appear. The step before that is what your server carries.
4. Remove `RATELIMIT_ENABLED=0` and restart. Do not forget this.

The tool needs database access to create and remove its test accounts, so run it where `user_app/.env` points to the same database.

**Done when:** you know the number of students your server carries with no errors, and rate limits are on again.

---

## Later, when one server is not enough

Not needed for the first launch. One server of 8 to 10 cores should carry roughly 5,000 students inside a test at the same time (an estimate from laptop measurements).

| Need | What to do |
|---|---|
| More students | Add student servers behind a load balancer. All use the same MySQL and the same Redis. Use sticky sessions for `/socket.io/`. |
| Student recordings on several servers | Set `UPLOAD_BASE` on every student server to one disk they all share. |
| Coding exams for many students | Set `JUDGE_MODE=queue` on the student servers and run `deploy/spp-judge-worker.service` on separate judge machines with the same `REDIS_URL`. |
| One lakh at the same moment | About 20 student servers, a large MySQL server and separate judge machines. Test it before promising it. |

## Already done, nothing to do

So you do not look for these:

- The database connection pool, the multi-worker server setup and the rate limits.
- A dropped MySQL connection is replaced by itself.
- Test submission retries by itself and cannot be stored twice.
- The two apps are separate; admin uploads travel through the database.
- The "please wait" page for an overloaded server (`user_app/deploy/busy.html`, already wired into the nginx file).
- `robots.txt` and `sitemap.xml`.
