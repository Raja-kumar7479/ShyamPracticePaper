import logging
import time
from urllib.parse import urljoin, urlparse

import bcrypt
from flask import request, session

logger = logging.getLogger(__name__)

USER_LOGIN_ATTEMPT_LIMIT = 5
USER_LOCKOUT_TIME = 300


def is_safe_url(target):
    if not target:
        return False
    if '\\' in target:
        return False
    try:
        ref_url = urlparse(request.host_url)
        test_url = urlparse(urljoin(request.host_url, target))
    except Exception:
        return False
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


def safe_next_url(target, fallback=None):
    return target if is_safe_url(target) else fallback


def _client_ip():
    return request.remote_addr or 'unknown'


def _identifiers(email=None):
    target = (email or session.get('user_email_pending') or '').strip().lower()
    if not target:
        return []
    return [f"pair:{_client_ip()}|{target}"]


def _attempts_db():
    from routes.auth.database.auth_db import AuthOperation
    return AuthOperation()


def is_user_locked_out(email=None, strict=False):
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


def _offload(fn, *args):
    try:
        from gevent import monkey
        if monkey.is_module_patched('socket'):
            import gevent
            return gevent.get_hub().threadpool.apply(fn, args)
    except ImportError:
        pass
    return fn(*args)


def verify_password(input_password, hashed_password):
    try:
        return bool(_offload(bcrypt.checkpw, input_password.encode(), hashed_password.encode()))
    except Exception:
        return False


def hash_password(password):
    salt = bcrypt.gensalt()
    return _offload(bcrypt.hashpw, password.encode(), salt).decode()


def rebuild_session_at_login(preserve=('course_code', 'unique_code', 'user_login_next_url', '_sid')):
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
