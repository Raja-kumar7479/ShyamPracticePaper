# Admin app: server files

This folder belongs to the admin app only. The app is deployed on its own; copy the whole `admin_app` folder to the server (the examples use `/srv/admin_app`). The student app is deployed separately from its own folder. The two share one thing: the MySQL database.

Replace `admin.example.com`, the paths, the `spp` user and every password before use.

| File | Where it goes | What to change |
|---|---|---|
| `mysql-scale.cnf` | `/etc/mysql/conf.d/` on the database server, then restart MySQL | `innodb_buffer_pool_size`, `max_connections` |
| `create_app_db_user.sql` | run once as the MySQL root user | the password and `YOUR_DATABASE_NAME`; then put `spp_app` and the password in `.env` |
| `nginx.conf` | `/etc/nginx/conf.d/spp-admin.conf` | the domain name and the certificate paths |
| `spp-admin.service` | `/etc/systemd/system/` | paths and the user |

The database files are the same in the student app's folder. Apply them once; it does not matter from which folder.

Order on a new server:

1. Install nginx and Python. Create a virtual environment inside this folder (`python -m venv .venv`) and install `requirements.txt`.
2. Fill in `.env` with the same database name, user and password the student app uses.
3. Enable the service: `systemctl enable --now spp-admin`. The first start creates every table if the student app has not already done so.
4. Put `nginx.conf` in place and reload nginx.

Every file uploaded here (question images, notes, syllabus) is kept in `uploads/` on this server and also written to the database, which is how the student app receives it. If this server's disk is replaced, the files are copied back from the database when they are next opened.
