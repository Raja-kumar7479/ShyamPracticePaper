
import argparse
import logging
import os
import threading
import time

from admin.manage_modules.content_db import UserOperation

logger = logging.getLogger(__name__)

_LOCK_NAME = 'spp_content_expiry'
_FLASK_APP = None


def _app_context():
    global _FLASK_APP
    if _FLASK_APP is None:
        try:
            from app import app as flask_app
            _FLASK_APP = flask_app
        except Exception:
            logger.warning("EXPIRY: no Flask app available; emails cannot be sent from this run")
            return None
    return _FLASK_APP.app_context()


def _with_lock(user_op, fn):
    conn = user_op.connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT GET_LOCK(%s, 0)", (_LOCK_NAME,))
        got = (cursor.fetchone() or [0])[0]
        if not got:
            logger.info("EXPIRY: another process holds the lock; skipping this run")
            return None
        try:
            return fn()
        finally:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (_LOCK_NAME,))
            cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def run_cleanup(dry_run=False):
    user_op = UserOperation()

    def work():
        dropped = reminded = 0
        try:
            dropped = 0 if dry_run else user_op.purge_abandoned_subscription_orders()
            if dropped:
                logger.info("EXPIRY: removed %d unpaid subscription order(s) older than a day", dropped)
        except Exception:
            logger.exception("EXPIRY: could not clear abandoned subscription orders")

        try:
            reminded = 0 if dry_run else send_expiry_reminders()
            if reminded:
                logger.info("EXPIRY: sent %d premium expiry reminder(s)", reminded)
        except Exception:
            logger.exception("EXPIRY: could not send premium expiry reminders")

        report = {'orders_removed': dropped, 'reminders_sent': reminded}
        logger.info("EXPIRY: run finished - %s", report)
        return report

    return _with_lock(user_op, work)


def send_expiry_reminders():
    from admin.manage_modules.content_db import UserOperation as _Ops
    ops = _Ops()
    rows = ops.subscriptions_needing_reminder(days_before=3)
    if not rows:
        return 0
    ctx = _app_context()
    if ctx is None:
        return 0
    with ctx:
        return _send_reminder_batch(ops, rows)


def _send_reminder_batch(ops, rows):
    sent = 0
    for row in rows:
        try:
            from email_service import render_email, send_email
        except Exception:
            logger.warning("EXPIRY: email service unavailable; reminders skipped")
            return sent
        course = row.get('course_code') or 'your courses'
        expires = row.get('expires_at')
        when = expires.strftime('%d %b %Y, %I:%M %p') if expires else ''
        body = (f"<p>Hi {row.get('username') or 'there'},</p>"
                f"<p>Your <strong>{row.get('plan', '').title()}</strong> premium subscription for "
                f"<strong>{course}</strong> ends on <strong>{when}</strong>.</p>"
                f"<p>After that, every item marked Premium in {course} locks again. "
                f"You can buy premium for {course} again once this one has ended.</p>")
        try:
            html = render_email("Your premium subscription is ending soon", body,
                                preheader=f"Premium for {course} ends {when}")
            if send_email(f"Your {course} Premium ends soon", row['email'], html):
                ops.mark_reminder_sent(row['id'])
                sent += 1
        except Exception:
            logger.exception("EXPIRY: reminder email failed for %s", row.get('email'))
    return sent


def start_expiry_scheduler(app=None):
    global _FLASK_APP
    if app is not None:
        _FLASK_APP = app
    """Run the job on a timer inside the admin app.

    Off with CONTENT_EXPIRY_JOB=0; the interval is CONTENT_EXPIRY_INTERVAL_MIN
    minutes (10 by default). The advisory lock means running cron as well is
    harmless.
    """
    if os.environ.get('CONTENT_EXPIRY_JOB', '1') == '0':
        logger.info("EXPIRY: scheduler disabled by CONTENT_EXPIRY_JOB=0")
        return None
    reloader_on = not bool(os.environ.get('RENDER') or os.environ.get('GUNICORN_CMD_ARGS'))
    if reloader_on and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return None

    try:
        minutes = max(1, int(os.environ.get('CONTENT_EXPIRY_INTERVAL_MIN', '10')))
    except ValueError:
        minutes = 10

    def loop():
        time.sleep(30)
        while True:
            try:
                run_cleanup()
            except Exception:
                logger.exception("EXPIRY: scheduled run failed")
            time.sleep(minutes * 60)

    thread = threading.Thread(target=loop, name='content-expiry', daemon=True)
    thread.start()
    logger.info("EXPIRY: scheduler started, every %d minute(s)", minutes)
    return thread


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete or archive expired course content.")
    parser.add_argument('--dry-run', action='store_true', help="only report what would happen")
    args = parser.parse_args()

    from logging_config import configure_logging
    configure_logging()
    print(run_cleanup(dry_run=args.dry_run))
