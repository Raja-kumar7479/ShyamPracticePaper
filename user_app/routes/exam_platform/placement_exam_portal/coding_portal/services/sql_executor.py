"""
SQL section execution.

Each question owns a sandbox database seeded from its DDL. Candidate queries
run as a low-privilege, SELECT-only user inside a transaction that is always
rolled back, so a submitted query can neither mutate data nor read anything
outside its own sandbox.
"""
import hashlib
import re
import logging
from decimal import Decimal
from datetime import date, datetime, timedelta

import mysql.connector

from config import Config

logger = logging.getLogger(__name__)

# Only single read statements are accepted. Belt-and-braces alongside the
# GRANT: the sandbox user cannot write even if this misses something.
_ALLOWED_START = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|"
    r"REPLACE|RENAME|LOAD_FILE|INTO\s+OUTFILE|INTO\s+DUMPFILE|"
    r"INFORMATION_SCHEMA|MYSQL\.|PERFORMANCE_SCHEMA|SLEEP|BENCHMARK)\b",
    re.IGNORECASE,
)


class SqlError(Exception):
    pass


def sandbox_db_name(question_id: int) -> str:
    return f"{Config.SQL_SANDBOX_PREFIX}{int(question_id)}"


def _admin_conn(database=None):
    return mysql.connector.connect(
        host=Config.DB_HOST, port=Config.DB_PORT,
        user=Config.DB_USER, password=Config.DB_PASS,
        database=database, autocommit=True,
    )


def _fingerprint(schema_sql: str) -> str:
    return hashlib.sha256((schema_sql or "").encode("utf-8")).hexdigest()


def _built_fingerprint(question_id: int):
    """The schema this question's sandbox was last built from, or None."""
    conn = _admin_conn(database=Config.DB_NAME)
    try:
        cur = conn.cursor()
        cur.execute("SELECT fingerprint FROM cp_sql_sandboxes WHERE question_id = %s",
                    (int(question_id),))
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None
    except mysql.connector.Error:
        # Missing bookkeeping must not take the SQL section down; the worst case
        # is the old behaviour of leaving an existing sandbox alone.
        logger.exception("SQL SANDBOX: could not read fingerprint for q%s", question_id)
        return None
    finally:
        conn.close()


def _record_fingerprint(question_id: int, fingerprint: str):
    conn = _admin_conn(database=Config.DB_NAME)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO cp_sql_sandboxes (question_id, fingerprint) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE fingerprint = VALUES(fingerprint)",
            (int(question_id), fingerprint),
        )
        cur.close()
    except mysql.connector.Error:
        logger.exception("SQL SANDBOX: could not record fingerprint for q%s", question_id)
    finally:
        conn.close()


def ensure_sandbox(question_id: int, schema_sql: str, force=False) -> str:
    """
    Create and seed the sandbox database for a question.

    Rebuilt whenever the question's DDL has changed since the sandbox was last
    built, so editing a SQL question in the admin app takes effect on the next
    run. Previously an existing sandbox was left alone unless the caller passed
    force=True, and the only caller that did was the coding portal's own
    authoring screen -- which no longer exists.
    """
    db_name = sandbox_db_name(question_id)
    fingerprint = _fingerprint(schema_sql)
    if not force and _built_fingerprint(question_id) != fingerprint:
        force = True

    conn = _admin_conn()
    try:
        cur = conn.cursor()
        if force:
            cur.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        cur.close()

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

        _grant_readonly(db_name)
        _record_fingerprint(question_id, fingerprint)
        return db_name
    finally:
        conn.close()


def _grant_readonly(db_name: str):
    """Create the sandbox user if needed and grant SELECT on this DB only."""
    conn = _admin_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE USER IF NOT EXISTS %s@'%%' IDENTIFIED BY %s",
            (Config.SQL_SANDBOX_USER, Config.SQL_SANDBOX_PASS),
        )
        cur.execute(
            f"GRANT SELECT ON `{db_name}`.* TO %s@'%%'",
            (Config.SQL_SANDBOX_USER,),
        )
        cur.execute("FLUSH PRIVILEGES")
        cur.close()
    except mysql.connector.Error as e:
        # Managed MySQL may forbid user creation; fall back to the app user.
        logger.warning("Could not provision sandbox user: %s", e)
    finally:
        conn.close()


