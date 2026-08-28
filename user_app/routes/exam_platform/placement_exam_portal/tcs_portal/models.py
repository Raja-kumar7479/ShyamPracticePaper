import logging
from contextlib import contextmanager

from routes.db_pool import get_connection

logger = logging.getLogger(__name__)


@contextmanager
def _cursor(dictionary=True):
    conn = get_connection()
    cur = None
    try:
        cur = conn.cursor(dictionary=dictionary)
        yield conn, cur
    finally:
        if cur:
            try: cur.close()
            except Exception: pass
        try: conn.close()
        except Exception: pass


def _all(sql, params=()):
    with _cursor() as (conn, cur):
        cur.execute(sql, params)
        return cur.fetchall()


def _one(sql, params=()):
    with _cursor() as (conn, cur):
        cur.execute(sql, params)
        return cur.fetchone()


def _write(sql, params=()):
    with _cursor(dictionary=False) as (conn, cur):
        cur.execute(sql, params)
        conn.commit()
        return cur.rowcount


EXAM_SELECT = """
    SELECT e.*, cc.title AS block_title, cc.label AS block_label,
           td.subject_title AS aptitude_title, td.total_duration_minutes AS aptitude_minutes,
           td.total_questions AS aptitude_questions, td.total_marks AS aptitude_marks,
           td.test_id AS aptitude_section_id,
           ct.title AS coding_title, ct.slug AS coding_slug,
           ct.total_duration_min AS coding_minutes, ct.is_published AS coding_published
    FROM tcs_exams e
    LEFT JOIN course_content cc ON cc.section_id = e.section_id
    LEFT JOIN test_description td ON td.test_key = e.aptitude_test_key
    LEFT JOIN cp_tests ct ON ct.id = e.coding_test_id
"""


def list_exams(section_id, code):
    return _all(EXAM_SELECT + """
        WHERE e.section_id = %s AND e.code = %s AND e.is_published = 1
        ORDER BY e.created_at DESC
    """, (section_id, code))


def get_exam(exam_id):
    return _one(EXAM_SELECT + " WHERE e.id = %s", (exam_id,))


def get_attempt(exam_id, email):
    return _one("SELECT * FROM tcs_attempts WHERE tcs_exam_id = %s AND email = %s",
                (exam_id, email))


def attempts_for(email, exam_ids):
    if not exam_ids:
        return {}
    marks = ",".join(["%s"] * len(exam_ids))
    rows = _all(f"SELECT * FROM tcs_attempts WHERE email = %s AND tcs_exam_id IN ({marks})",
                (email, *exam_ids))
    return {r["tcs_exam_id"]: r for r in rows}


def start_attempt(exam_id, email):
    _write("""
        INSERT INTO tcs_attempts (tcs_exam_id, email)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE tcs_exam_id = tcs_exam_id
    """, (exam_id, email))
    return get_attempt(exam_id, email)


def mark_aptitude_done(exam_id, email, attempt_number):
    return _write("""
        UPDATE tcs_attempts
           SET stage = 'coding', aptitude_attempt_number = %s, aptitude_done_at = NOW()
         WHERE tcs_exam_id = %s AND email = %s AND stage = 'aptitude'
    """, (attempt_number, exam_id, email))


def mark_completed(exam_id, email, coding_attempt_id):
    return _write("""
        UPDATE tcs_attempts
           SET stage = 'completed', coding_attempt_id = %s, completed_at = NOW()
         WHERE tcs_exam_id = %s AND email = %s AND stage <> 'completed'
    """, (coding_attempt_id, exam_id, email))


def block_purchased(email, section_id):
    row = _one("""
        SELECT 1 FROM purchase p
        JOIN course_content cc ON cc.section_id = %s
        WHERE p.email = %s AND p.status = 'Paid'
          AND (p.section_id = cc.section_id OR (p.course_code = cc.code AND p.title = cc.title))
        LIMIT 1
    """, (section_id, email))
    return row is not None


def latest_aptitude_attempt_number(email, test_key):
    row = _one("""
        SELECT MAX(attempt_number) AS n FROM test_result WHERE email = %s AND test_key = %s
    """, (email, test_key))
    return (row or {}).get("n")


def coding_attempt_for(test_id, user_id):
    return _one("SELECT * FROM cp_attempts WHERE test_id = %s AND user_id = %s",
                (test_id, user_id))
