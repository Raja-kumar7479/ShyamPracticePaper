import logging
from routes.db_pool import get_connection

logger = logging.getLogger(__name__)

STALE_SECONDS = 30


def _rows(query, params=()):
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def _release_stale(email, ignore_test_key=None):
    """Release sessions whose window is gone.

    ignore_test_key is the test the user is opening right now: never release it,
    otherwise resuming a test would destroy the very session being resumed.
    """
    conn = get_connection()
    cur = conn.cursor()
    keep = ignore_test_key or ''
    try:
        cur.execute("""
            UPDATE user_test_log
            SET status = 'unperformed', end_time = NOW(), updated_at = NOW()
            WHERE email = %s AND status = 'in_progress' AND test_key <> %s
              AND (last_heartbeat IS NULL OR last_heartbeat < NOW() - INTERVAL %s SECOND)
        """, (email, keep, STALE_SECONDS))
        n1 = cur.rowcount
        cur.execute("""
            UPDATE comm_user_log
            SET status = 'terminated', session_token = NULL, tab_id = NULL
            WHERE email = %s AND status = 'started' AND test_key <> %s
              AND (last_heartbeat IS NULL OR last_heartbeat < NOW() - INTERVAL %s SECOND)
              AND test_key NOT IN (SELECT test_key FROM cp_tests WHERE test_key IS NOT NULL)
        """, (email, keep, STALE_SECONDS))
        n2 = cur.rowcount
        conn.commit()
        if n1 or n2:
            logger.info(f"TEST LOCK: released {n1} stale mock + {n2} stale communication session(s) for {email}")
    except Exception:
        conn.rollback()
        logger.exception(f"TEST LOCK: failed releasing stale sessions for {email}")
    finally:
        cur.close()
        conn.close()


def get_active_test(email, ignore_test_key=None):
    if not email:
        return None
    _release_stale(email, ignore_test_key)

    mock = _rows("""
        SELECT utl.test_key, td.subject_title AS title, 'competitive' AS portal
        FROM user_test_log utl
        LEFT JOIN test_description td ON td.test_key = utl.test_key
        WHERE utl.email = %s AND utl.status = 'in_progress'
        ORDER BY utl.id DESC LIMIT 1
    """, (email,))
    comm = _rows("""
        SELECT cul.test_key, cd.subject_title AS title, 'communication' AS portal
        FROM comm_user_log cul
        LEFT JOIN comm_description cd ON cd.test_key = cul.test_key
        WHERE cul.email = %s AND cul.status = 'started'
          AND cul.test_key NOT IN (SELECT test_key FROM cp_tests WHERE test_key IS NOT NULL)
        ORDER BY cul.id DESC LIMIT 1
    """, (email,))
    coding = _rows("""
        SELECT t.test_key, t.title, t.slug, 'coding' AS portal
        FROM cp_attempts a
        JOIN cp_tests t ON t.id = a.test_id
        JOIN auth u ON u.id = a.user_id
        WHERE u.email = %s AND a.status = 'in_progress'
        ORDER BY a.id DESC LIMIT 1
    """, (email,))

    for row in (mock + coding + comm):
        if ignore_test_key and row.get('test_key') == ignore_test_key:
            continue
        logger.warning(f"TEST LOCK: [{email}] already has an active {row['portal']} test "
                       f"{row['test_key']!r} ({row.get('title')!r})")
        return row
    return None


def blocked_message(active=None):
    return "Already another test running. First close it, then proceed."

def _codes_for(email, course_code):
    from flask import session
    unique = None
    if course_code:
        rows = _rows("SELECT unique_code FROM enrollment WHERE email = %s AND code = %s LIMIT 1",
                     (email, course_code))
        if rows:
            unique = rows[0]['unique_code']
    course = course_code or session.get('course_code')
    unique = unique or session.get('unique_code')
    if course and unique:
        return {'course_code': course, 'unique_code': unique}
    return None


def resume_url_for(email, row):
    from flask import url_for
    key = row.get('test_key')
    if not key and not row.get('slug'):
        return None
    try:
        tcs = _rows("""
            SELECT a.tcs_exam_id, e.code, e.aptitude_test_key, ct.test_key AS coding_key
            FROM tcs_attempts a
            JOIN tcs_exams e ON e.id = a.tcs_exam_id
            LEFT JOIN cp_tests ct ON ct.id = e.coding_test_id
            WHERE a.email = %s AND a.stage <> 'completed'
        """, (email,))
    except Exception:
        tcs = []
    for t in tcs:
        if key in (t['aptitude_test_key'], t['coding_key']):
            codes = _codes_for(email, t['code'])
            if codes:
                return url_for('tcs.start', exam_id=t['tcs_exam_id'], **codes)
    if row.get('portal') == 'competitive':
        td = _rows("""
            SELECT td.test_id, cc.code FROM test_description td
            LEFT JOIN course_content cc ON cc.section_id = td.test_id
            WHERE td.test_key = %s
        """, (key,))
        if td:
            codes = _codes_for(email, td[0]['code'])
            if codes:
                return url_for('users.test_login', section_id=td[0]['test_id'], test_key=key, **codes)
        return None
    if row.get('slug'):
        return url_for('coding_test.start', slug=row['slug'])
    cp = _rows("SELECT slug FROM cp_tests WHERE test_key = %s LIMIT 1", (key,))
    if cp:
        return url_for('coding_test.start', slug=cp[0]['slug'])
    log = _rows("""
        SELECT course_code, unique_code FROM comm_user_log
        WHERE email = %s AND test_key = %s ORDER BY id DESC LIMIT 1
    """, (email, key))
    codes = None
    if log and log[0].get('course_code') and log[0].get('unique_code'):
        codes = {'course_code': log[0]['course_code'], 'unique_code': log[0]['unique_code']}
    codes = codes or _codes_for(email, None)
    if not codes:
        return None
    try:
        from routes.exam_platform.placement_exam_portal.communication_portal.databases.proctor_db import ProctorDB
        round_name = ProctorDB().get_round_for_test_key(key) or 'Communication'
    except Exception:
        round_name = 'Communication'
    return url_for('users.assessment_system_info', round_name=round_name, test_key=key, **codes)


def active_test_redirect(email, ignore_test_key=None):
    row = get_active_test(email, ignore_test_key=ignore_test_key)
    if not row:
        return None
    try:
        url = resume_url_for(email, row)
    except Exception:
        logger.exception("TEST LOCK: could not build resume url for %s", email)
        url = None
    if url:
        logger.info("TEST LOCK: [%s] redirecting to running test %s", email, row.get('test_key'))
    return url

