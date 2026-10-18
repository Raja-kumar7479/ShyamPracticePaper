from functools import wraps
from flask import flash, redirect, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO
import logging
import os
import redis

logger = logging.getLogger(__name__)

redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
is_redis_available = False

try:
    r_check = redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
    r_check.ping()
    is_redis_available = True
    logger.info("Redis detected. Using High-Scale configuration.")
except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError):
    logger.warning("Redis NOT detected (Timeout/Refused). Falling back to in-memory mode (Dev Only).")
    is_redis_available = False
except Exception as e:
    logger.warning("Redis check failed unexpectedly: %s. Falling back.", e)
    is_redis_available = False

redis_pool = None
storage_options = {}
if is_redis_available:
    redis_pool = redis.BlockingConnectionPool.from_url(
        redis_url, max_connections=max(8, int(os.environ.get('REDIS_POOL_SIZE', '64'))), timeout=15)
    socketio = SocketIO(message_queue=redis_url)
    storage_uri = redis_url
    storage_options = {'connection_pool': redis_pool}
else:
    socketio = SocketIO()
    storage_uri = "memory://"

def rate_limit_key():
    try:
        email = session.get('user_email')
        if email and not str(email).startswith('guest_'):
            return f"user:{email}"
    except Exception:
        pass
    return get_remote_address()


limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=["3000 per hour", "30000 per day"],
    headers_enabled=True,
    storage_uri=storage_uri,
    storage_options=storage_options
)


def init_limiter(app):
    limiter.init_app(app)


def user_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_username' not in session or 'user_email' not in session:
            flash("Access denied. Please log in to continue.", 'error')
            next_url = request.path
            return redirect(url_for('users.user_login', next=next_url))
        return f(*args, **kwargs)
    return decorated_function
