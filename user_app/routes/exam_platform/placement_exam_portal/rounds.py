import logging
import mysql.connector
from flask import render_template, session
from config import Config
from routes.exam_platform.placement_exam_portal.communication_portal.utils.utils_token import get_user_session, comm_login_required
from routes.exam_platform.placement_exam_portal.communication_portal.utils.utils_secure_code import secure_access_required
from routes import users_bp

logger = logging.getLogger(__name__)

AVAILABLE_ROUND_PORTALS = {'Communication'}

ROUND_SECTIONS = {
    'Communication': 'communication_test',
    'Aptitude': 'aptitude_test',
    'Coding': 'coding_test',
}


def section_for_round(round_name):
    return ROUND_SECTIONS.get((round_name or '').strip().title(), '')


def classify_round(title):
    t = (title or '').lower()
    if 'communication' in t or 'verbal' in t:
        return 'Communication'
    if 'aptitude' in t or 'logical' in t or 'reasoning' in t or 'quant' in t:
        return 'Aptitude'
    if 'coding' in t or 'technical' in t or 'programming' in t:
        return 'Coding'
    return None


class RoundsDB:
    def get_conn(self):
        try:
            from routes.db_pool import get_connection
            return get_connection()
        except mysql.connector.Error as err:
            logger.critical(f"ROUNDS DB: connection failed: {err}")
            raise Exception("Database Connection Failed")

    def get_assessments_by_round(self, course_code, round_name, email):
        conn = self.get_conn(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT section_id, title FROM course_content
                WHERE code = %s AND section = %s AND status = 'active'
            """, (course_code, section_for_round(round_name)))
            section_ids = [r['section_id'] for r in cursor.fetchall()]

            if not section_ids:
                return []

            placeholders = ','.join(['%s'] * len(section_ids))
            cursor.execute(f"""
                SELECT cd.test_key, cd.subject_title AS assessment_title, cd.test_id,
                       cd.total_duration_minutes AS duration_minutes, cd.total_questions,
                       cd.total_marks, COALESCE(cd.requires_seb, 0) AS requires_seb,
                       COALESCE(cd.difficulty_level, 'Medium') AS difficulty_level,
                       COALESCE(cd.access_label, 'inherit') AS access_label,
                       COALESCE(u.status, 'not_started') AS user_test_status,
                       cd.subject_subtitle AS assessment_subtitle
                FROM comm_description cd
                LEFT JOIN comm_user_log u ON u.test_key = cd.test_key AND u.email = %s
                WHERE cd.test_id IN ({placeholders})
                ORDER BY cd.subject_title
            """, (email, *section_ids))
            tests = cursor.fetchall()
            logger.info(f"ROUNDS DB: {len(tests)} assessment(s) for course {course_code!r}, round {round_name!r}")
            return tests
        finally:
            cursor.close(); conn.close()

    def get_locked_paid_rounds(self, course_code, round_name, email):
        conn = self.get_conn(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT cc.section_id, cc.title, cc.subtitle, cc.price, cc.discount,
                       (SELECT COUNT(*) FROM comm_description cd
                         WHERE cd.test_id = cc.section_id) AS test_count
                FROM course_content cc
                WHERE cc.code = %s
                  AND cc.section = %s
                  AND cc.label = 'Paid'
                  AND cc.status = 'active'
                  AND NOT EXISTS (
                        SELECT 1 FROM purchase p
                         WHERE p.email = %s
                           AND p.status = 'Paid'
                           AND (p.section_id = cc.section_id
                                OR (p.course_code = cc.code AND p.title = cc.title))
                  )
                ORDER BY cc.created_at DESC
            """, (course_code, section_for_round(round_name), email))
            rows = cursor.fetchall()
            logger.info(f"ROUNDS DB: {len(rows)} locked paid section(s) for {course_code!r}, round {round_name!r}")
            return rows
        except mysql.connector.Error:
            logger.exception(f"ROUNDS DB: failed fetching locked paid sections for {course_code!r}")
            return []
        finally:
            cursor.close(); conn.close()


db_ops = RoundsDB()


@users_bp.route('/<round_name>/assessments/<course_code>/<unique_code>')
@comm_login_required
@secure_access_required(('course_code', 'unique_code'))
def round_assessments(round_name, course_code, unique_code):
    session['course_code'] = course_code
    session['unique_code'] = unique_code
    email, username, _ = get_user_session()
    tests = db_ops.get_assessments_by_round(course_code, round_name, email)
    from routes.exam_platform.subscription_access import annotate_tests, premium_url as _premium_url
    subscribed = annotate_tests(tests, email, course_code=course_code, unique_code=unique_code)
    premium_url = _premium_url(course_code, unique_code)
    locked_paid = db_ops.get_locked_paid_rounds(course_code, round_name, email)
    logger.info(f"ROUNDS: [{email}] opened {round_name!r} assessments for {course_code!r} "
                f"({len(tests)} test(s), {len(locked_paid)} locked)")
    from flask import url_for
    items, completed = [], []
    for t in tests:
        status = t.get('user_test_status') or 'not_started'
        if status == 'completed':
            completed.append({
                'title': t.get('assessment_title'), 'subtitle': t.get('assessment_subtitle'), 'submitted_at': None,
                'score': None, 'percentage': None, 'result_label': 'View Result',
                'result_url': url_for('users.get_test_result', test_key=t['test_key'], round_name=round_name,
                                      course_code=course_code, unique_code=unique_code)})
            continue
        items.append({
            'title': t.get('assessment_title'), 'subtitle': t.get('assessment_subtitle'),
            'status': 'unperformed' if status in ('started', 'pending', 'terminated') else 'pending',
            'access': 'premium' if (t.get('access_label') == 'paid' or t.get('is_locked')) else 'free',
            'locked': bool(t.get('is_locked')), 'unlock_url': t.get('premium_url') or premium_url,
            'unlock_label': 'Unlock Premium', 'is_new': False,
            'tags': [t.get('difficulty_level')] if t.get('difficulty_level') else [],
            'meta': [{'icon': 'far fa-question-circle', 'text': f"{t.get('total_questions')} Qs"},
                     {'icon': 'far fa-check-square', 'text': f"{t.get('total_marks')} Marks"},
                     {'icon': 'far fa-clock', 'text': f"{t.get('duration_minutes')} Min"}],
            'action_url': url_for('users.assessment_system_info', test_key=t['test_key'], round_name=round_name,
                                  course_code=course_code, unique_code=unique_code),
            'action_label': 'Start Test', 'resume_label': 'Resume Test', 'launch': 'same',
        })
    return render_template('users/exam_platform/test_list.html',
                           portal_label=f'{round_name} Tests', portal_icon='fa-comments',
                           intro='Speaking, listening and writing rounds. Each test opens in a proctored full-screen window.',
                           tests=items, completed=completed, paid_blocks=locked_paid,
                           round_name=round_name, course_code=course_code, unique_code=unique_code,
                           username=username, email=email, dashboard_type='free',
                           subscribed=subscribed, premium_url=premium_url,
                           back_url=url_for('users.view_course_dashboard', course_code=course_code, unique_code=unique_code),
                           shop_url=url_for('users.course_shop', course_code=course_code, unique_code=unique_code))


@users_bp.route('/<round_name>/coming_soon/<course_code>/<unique_code>')
@secure_access_required(('course_code', 'unique_code'))
def round_coming_soon(round_name, course_code, unique_code):
    return render_template('users/exam_platform/placement_exam_portal/round_coming_soon.html',
                           round_name=round_name, course_code=course_code, unique_code=unique_code)