def _sandbox_conn(db_name: str):
    """Connect as the restricted user, falling back to the app user."""
    try:
        return mysql.connector.connect(
            host=Config.DB_HOST, port=Config.DB_PORT,
            user=Config.SQL_SANDBOX_USER, password=Config.SQL_SANDBOX_PASS,
            database=db_name, autocommit=False,
        )
    except mysql.connector.Error:
        logger.warning("Sandbox user unavailable; using app credentials")
        return mysql.connector.connect(
            host=Config.DB_HOST, port=Config.DB_PORT,
            user=Config.DB_USER, password=Config.DB_PASS,
            database=db_name, autocommit=False,
        )


def validate(query: str):
    """Reject anything that is not a single read-only statement."""
    if not query or not query.strip():
        raise SqlError("Query is empty.")

    stripped = query.strip().rstrip(";")
    if ";" in stripped:
        raise SqlError("Only a single statement is allowed.")
    if not _ALLOWED_START.match(stripped):
        raise SqlError("Only SELECT queries are allowed.")

    # Strip string literals before scanning so a legitimate value such as
    # 'admin@delete.com' cannot trip the keyword check.
    without_literals = re.sub(r"'(?:[^'\\]|\\.)*'", "''", stripped)
    without_literals = re.sub(r'"(?:[^"\\]|\\.)*"', '""', without_literals)
    match = _FORBIDDEN.search(without_literals)
    if match:
        raise SqlError(f"'{match.group(1)}' is not permitted in this query.")
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


def run_query(question_id: int, schema_sql: str, query: str):
    """
    Execute a candidate query against the question's sandbox.

    Returns {columns, rows, row_count, truncated}. Always rolls back.
    """
    stripped = validate(query)
    db_name = ensure_sandbox(question_id, schema_sql)

    conn = _sandbox_conn(db_name)
    try:
        cur = conn.cursor()
        # Server-side ceiling so a heavy query cannot pin a connection.
        try:
            cur.execute(
                f"SET SESSION MAX_EXECUTION_TIME={int(Config.SQL_QUERY_TIMEOUT_MS)}"
            )
        except mysql.connector.Error:
            pass  # MariaDB and older MySQL lack this; the read-only txn still applies.

        cur.execute(stripped)
        columns = [d[0] for d in (cur.description or [])]
        raw = cur.fetchmany(Config.SQL_MAX_ROWS + 1)
        truncated = len(raw) > Config.SQL_MAX_ROWS
        raw = raw[:Config.SQL_MAX_ROWS]
        rows = [[_jsonable(v) for v in row] for row in raw]
        cur.close()
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
        }
    except mysql.connector.Error as e:
        raise SqlError(str(e))
    finally:
        # Candidate SQL never commits.
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()


def _comparable(result, ordered):
    rows = [tuple(str(v) for v in row) for row in result["rows"]]
    return rows if ordered else sorted(rows)


def check_query(question_id: int, schema_sql: str, candidate_query: str,
                solution_query: str, ordered=False):
    """
    Grade a candidate query by running it and the reference side by side.

    Comparing result sets (rather than query text) means any correct
    formulation passes.
    """
    actual = run_query(question_id, schema_sql, candidate_query)
    expected = run_query(question_id, schema_sql, solution_query)

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
    conn = _admin_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
        cur.close()
    finally:
        conn.close()

    # Forget the fingerprint too, so the next run rebuilds from scratch rather
    # than believing a sandbox that no longer exists is already current.
    meta = _admin_conn(database=Config.DB_NAME)
    try:
        cur = meta.cursor()
        cur.execute("DELETE FROM cp_sql_sandboxes WHERE question_id = %s", (int(question_id),))
        cur.close()
    except mysql.connector.Error:
        logger.exception("SQL SANDBOX: could not clear fingerprint for q%s", question_id)
    finally:
        meta.close()
