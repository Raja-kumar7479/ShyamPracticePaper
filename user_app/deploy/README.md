# Student app: server files

This folder belongs to the student app only. The app is deployed on its own; copy the whole `user_app` folder to the server (the examples use `/srv/user_app`). The admin app is deployed separately from its own folder. The two share one thing: the MySQL database.

Replace `example.com`, the paths, the `spp` user and every password before use.

| File | Where it goes | What to change |
|---|---|---|
| `mysql-scale.cnf` | `/etc/mysql/conf.d/` on the database server, then restart MySQL | `innodb_buffer_pool_size` (half the memory of the database server), `max_connections` |
| `create_app_db_user.sql` | run once as the MySQL root user | the password and `YOUR_DATABASE_NAME`; then put `spp_app` and the password in `.env` |
| `nginx.conf` | `/etc/nginx/conf.d/spp-student.conf` | the domain names, the certificate paths, the two `/srv/user_app` paths |
| `busy.html` | stays here; nginx serves it for 502, 503 and 504 | nothing |
| `spp-student.service` | `/etc/systemd/system/` | paths and the user |
| `spp-judge-worker.service` | `/etc/systemd/system/` on each judge host | paths; the user must be allowed to run Docker |

The database files are the same in the admin app's folder. Apply them once; it does not matter from which folder.

Order on a new server:

1. Install Redis, nginx, Docker and Python. Create a virtual environment inside this folder (`python -m venv .venv`) and install `requirements.txt`.
2. Fill in `.env` (start from `.env.example`). Set `APP_ENV=production`, `REDIS_URL`, `WEBSITE_URL`, `WEB_CONCURRENCY` and the database user.
3. Build the judge image: `docker build -f docker/Dockerfile.judge -t codejudge-runner:latest docker`.
4. Enable the service: `systemctl enable --now spp-student`. The first start creates every table, including the ones the admin app uses.
5. Put `nginx.conf` in place and reload nginx.
6. Check `https://your-domain/practice-coding/api/judge/health`.

Files the admin uploads (question images, notes, syllabus) reach this server through the database. The first time a student opens one, it is copied into `uploads/` here. Student recordings and photos stay in `uploads/` on this server; with several student servers, point `UPLOAD_BASE` at a disk they all share.

For separate judge hosts, set `JUDGE_MODE=queue` in `.env` on the web servers and enable `spp-judge-worker` on each judge host with the same `REDIS_URL`.
