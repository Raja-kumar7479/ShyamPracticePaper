# Shyam Practice Paper — Exam & Courses Platform

The project is **two independent Flask applications**. Each one is deployed on
its own, from its own folder. The only thing they share is one MySQL database
(the same credentials, written in each app's own `.env`).

| App          | Folder       | Port | Role                                        |
|--------------|--------------|------|---------------------------------------------|
| User portal  | `user_app/`  | 5002 | Everything end users see (courses, exams, practice, proctoring) |
| Admin portal | `admin_app/` | 5001 | Content management (courses, tests, notes, questions, purchases) |

```
shyampracticepp/
├── user_app/                 # User-facing Flask app (blueprint: "users")
│   ├── app.py  wsgi.py  Procfile  runtime.txt  gunicorn.conf.py
│   ├── config.py  extensions.py  logging_config.py  db_bootstrap.py
│   ├── requirements.txt  .env  .env.example
│   ├── database/  migrations/  # every table and migration, for both apps
│   ├── deploy/               # nginx, service and database files for this app
│   ├── uploads/              # files on this server (student recordings, cached admin files)
│   ├── routes/  templates/users/  static/
│
├── admin_app/                # Admin Flask app (blueprint: "admin")
│   ├── app.py  wsgi.py  Procfile  runtime.txt
│   ├── config.py  extensions.py  logging_config.py  db_bootstrap.py
│   ├── requirements.txt  .env  .env.example
│   ├── database/  migrations/  # every table and migration, for both apps
│   ├── deploy/               # nginx, service and database files for this app
│   ├── uploads/              # files the admin uploaded
│   ├── admin/  templates/admin/  static/
│
├── docs/                     # notes for developers; not used by either app
└── scripts/                  # test and load tools for a developer machine; not deployed
```

## What the two apps have in common

- **Database only.** Both apps connect to the same MySQL database. Whichever
  app starts first creates every table; the other finds them already there.
  Each app carries a full copy of the schema and migration files, so keep the
  two copies the same (`scripts/checks/separate_apps_check.py` checks this).
- **Uploaded files travel through the database.** A file the admin uploads is
  saved in `admin_app/uploads/` and written to the `shared_files` tables. The
  student app copies it into `user_app/uploads/` the first time it is opened.
  Student recordings and photos stay on the student server.
- Nothing else is shared: no common folder, no common Python file, and neither
  app imports the other.

## Running locally (two terminals)

```bash
# Terminal 1 — user app on :5002
cd user_app
pip install -r requirements.txt      # first time only
cp .env.example .env                 # then fill in real values
python app.py

# Terminal 2 — admin app on :5001
cd admin_app
pip install -r requirements.txt      # first time only
cp .env.example .env                 # same DB credentials as user app
python app.py
```

- User portal:  http://127.0.0.1:5002
- Admin portal: http://127.0.0.1:5001  (redirects to `/admin_login`)

Redis is optional; without it the user app uses client-side cookie sessions.

## Production

Each app has its own `Procfile` and its own `deploy/` folder with a short
README:

- `user_app/Procfile`  → `gunicorn -c gunicorn.conf.py wsgi:app`
- `admin_app/Procfile` → `gunicorn -w 2 wsgi:app`

Deploy each folder as its own service and give both the same database
credentials. No shared disk is needed between them.

## Logging

Each app configures logging once in its own `logging_config.py` (rotating file
`logs/app.log` + console). Modules only do `logger = logging.getLogger(__name__)`
— never `logging.basicConfig()`. Control verbosity with `LOG_LEVEL`.
