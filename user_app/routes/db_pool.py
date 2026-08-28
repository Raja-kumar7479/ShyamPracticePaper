import logging
import os
import mysql.connector
from mysql.connector import pooling
from config import Config

logger = logging.getLogger(__name__)

_POOL = None
_POOL_SIZE = int(os.environ.get('DB_POOL_SIZE', '10'))


def _build_pool():
    global _POOL
    if _POOL is None:
        try:
            _POOL = pooling.MySQLConnectionPool(
                pool_name='user_pool',
                pool_size=_POOL_SIZE,
                pool_reset_session=True,
                host=Config.DATABASE_HOST,
                user=Config.DATABASE_USER,
                password=Config.DATABASE_PASSWORD,
                database=Config.DATABASE_NAME,
                # Pure Python by default: under eventlet the C extension's
                # socket never yields, so a single worker would serialise every
                # request behind each query, and the extension is not installed
                # at all in most environments -- asking for it there kills the
                # pool outright and silently drops us to direct connections.
                # Set MYSQL_USE_PURE=0 only where the C extension is present.
                use_pure=os.environ.get('MYSQL_USE_PURE', '1') != '0',
            )
            logger.info(f"DB POOL: user connection pool ready (size={_POOL_SIZE})")
        except Exception as exc:
            logger.error(f"DB POOL: pool creation failed ({exc}); falling back to direct connections")
            _POOL = False
    return _POOL


def _use_read_committed(conn):
    """MySQL defaults to REPEATABLE READ, which pins the first SELECT's snapshot
    for the life of the transaction. On a pooled connection that means a page
    can keep serving data that another session already changed, so a refresh
    shows nothing new until the connection happens to be recycled.

    READ COMMITTED makes every statement see the latest committed rows while
    still keeping explicit multi-statement transactions atomic.
    """
    try:
        cur = conn.cursor()
        try:
            cur.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
        finally:
            cur.close()
    except Exception as exc:
        logger.warning(f"DB POOL: could not set READ COMMITTED ({exc})")
    return conn


def get_connection():
    pool = _build_pool()
    if pool:
        try:
            return _use_read_committed(pool.get_connection())
        except Exception as exc:
            logger.warning(f"DB POOL: exhausted or unavailable ({exc}); using direct connection")
    return _use_read_committed(mysql.connector.connect(
        host=Config.DATABASE_HOST,
        user=Config.DATABASE_USER,
        password=Config.DATABASE_PASSWORD,
        database=Config.DATABASE_NAME
    ))
