import logging
import time
from datetime import datetime, timedelta

from flask import redirect, url_for

from routes.db_pool import get_connection

logger = logging.getLogger(__name__)

_VERSION_CACHE = {}
_VERSION_TTL_SECONDS = 10


def content_unavailable(course_code, unique_code, section_id=None, email=None, reason='removed'):
    logger.info("CONTENT GONE: [%s] %s content %s in %s - returned to the dashboard",
                email or 'anonymous', reason, section_id, course_code)
    return redirect(url_for('users.view_course_dashboard',
                            course_code=course_code, unique_code=unique_code))


def content_version(course_code, _now=None):
    now = _now if _now is not None else time.time()
    cached = _VERSION_CACHE.get(course_code)
    if cached and cached[1] > now:
        return cached[0]

    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*), COALESCE(MAX(updated_at), 0) FROM course_content "
            "WHERE code = %s AND status = 'active'",
            (course_code,),
        )
        count, newest = cursor.fetchone()
        version = f"{count}-{newest}"
    except Exception as e:
        logger.warning("CONTENT VERSION: could not read the fingerprint for %s: %s", course_code, e)
        version = ''
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    if version:
        _VERSION_CACHE[course_code] = (version, now + _VERSION_TTL_SECONDS)
    return version


NEW_CONTENT_DAYS = 3


def mark_new_content(rows, days=NEW_CONTENT_DAYS):
    cutoff = datetime.now() - timedelta(days=days)
    for row in rows or []:
        added = row.get('created_at')
        row['is_newly_added'] = bool(added and added > cutoff)
    return rows
