import logging
import os
import threading
import mysql.connector
from mysql.connector import Error, pooling
from config import Config

logger = logging.getLogger(__name__)

_pool = None
_pool_lock = threading.Lock()


def _pool_size():
    try:
        size = int(os.environ.get("DB_POOL_SIZE", "16"))
    except ValueError:
        size = 16
    return max(1, min(size, 32))


def _init_pool():
    global _pool
    try:
        _pool = pooling.MySQLConnectionPool(
            pool_name="app_pool",
            pool_size=_pool_size(),
            pool_reset_session=True,
            host=Config.DATABASE_HOST,
            user=Config.DATABASE_USER,
            password=Config.DATABASE_PASSWORD,
            database=Config.DATABASE_NAME,
        )
        logger.info("MySQL connection pool ready (size=%s).", _pool.pool_size)
    except Error as e:
        logger.error("Could not create MySQL pool (%s); using direct connections.", e)
        _pool = None


def _direct_connection():
    return mysql.connector.connect(
        host=Config.DATABASE_HOST,
        user=Config.DATABASE_USER,
        password=Config.DATABASE_PASSWORD,
        database=Config.DATABASE_NAME,
    )


def get_connection():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _init_pool()
    if _pool is not None:
        try:
            return _pool.get_connection()
        except Error as e:
            logger.warning("Pool busy (%s); serving a direct connection.", e)
    return _direct_connection()
