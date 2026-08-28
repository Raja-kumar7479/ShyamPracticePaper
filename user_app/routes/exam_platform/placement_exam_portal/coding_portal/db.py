"""Database helpers for the coding portal.

The standalone compiler owned its own MySQL pool and database. Inside this
app there is already one pool and one database, so this module keeps the same
helper API the ported blueprints use (query_all / query_one / execute /
executemany / get_cursor) but serves every call from the app's shared pool.
"""
import logging
import os
from contextlib import contextmanager

from routes.db_pool import get_connection

logger = logging.getLogger(__name__)

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


@contextmanager
def get_cursor(dictionary=True, commit=False):
    conn = get_connection()
    cur = conn.cursor(dictionary=dictionary)
    try:
        yield cur
        if commit:
            conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        cur.close()
        conn.close()


def query_all(sql, params=None):
    with get_cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def query_one(sql, params=None):
    with get_cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchone()


def execute(sql, params=None):
    """Runs a write and returns lastrowid (inserts) or rowcount (updates)."""
    with get_cursor(commit=True) as cur:
        cur.execute(sql, params or ())
        return cur.lastrowid or cur.rowcount


def executemany(sql, seq):
    with get_cursor(commit=True) as cur:
        cur.executemany(sql, seq)
        return cur.rowcount


def warm_pool():
    """No-op: the shared application pool is warmed at startup."""
    return True


def init_db():
    """Applies the coding-portal schema onto the existing database.

    Every statement is CREATE TABLE IF NOT EXISTS, so this is idempotent and
    never touches the app's other tables.
    """
    if not os.path.exists(SCHEMA_PATH):
        logger.warning("CODING DB: schema.sql not found at %s", SCHEMA_PATH)
        return False

    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        sql_text = fh.read()

    # Strip comment lines BEFORE splitting: a ';' inside a comment would
    # otherwise cut a CREATE TABLE in half and the statement would fail.
    cleaned = "\n".join(line for line in sql_text.splitlines()
                        if not line.strip().startswith("--"))
    statements = [s.strip() for s in cleaned.split(";") if s.strip()]
    applied = 0
    conn = get_connection()
    cur = conn.cursor()
    try:
        for stmt in statements:
            low = stmt.lower()
            # The portal must never create or switch databases inside this app.
            if low.startswith(("create database", "use ", "drop database")):
                continue
            try:
                cur.execute(stmt)
                applied += 1
            except Exception as e:
                logger.warning("CODING DB: statement skipped (%s)", str(e)[:120])
        conn.commit()
    finally:
        cur.close()
        conn.close()
    logger.info("CODING DB: schema applied (%d statement(s))", applied)
    return True
