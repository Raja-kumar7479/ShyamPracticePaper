"""Keeps the round assessment list in step with coding attempts.

The round page (`users.round_assessments`) reads every assessment's status from
`comm_user_log`, because that is where the communication portal records it. The
coding portal kept its own state in `cp_attempts` and never wrote
`comm_user_log`, so a finished coding test still advertised "Start Assessment"
on the round page and could be entered again.

Writing the same row the round page already reads fixes both at once: the card
flips to Completed, and the existing completed-test guards start applying to
coding as well.
"""
import logging

from flask import session

from .db import execute, query_one

logger = logging.getLogger(__name__)


def _test_identity(test_db_id):
    """The course-facing keys for a coding test, or None when it has no link."""
    row = query_one(
        "SELECT test_key, code FROM cp_tests WHERE id = %s",
        (test_db_id,),
    )
    if not row or not row.get("test_key"):
        logger.warning("ROUND SYNC: cp_tests id=%s has no test_key; skipping", test_db_id)
        return None
    return row


def sync_round_status(test_db_id, email, status):
    """Upsert this student's row for a coding test in `comm_user_log`.

    `comm_user_log` has a UNIQUE key on (email, test_key), so the insert
    collapses into an update for a student who is sitting the test again.
    A row that already reached a closed state (completed or terminated) is
    never downgraded back to started, because that would advertise a finished
    assessment as startable again on the round page.
    """
    if not email or not test_db_id:
        return
    identity = _test_identity(test_db_id)
    if not identity:
        return

    course_code = identity.get("code") or session.get("coding_course_code")
    unique_code = session.get("coding_unique_code")
    end_time_sql = "NOW()" if status == "completed" else "NULL"

    try:
        execute(
            f"""
            INSERT INTO comm_user_log (email, test_key, course_code, unique_code, status, end_time)
            VALUES (%s, %s, %s, %s, %s, {end_time_sql})
            ON DUPLICATE KEY UPDATE
                status = IF(comm_user_log.status IN ('completed', 'terminated'),
                            comm_user_log.status, VALUES(status)),
                course_code = COALESCE(VALUES(course_code), comm_user_log.course_code),
                unique_code = COALESCE(VALUES(unique_code), comm_user_log.unique_code),
                end_time = IF(VALUES(status) = 'completed', NOW(), comm_user_log.end_time)
            """,
            (email, identity["test_key"], course_code, unique_code, status),
        )
        logger.info("ROUND SYNC: [%s] coding test_key=%s -> %s",
                    email, identity["test_key"], status)
    except Exception:
        # Never let bookkeeping break the exam the student is sitting.
        logger.exception("ROUND SYNC FAILED: [%s] test id=%s status=%s",
                         email, test_db_id, status)


def completed_test_keys(email, test_keys):
    """Which of these coding test_keys the student has already submitted."""
    if not email or not test_keys:
        return set()
    placeholders = ",".join(["%s"] * len(test_keys))
    from .db import query_all
    rows = query_all(
        f"SELECT test_key FROM comm_user_log "
        f"WHERE email = %s AND status = 'completed' AND test_key IN ({placeholders})",
        (email, *test_keys),
    )
    return {r["test_key"] for r in rows}
