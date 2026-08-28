import logging
import time
from urllib.parse import urljoin, urlparse

import bcrypt
from flask import request, session

logger = logging.getLogger(__name__)

USER_LOGIN_ATTEMPT_LIMIT = 5
USER_LOCKOUT_TIME = 300


def is_safe_url(target):
    """True only for a URL on this host.

    Shared so signup, Google login and set-password validate `next` the same
    way login always did. Each of those used to follow `next` unchecked, which
    let a crafted link bounce a user to an external site straight after a
    successful sign-in.
    """
    if not target:
        return False
    # Browsers read a backslash in the authority position as a slash, so
    # "/\evil.com" navigates to evil.com even though urlparse reads it as a
    # path on this host. Rejecting backslashes outright closes that gap;
    # no legitimate route on this site contains one.
    if '\\' in target:
        return False
    try:
        ref_url = urlparse(request.host_url)
        test_url = urlparse(urljoin(request.host_url, target))
    except Exception:
        return False
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


def safe_next_url(target, fallback=None):
    """The target if it is local, otherwise the fallback."""
    return target if is_safe_url(target) else fallback


# ---------------------------------------------------------------- lockout
# Attempts used to be counted in the visitor's own session, so discarding the
# cookie reset the counter and the 5-attempt lockout never bit. They are kept
# server-side now, keyed on the client IP and the account being targeted.
def _client_ip():
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _identifiers(email=None):
    keys = [f"ip:{_client_ip()}"]
    target = (email or session.get('user_email_pending') or '').strip().lower()
    if target:
        keys.append(f"account:{target}")
    return keys


def _attempts_db():
    from routes.auth.database.auth_db import AuthOperation
    return AuthOperation()


def is_user_locked_out(email=None, strict=False):
    """Whether this client, or the account it is targeting, is locked out.

    Pass strict=True where a password is actually being checked. If the attempt
    store cannot be read there, report a lockout rather than waving the guess
    through: sign-in needs that same database anyway, so failing open buys a
    caller nothing except an unmetered window to guess in. Plain page views stay
    permissive, so a brief database problem does not greet every visitor with a
    lockout notice.
    """
    try:
        db = _attempts_db()
        return any(db.is_locked_out(key) for key in _identifiers(email))
    except Exception:
        logger.exception("Lockout check failed (strict=%s)", strict)
        return strict


def increment_user_login_attempts(email=None):
    try:
        db = _attempts_db()
        for key in _identifiers(email):
            db.register_failed_attempt(key, USER_LOGIN_ATTEMPT_LIMIT, USER_LOCKOUT_TIME)
    except Exception:
        logger.exception("Could not record a failed login attempt")


def reset_user_login_attempts(email=None):
    try:
        db = _attempts_db()
        for key in _identifiers(email):
            db.clear_attempts(key)
    except Exception:
        logger.exception("Could not clear login attempts")


def verify_password(input_password, hashed_password):
    try:
        return bcrypt.checkpw(input_password.encode(), hashed_password.encode())
    except Exception:
        return False


def rebuild_session_at_login(preserve=('course_code', 'unique_code', 'user_login_next_url')):
    from flask import session as _session
    kept = {}
    for key in preserve:
        value = _session.get(key)
        if value is not None:
            kept[key] = value
    _session.clear()
    for key, value in kept.items():
        _session[key] = value
    _session.permanent = True
