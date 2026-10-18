import hashlib
import re
import logging
import threading
import time
from decimal import Decimal
from datetime import date, datetime, timedelta

import mysql.connector

from config import Config

logger = logging.getLogger(__name__)

_ALLOWED_START = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|"
    r"REPLACE\s+INTO|RENAME|LOAD_FILE|INTO\s+OUTFILE|INTO\s+DUMPFILE|"
    r"INFORMATION_SCHEMA|PERFORMANCE_SCHEMA|SLEEP|BENCHMARK|"
    r"GET_LOCK|RELEASE_LOCK|RELEASE_ALL_LOCKS|IS_FREE_LOCK|IS_USED_LOCK)\b"
    r"|((?:`\s*)?\bMYSQL\b(?:\s*`)?\s*\.)",
    re.IGNORECASE,
)

BUSY_MESSAGE = "The SQL judge is busy. Please try again in a moment."
DOWN_MESSAGE = "The SQL judge is not available right now. Please try again in a moment."
BROKEN_TABLES = "The tables for this question could not be prepared. Please tell the invigilator."
BROKEN_REFERENCE = "The reference answer for this question could not be run. Please tell the invigilator."
BUILD_LOCK_WAIT = 15
EXPECTED_TTL = 60

_ready = {}
_expected = {}
_slots = threading.BoundedSemaphore(max(1, int(Config.SQL_SANDBOX_PARALLEL)))


class SqlError(Exception):
    pass


class SqlUnavailable(SqlError):
    pass


class SqlQuestionBroken(SqlUnavailable):
    pass


def sandbox_db_name(question_id: int) -> str:
    return f"{Config.SQL_SANDBOX_PREFIX}{int(question_id)}"


def _admin_conn(database=None):
    return mysql.connector.connect(
        host=Config.DB_HOST, port=Config.DB_PORT,
        user=Config.DB_USER, password=Config.DB_PASS,
        database=database, autocommit=True, connection_timeout=10, use_pure=True,
    )


def _fingerprint(schema_sql: str) -> str:
    return hashlib.sha256((schema_sql or "").encode("utf-8")).hexdigest()


def _built_fingerprint(cur, question_id: int):
    try:
        cur.execute(
            f"SELECT fingerprint FROM `{Config.DB_NAME}`.cp_sql_sandboxes WHERE question_id = %s",
            (int(question_id),))
        row = cur.fetchone()
        return row[0] if row else None
    except mysql.connector.Error:
        logger.exception("SQL SANDBOX: could not read fingerprint for q%s", question_id)
        return None


def _record_fingerprint(cur, question_id: int, fingerprint: str):
    try:
        cur.execute(
            f"INSERT INTO `{Config.DB_NAME}`.cp_sql_sandboxes (question_id, fingerprint) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE fingerprint = VALUES(fingerprint)",
            (int(question_id), fingerprint),
        )
    except mysql.connector.Error:
        logger.exception("SQL SANDBOX: could not record fingerprint for q%s", question_id)


def _seed(db_name: str, schema_sql: str):
    seeded = _admin_conn(database=db_name)
    try:
        c2 = seeded.cursor()
        c2.execute("SHOW TABLES")
        has_tables = bool(c2.fetchall())
        if not has_tables and schema_sql:
            for result in c2.execute(schema_sql, multi=True):
                if result.with_rows:
                    result.fetchall()
        c2.close()
    finally:
        seeded.close()


def _sandbox_pattern() -> str:
    prefix = Config.SQL_SANDBOX_PREFIX
    if not re.fullmatch(r"[A-Za-z0-9_]+", prefix or ""):
        raise SqlUnavailable(DOWN_MESSAGE)
    return prefix.replace("_", "\\_") + "%"


def _grant_readonly(cur):
    user = Config.SQL_SANDBOX_USER
    if not re.fullmatch(r"[A-Za-z0-9_]+", user or ""):
        logger.error("SQL SANDBOX: SQL_SANDBOX_USER must be letters, digits and underscores")
        return
    try:
        cur.execute(
            "CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s",
            (user, "%", Config.SQL_SANDBOX_PASS),
        )
        cur.execute(
            "ALTER USER %s@%s IDENTIFIED BY %s",
            (user, "%", Config.SQL_SANDBOX_PASS),
        )
        cur.execute(f"GRANT SELECT ON `{_sandbox_pattern()}`.* TO '{user}'@'%'")
    except mysql.connector.Error as e:
        logger.warning("Could not provision sandbox user: %s", e)


def _build(question_id: int, db_name: str, schema_sql: str, fingerprint: str, force: bool):
    lock_name = f"spp_sbx_{int(question_id)}"
    conn = _admin_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT GET_LOCK(%s, %s)", (lock_name, BUILD_LOCK_WAIT))
        if not (cur.fetchone() or [0])[0]:
            raise SqlUnavailable(BUSY_MESSAGE)
        try:
            if not force and _built_fingerprint(cur, question_id) != fingerprint:
                force = True
            if force:
                cur.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            try:
                _seed(db_name, schema_sql)
            except mysql.connector.Error as e:
                logger.error("SQL SANDBOX: tables for q%s could not be created: %s", question_id, e)
                raise SqlQuestionBroken(BROKEN_TABLES)
            _grant_readonly(cur)
            _record_fingerprint(cur, question_id, fingerprint)
        finally:
            cur.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))
            cur.fetchall()
        cur.close()
    finally:
        conn.close()


def ensure_sandbox(question_id: int, schema_sql: str, force=False) -> str:
    db_name = sandbox_db_name(question_id)
    fingerprint = _fingerprint(schema_sql)
    if not force and _ready.get(int(question_id)) == fingerprint:
        return db_name
    try:
        _build(question_id, db_name, schema_sql, fingerprint, force)
    except SqlError:
        raise
    except Exception as e:
        logger.error("SQL SANDBOX: could not prepare q%s: %s", question_id, e)
        raise SqlUnavailable(DOWN_MESSAGE)
    _ready[int(question_id)] = fingerprint
    return db_name


