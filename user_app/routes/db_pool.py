import logging
import os
import queue
import select
import time
import threading
from mysql.connector import errors as mysql_errors
from mysql.connector import pooling
from config import Config

logger = logging.getLogger(__name__)

_POOL = None
_RETRY_AT = 0.0
_RETRY_SECONDS = 2.0
_BUILD_LOCK = threading.Lock()
_WORKERS = max(1, int(os.environ.get('WEB_CONCURRENCY', '1') or 1))
_POOL_SIZE = max(2, min(int(os.environ.get('DB_POOL_SIZE', str(max(4, 96 // _WORKERS)))), 32))
_WAIT_SECONDS = max(1.0, float(os.environ.get('DB_POOL_WAIT', '15')))
_PING_AFTER_IDLE = 20.0
_ISOLATION = "SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED"
_DETECT_NESTED = (os.environ.get('DB_POOL_DETECT_NESTED') == '1'
                  or os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.detect_nested')))
_held = {}
_held_lock = threading.Lock()


def _note_checkout(conn):
    import traceback
    ident = threading.get_ident()
    with _held_lock:
        count = _held.get(ident, 0)
        _held[ident] = count + 1
    conn._spp_owner = ident
    if count:
        stack = [ln for ln in traceback.format_stack(limit=18) if '/user_app/' in ln and 'db_pool.py' not in ln]
        logger.warning("DB POOL NESTED CHECKOUT (already holding %d):\n%s", count, ''.join(stack[-5:]))


def _note_return(conn):
    ident = getattr(conn, '_spp_owner', None)
    if ident is None:
        return
    with _held_lock:
        left = _held.get(ident, 0) - 1
        if left > 0:
            _held[ident] = left
        else:
            _held.pop(ident, None)


def _guard(cnx):
    if getattr(cnx, '_spp_guarded', False):
        return
    send = getattr(cnx, '_send_cmd', None)
    if send is None:
        return

    def guarded(*args, **kwargs):
        try:
            return send(*args, **kwargs)
        except (mysql_errors.InterfaceError, mysql_errors.OperationalError):
            cnx._spp_broken = True
            raise

    try:
        cnx._send_cmd = guarded
        cnx._spp_guarded = True
    except Exception:
        pass


def _socket_closed(cnx):
    try:
        sock = cnx._socket.sock
    except AttributeError:
        return False
    if sock is None:
        return True
    try:
        readable, _, _ = select.select([sock], [], [], 0)
    except Exception:
        return True
    return bool(readable)


class _PooledConnection(pooling.PooledMySQLConnection):
    def close(self):
        cnx = self._cnx
        pool = self._cnx_pool
        if cnx is None:
            return
        self._cnx = None
        if _DETECT_NESTED:
            _note_return(self)
        if not getattr(cnx, '_spp_broken', False):
            try:
                if cnx.unread_result:
                    cnx.consume_results()
                if cnx.in_transaction:
                    cnx.rollback()
                cnx._spp_last_used = time.monotonic()
            except Exception:
                cnx._spp_broken = True
        pool._cnx_queue.put(cnx, block=False)


class _Pool(pooling.MySQLConnectionPool):
    def _queue_connection(self, cnx):
        _guard(cnx)
        super()._queue_connection(cnx)

    def get_connection(self, wait=0.0):
        try:
            cnx = self._cnx_queue.get(block=wait > 0, timeout=wait if wait > 0 else None)
        except queue.Empty as err:
            raise pooling.PoolError("Failed getting connection; pool exhausted") from err
        try:
            idle = time.monotonic() - getattr(cnx, '_spp_last_used', 0.0)
            stale = self._config_version != cnx.pool_config_version
            broken = getattr(cnx, '_spp_broken', False) or _socket_closed(cnx)
            if stale or broken or (idle > _PING_AFTER_IDLE and not cnx.is_connected()):
                cnx.config(**self._cnx_config)
                cnx.reconnect()
                cnx.pool_config_version = self._config_version
                cnx._spp_broken = False
                cnx._spp_last_used = time.monotonic()
                if broken:
                    logger.warning("DB POOL: a dropped connection was replaced")
        except Exception:
            self._cnx_queue.put(cnx, block=False)
            raise
        return _PooledConnection(self, cnx)


def _build_pool():
    global _POOL, _RETRY_AT
    if _POOL is not None:
        return _POOL
    with _BUILD_LOCK:
        if _POOL is not None:
            return _POOL
        if time.monotonic() < _RETRY_AT:
            raise pooling.PoolError("Database is not reachable; retrying shortly")
        try:
            _POOL = _Pool(
                pool_name='user_pool',
                pool_size=_POOL_SIZE,
                pool_reset_session=False,
                host=Config.DATABASE_HOST,
                user=Config.DATABASE_USER,
                password=Config.DATABASE_PASSWORD,
                database=Config.DATABASE_NAME,
                use_pure=os.environ.get('MYSQL_USE_PURE', '1') != '0',
                connection_timeout=10,
                init_command=_ISOLATION,
            )
            logger.info(f"DB POOL: user connection pool ready (size={_POOL_SIZE})")
        except Exception as exc:
            _RETRY_AT = time.monotonic() + _RETRY_SECONDS
            logger.error(f"DB POOL: pool creation failed ({exc}); retrying in {_RETRY_SECONDS:.0f}s")
            raise pooling.PoolError(f"Database is not reachable ({exc})") from exc
    return _POOL


def get_connection():
    pool = _build_pool()
    try:
        conn = pool.get_connection(wait=_WAIT_SECONDS)
        if _DETECT_NESTED:
            _note_checkout(conn)
        return conn
    except pooling.PoolError:
        logger.error("DB POOL: no free connection after %.0fs (size=%d)", _WAIT_SECONDS, _POOL_SIZE)
        raise


def pool_stats():
    pool = _POOL
    if not pool:
        return {'size': 0, 'free': 0}
    try:
        free = pool._cnx_queue.qsize()
    except Exception:
        free = -1
    return {'size': _POOL_SIZE, 'free': free}
