import atexit
import functools
import logging
import os
import queue
import socket
import threading
import time
from email.utils import make_msgid as _stdlib_make_msgid
from flask import current_app
from flask_mail import Mail, Message

logger = logging.getLogger(__name__)
mail = Mail()

EMAIL_ASYNC = os.environ.get('EMAIL_ASYNC', '1').strip().lower() not in ('0', 'false', 'no', 'off')
EMAIL_WORKERS = max(1, int(os.environ.get('EMAIL_WORKERS', '4')))
EMAIL_QUEUE_MAX = max(1, int(os.environ.get('EMAIL_QUEUE_MAX', '5000')))
_IDLE_SECONDS = 5.0
_SHUTDOWN_WAIT = 10.0

_queue = queue.Queue(maxsize=EMAIL_QUEUE_MAX)


_msgid_domain = None


def _resolve_msgid_domain():
    explicit = (os.environ.get('EMAIL_MSGID_DOMAIN') or '').strip()
    if explicit:
        return explicit
    sender = (os.environ.get('MAIL_DEFAULT_SENDER') or os.environ.get('MAIL_USERNAME') or '')
    if '@' in sender:
        domain = sender.rsplit('@', 1)[1].strip(" '\"<>)")
        if domain:
            return domain
    try:
        return socket.gethostname() or 'localhost'
    except Exception:
        return 'localhost'


def _fast_make_msgid(idstring=None, domain=None):
    global _msgid_domain
    if domain is None:
        if _msgid_domain is None:
            _msgid_domain = _resolve_msgid_domain()
        domain = _msgid_domain
    return _stdlib_make_msgid(idstring, domain)


try:
    import flask_mail as _flask_mail
    if hasattr(_flask_mail, 'make_msgid'):
        _flask_mail.make_msgid = _fast_make_msgid
except Exception:
    logger.exception("EMAIL: could not install the fast Message-ID builder")


socket.getfqdn = functools.lru_cache(maxsize=None)(socket.getfqdn)


def _prime_hostname():
    try:
        socket.getfqdn()
    except Exception:
        pass
_started = False
_start_lock = threading.Lock()

BRAND_PRIMARY = "#4f46e5"
BRAND_DARK = "#111827"


def _brand():
    try:
        return current_app.config.get("BRAND_NAME", "Shyam Practice Paper")
    except Exception:
        return "Shyam Practice Paper"


def render_email(heading, body_html, cta_text=None, cta_url=None, preheader=""):
    brand = _brand()
    button = ""
    if cta_text and cta_url:
        button = (
            f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:8px 0 6px;">'
            f'<tr><td align="center" bgcolor="{BRAND_PRIMARY}" style="border-radius:8px;">'
            f'<a href="{cta_url}" style="display:inline-block;padding:13px 34px;font-size:15px;'
            f'font-weight:600;color:#ffffff;text-decoration:none;">{cta_text}</a>'
            f'</td></tr></table>'
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
<span style="display:none;max-height:0;overflow:hidden;opacity:0;">{preheader}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:28px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 8px 30px rgba(2,6,23,.08);">
<tr><td style="background:linear-gradient(135deg,{BRAND_PRIMARY},#7c3aed);padding:26px 32px;">
<span style="color:#ffffff;font-size:20px;font-weight:700;letter-spacing:.3px;">{brand} · Admin</span>
</td></tr>
<tr><td style="padding:34px 32px 12px;">
<h1 style="margin:0 0 14px;font-size:22px;line-height:1.3;color:{BRAND_DARK};">{heading}</h1>
<div style="font-size:15px;line-height:1.65;color:#334155;">{body_html}</div>
{button}
</td></tr>
<tr><td style="padding:22px 32px 30px;border-top:1px solid #f1f5f9;">
<p style="margin:0;font-size:12px;line-height:1.6;color:#94a3b8;">This is a security email for your {brand} admin account. If you did not request this, no action is needed and your account remains secure.</p>
<p style="margin:10px 0 0;font-size:12px;color:#cbd5e1;">&copy; {brand}. All rights reserved.</p>
</td></tr>
</table>
</td></tr>
</table>
</body></html>"""


def _build(subject, recipients, html, attachments):
    msg = Message(subject=subject, recipients=recipients)
    msg.html = html
    for name, content_type, data in (attachments or ()):
        msg.attach(name, content_type, data)
    return msg


def _deliver(conn, item):
    subject, recipients, html, attachments, attempt = item
    try:
        conn.send(_build(subject, recipients, html, attachments))
        logger.info("EMAIL: sent to %s (subject=%s)", recipients, subject)
    except Exception as e:
        if attempt == 0:
            logger.warning("EMAIL: send to %s failed (%s); retrying once", recipients, e)
            _enqueue((subject, recipients, html, attachments, 1))
        else:
            logger.error("EMAIL: gave up on %s (subject=%s): %s", recipients, subject, e)


def _worker(app):
    while True:
        item = _queue.get()
        with app.app_context():
            try:
                with mail.connect() as conn:
                    while item is not None:
                        _deliver(conn, item)
                        try:
                            item = _queue.get(timeout=_IDLE_SECONDS)
                        except queue.Empty:
                            item = None
            except Exception as e:
                logger.error("EMAIL: SMTP connection failed: %s", e)
                if item is not None:
                    subject, recipients, html, attachments, attempt = item
                    if attempt == 0:
                        _enqueue((subject, recipients, html, attachments, 1))
                    else:
                        logger.error("EMAIL: gave up on %s (subject=%s): no SMTP connection",
                                     recipients, subject)
                time.sleep(1)


def _enqueue(item):
    try:
        _queue.put_nowait(item)
        return True
    except queue.Full:
        return False


def _flush_on_exit():
    deadline = time.time() + _SHUTDOWN_WAIT
    while not _queue.empty() and time.time() < deadline:
        time.sleep(0.2)
    if not _queue.empty():
        logger.warning("EMAIL: %d message(s) still queued at shutdown", _queue.qsize())


def _ensure_workers(app):
    global _started
    if _started:
        return
    with _start_lock:
        if _started:
            return
        threading.Thread(target=_prime_hostname, daemon=True, name="email-dns-prime").start()
        for i in range(EMAIL_WORKERS):
            threading.Thread(target=_worker, args=(app,), daemon=True,
                             name=f"email-worker-{i}").start()
        atexit.register(_flush_on_exit)
        _started = True
        logger.info("EMAIL: %d background sender(s) started (queue max %d)",
                    EMAIL_WORKERS, EMAIL_QUEUE_MAX)


def send_email(subject, recipients, html, attachments=None, background=None):
    if isinstance(recipients, str):
        recipients = [recipients]
    use_background = EMAIL_ASYNC if background is None else background

    if use_background:
        try:
            _ensure_workers(current_app._get_current_object())
            if _enqueue((subject, recipients, html, attachments, 0)):
                return True
            logger.warning("EMAIL: queue is full; sending to %s inline", recipients)
        except Exception:
            logger.exception("EMAIL: could not queue; sending inline")

    try:
        mail.send(_build(subject, recipients, html, attachments))
        logger.info("EMAIL: sent to %s (subject=%s)", recipients, subject)
        return True
    except Exception as e:
        logger.error("EMAIL: send failed to %s: %s", recipients, e)
        return False