def _sandbox_conn(db_name: str):
    return mysql.connector.connect(
        host=Config.DB_HOST, port=Config.DB_PORT,
        user=Config.SQL_SANDBOX_USER, password=Config.SQL_SANDBOX_PASS,
        database=db_name, autocommit=False, connection_timeout=10, use_pure=True,
    )


def _open(question_id: int, schema_sql: str):
    db_name = ensure_sandbox(question_id, schema_sql)
    try:
        return _sandbox_conn(db_name)
    except mysql.connector.Error:
        _ready.pop(int(question_id), None)
    db_name = ensure_sandbox(question_id, schema_sql)
    try:
        return _sandbox_conn(db_name)
    except mysql.connector.Error as e:
        _ready.pop(int(question_id), None)
        logger.error("SQL SANDBOX: read-only account cannot open %s: %s", db_name, e)
        raise SqlUnavailable(DOWN_MESSAGE)


def validate(query: str):
    if not query or not query.strip():
        raise SqlError("Query is empty.")

    stripped = query.strip().rstrip(";")
    if ";" in stripped:
        raise SqlError("Only a single statement is allowed.")
    if not _ALLOWED_START.match(stripped):
        raise SqlError("Only SELECT queries are allowed.")

    without_literals = re.sub(r"'(?:[^'\\]|\\.)*'", "''", stripped)
    without_literals = re.sub(r'"(?:[^"\\]|\\.)*"', '""', without_literals)
    match = _FORBIDDEN.search(without_literals)
    if match:
        token = (match.group(1) or match.group(2) or "").strip("`. ")
        raise SqlError(f"'{token}' is not permitted in this query.")
    return stripped


def _jsonable(value):
    if isinstance(value, Decimal):
        f = float(value)
        return int(f) if f.is_integer() else f
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ")
    if isinstance(value, timedelta):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return value


def _execute(question_id: int, schema_sql: str, stripped: str):
    conn = _open(question_id, schema_sql)
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                f"SET SESSION MAX_EXECUTION_TIME={int(Config.SQL_QUERY_TIMEOUT_MS)}"
            )
        except mysql.connector.Error:
            pass

        cur.execute(stripped)
        columns = [d[0] for d in (cur.description or [])]
        raw = cur.fetchmany(Config.SQL_MAX_ROWS + 1)
        truncated = len(raw) > Config.SQL_MAX_ROWS
        raw = raw[:Config.SQL_MAX_ROWS]
        rows = [[_jsonable(v) for v in row] for row in raw]
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
        }
    except mysql.connector.Error as e:
        code = e.errno if isinstance(e.errno, int) else -1
        if code < 0 or 2000 <= code < 3000 or code in (1040, 1053, 1203, 1226):
            logger.error("SQL SANDBOX: database not reachable for q%s: %s", question_id, e)
            raise SqlUnavailable(DOWN_MESSAGE)
        raise SqlError(str(e))
    finally:
        try:
            conn.close()
        except Exception:
            pass


def run_query(question_id: int, schema_sql: str, query: str):
    stripped = validate(query)
    if not _slots.acquire(timeout=max(1, int(Config.SQL_SANDBOX_WAIT))):
        raise SqlUnavailable(BUSY_MESSAGE)
    try:
        return _execute(question_id, schema_sql, stripped)
    finally:
        _slots.release()


def _comparable(result, ordered):
    rows = [tuple(str(v) for v in row) for row in result["rows"]]
    return rows if ordered else sorted(rows)


def _expected_result(question_id: int, schema_sql: str, solution_query: str):
    key = (int(question_id), _fingerprint(schema_sql), _fingerprint(solution_query))
    hit = _expected.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < EXPECTED_TTL:
        return hit[1]
    try:
        expected = run_query(question_id, schema_sql, solution_query)
    except SqlUnavailable:
        raise
    except SqlError as e:
        logger.error("SQL SANDBOX: reference solution for q%s failed: %s", question_id, e)
        raise SqlQuestionBroken(BROKEN_REFERENCE)
    if len(_expected) > 500:
        _expected.clear()
    _expected[key] = (now, expected)
    return expected


def check_query(question_id: int, schema_sql: str, candidate_query: str,
                solution_query: str, ordered=False):
    actual = run_query(question_id, schema_sql, candidate_query)
    expected = _expected_result(question_id, schema_sql, solution_query)

    col_match = ([c.lower() for c in actual["columns"]] ==
                 [c.lower() for c in expected["columns"]])
    rows_match = _comparable(actual, ordered) == _comparable(expected, ordered)

    if not col_match:
        reason = (f"Expected {len(expected['columns'])} column(s) "
                  f"{expected['columns']}, got {actual['columns']}.")
    elif not rows_match:
        reason = (f"Result rows differ. Expected {expected['row_count']} row(s), "
                  f"got {actual['row_count']}.")
    else:
        reason = ""

    return {
        "correct": bool(col_match and rows_match),
        "reason": reason,
        "result": actual,
        "expected_row_count": expected["row_count"],
    }


def drop_sandbox(question_id: int):
    db_name = sandbox_db_name(question_id)
    _ready.pop(int(question_id), None)
    conn = _admin_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
        try:
            cur.execute(
                f"DELETE FROM `{Config.DB_NAME}`.cp_sql_sandboxes WHERE question_id = %s",
                (int(question_id),))
        except mysql.connector.Error:
            logger.exception("SQL SANDBOX: could not clear fingerprint for q%s", question_id)
        cur.close()
    finally:
        conn.close()
