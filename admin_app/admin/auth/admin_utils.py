import hashlib
import hmac
import logging
import time
import bcrypt
from flask import current_app, request, session

logger = logging.getLogger(__name__)

ADMIN_LOGIN_ATTEMPT_LIMIT = 5
ADMIN_LOCKOUT_TIME = 300

USER_LOGIN_ATTEMPT_LIMIT = 5
USER_LOCKOUT_TIME = 300

RESET_REQUEST_LIMIT = 3
RESET_REQUEST_WINDOW = 900
RESET_REQUEST_LOCKOUT = 900


def _client_ip():
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _identifiers(email=None):
    keys = [f"ip:{_client_ip()}"]
    target = (email or session.get('admin_email_pending') or '').strip().lower()
    if target:
        keys.append(f"account:{target}")
    return keys


def _attempts_db():
    from admin.auth.admin_db import UserOperation
    return UserOperation()


def is_admin_locked_out(email=None):
    try:
        db = _attempts_db()
        return any(db.is_locked_out(key) for key in _identifiers(email))
    except Exception:
        logger.exception("Lockout check failed; allowing request")
        return False


def increment_admin_login_attempts(email=None):
    try:
        db = _attempts_db()
        for key in _identifiers(email):
            db.register_failed_attempt(key, ADMIN_LOGIN_ATTEMPT_LIMIT, ADMIN_LOCKOUT_TIME)
    except Exception:
        logger.exception("Could not record failed admin login attempt")


def reset_admin_login_attempts(email=None):
    try:
        db = _attempts_db()
        for key in _identifiers(email):
            db.clear_attempts(key)
    except Exception:
        logger.exception("Could not clear admin login attempts")


def verify_password(input_password, hashed_password):
    try:
        return bcrypt.checkpw(input_password.encode(), hashed_password.encode())
    except Exception:
        return False


def hash_password(password):
    try:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    except Exception:
        return None


def password_fingerprint(password_hash):
    secret = (current_app.config.get('SECRET_KEY') or '').encode()
    return hmac.new(secret, (password_hash or '').encode(), hashlib.sha256).hexdigest()[:32]


def _reset_identifiers(email):
    keys = [f"reset:ip:{_client_ip()}"]
    target = (email or '').strip().lower()
    if target:
        keys.append(f"reset:account:{target}"[:190])
    return keys


def is_reset_throttled(email=None):
    try:
        db = _attempts_db()
        return any(db.is_locked_out(key) for key in _reset_identifiers(email))
    except Exception:
        logger.exception("Reset throttle check failed; allowing request")
        return False


def register_reset_request(email=None):
    try:
        db = _attempts_db()
        for key in _reset_identifiers(email):
            db.register_reset_request(key, RESET_REQUEST_LIMIT, RESET_REQUEST_WINDOW, RESET_REQUEST_LOCKOUT)
    except Exception:
        logger.exception("Could not record admin password reset request")
