# User App - Production Deployment Checklist

## Environment variables

Copy `user_app/.env.example` to `.env` and fill every value. The ones that
gate production behavior:

| Variable | Why it matters |
| --- | --- |
| `APP_ENV=production` | The reliable production switch: ProxyFix, secure cookies, https links, strict OAuth transport. Render/PythonAnywhere/gunicorn are auto-detected, but set this anyway. |
| `SECRET_KEY` | App refuses to start without it. Long random string. |
| `WEBSITE_URL` | Used in emailed links and Socket.IO allowed origins. |
| `REDIS_URL` | Without it: rate limits are per-worker, Socket.IO events do not cross workers, sessions sit on local disk. Required for more than one worker. A critical log line fires at startup if missing in production. |
| `RAZORPAY_KEY_ID` / `RAZORPAY_SECRET` | Payments 503 without them. Startup logs a critical line if missing. |
| `RAZORPAY_WEBHOOK_SECRET` | Enables `/practice-coding/api/subscribe/webhook` so a paid subscription activates even if the buyer's browser never returns. Register the webhook (event `payment.captured`) in the Razorpay dashboard. |
| `REDIRECT_URI` | Google OAuth callback for the deployed domain, e.g. `https://your-domain/callback`. Must match the Google console entry. |
| `UPLOAD_BASE` | Defaults to the `uploads` folder inside the app. On hosts with ephemeral disks point this at a persistent volume, or every exam recording is lost on redeploy. |

## Process model

- `Procfile`: `gunicorn --worker-class eventlet -w 1 wsgi:app`. Eventlet is
  monkey-patched in `wsgi.py` before anything else imports; keep `wsgi:app`
  as the entry point.
- More than one worker (or more than one instance) requires `REDIS_URL`.
- PythonAnywhere runs uWSGI without eventlet: Socket.IO falls back to
  long-polling automatically; nothing to configure.

## Monitoring

- `GET /healthz` - returns `200 {"status":"ok"}` with database and redis
  checks, `503` when the database is unreachable. Rate-limit exempt; point
  the uptime monitor here.
- Logs: stdout plus rotating `user_app/logs/app.log` (5 MB x 5). Startup
  prints critical lines for any missing production configuration.

## Data

- `user_app/uploads/` holds exam recordings, organized
  `<kind>/<round>/<test_key>/<per-user-folder>/`. Back this directory up; it
  is user work product.
- MySQL pool: 16 connections per worker by default (`DB_POOL_SIZE`).

## Smoke test after deploy

1. `curl https://your-domain/healthz` returns 200.
2. Log in, open a course dashboard, start and submit one free communication
   test end to end (audio question included).
3. Buy nothing, but open the premium page and confirm the Razorpay window
   shows the ShyamPracticePaper logo over https.
4. Check `logs/app.log` for `PRODUCTION CONFIG INCOMPLETE` or
   `PRODUCTION WITHOUT REDIS` lines.
