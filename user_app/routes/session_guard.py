import logging
import secrets
import threading
import time

from flask import session

from extensions import redis_pool
from routes.db_pool import get_connection

logger = logging.getLogger(__name__)

_KEY = 'spp:active:'
_TTL_SECONDS = 12 * 3600
_CACHE_SECONDS = 15.0
_CACHE_MAX = 200000
_cache = {}
_cache_lock = threading.Lock()


def _redis():
    if redis_pool is None:
        return None
    import redis
    return redis.Redis(connection_pool=redis_pool)


def _db_get(email):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT active_session FROM auth WHERE email = %s LIMIT 1", (email,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        cur.close()
        conn.close()


def _db_set(email, token):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE auth SET active_session = %s WHERE email = %s", (token, email))
        conn.commit()
    finally:
        cur.close()
        conn.close()


def _remember(email, token):
    with _cache_lock:
        if len(_cache) >= _CACHE_MAX:
            _cache.clear()
        _cache[email] = (token, time.monotonic())


def register_login(email):
    token = secrets.token_hex(16)
    session['_sid'] = token
    try:
        _db_set(email, token)
    except Exception:
        logger.exception("SESSION GUARD: could not store the active session for %s", email)
    client = _redis()
    if client is not None:
        try:
            client.set(_KEY + email, token, ex=_TTL_SECONDS)
        except Exception:
            logger.warning("SESSION GUARD: redis write failed for %s", email)
    _remember(email, token)
    return token


def current_token(email):
    client = _redis()
    if client is not None:
        try:
            value = client.get(_KEY + email)
            if value:
                return value.decode() if isinstance(value, bytes) else str(value)
        except Exception:
            logger.warning("SESSION GUARD: redis read failed for %s", email)
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(email)
    if hit and now - hit[1] < _CACHE_SECONDS:
        return hit[0]
    try:
        token = _db_get(email)
    except Exception:
        logger.exception("SESSION GUARD: could not read the active session for %s", email)
        return hit[0] if hit else None
    _remember(email, token)
    if client is not None and token:
        try:
            client.set(_KEY + email, token, ex=_TTL_SECONDS)
        except Exception:
            pass
    return token


def is_replaced():
    email = session.get('user_email')
    if not email or str(email).startswith('guest_'):
        return False
    mine = session.get('_sid')
    current = current_token(email)
    if not mine:
        if current:
            session['_sid'] = current
        else:
            register_login(email)
        return False
    return bool(current) and current != mine


def running_test_elsewhere(email):
    try:
        from routes.exam_platform.active_test_lock import get_active_test
        return get_active_test(email) is not None
    except Exception:
        logger.exception("SESSION GUARD: could not check for a running test for %s", email)
        return False
