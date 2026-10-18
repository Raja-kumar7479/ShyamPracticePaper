import logging
import os
import threading
import mysql.connector
from mysql.connector import pooling
from config import Config

logger = logging.getLogger(__name__)

_pool = None
_pool_lock = threading.Lock()
_pool_failed = False
_POOL_SIZE = int(os.environ.get('DB_POOL_SIZE', '10'))


def _build_pool():
    return pooling.MySQLConnectionPool(
        pool_name='admin_pool',
        pool_size=_POOL_SIZE,
        pool_reset_session=True,
        host=Config.DATABASE_HOST,
        user=Config.DATABASE_USER,
        password=Config.DATABASE_PASSWORD,
        database=Config.DATABASE_NAME,
        charset='utf8mb4',
    )


def _use_read_committed(conn):
    try:
        cur = conn.cursor()
        try:
            cur.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
        finally:
            cur.close()
    except mysql.connector.Error as e:
        logger.warning(f"DB POOL: could not set READ COMMITTED ({e})")
    return conn


def get_connection():
    global _pool, _pool_failed

    if not _pool_failed and _pool is None:
        with _pool_lock:
            if _pool is None and not _pool_failed:
                try:
                    _pool = _build_pool()
                    logger.info(f"DB POOL: admin connection pool ready (size={_POOL_SIZE})")
                except mysql.connector.Error as e:
                    _pool_failed = True
                    logger.warning(f"DB POOL: pool creation failed ({e}); falling back to direct connections")

    if _pool is not None:
        try:
            return _use_read_committed(_pool.get_connection())
        except mysql.connector.Error as e:
            logger.warning(f"DB POOL: checkout failed ({e}); using direct connection for this request")

    return _use_read_committed(mysql.connector.connect(
        host=Config.DATABASE_HOST,
        user=Config.DATABASE_USER,
        password=Config.DATABASE_PASSWORD,
        database=Config.DATABASE_NAME,
        charset='utf8mb4',
    ))
