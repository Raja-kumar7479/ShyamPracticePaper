import logging
from flask import flash, redirect, render_template, session, url_for
from routes.exam_platform.competitive_exam_platform.databases.main_handler_db import UserOperation
from routes.exam_platform.competitive_exam_platform.utils.utils_test_dashboard  import get_user_session, redirect_if_test_not_found
from routes.exam_platform.competitive_exam_platform.utils.utils_secure_code import secure_access_required
from extensions import user_login_required
from routes import users_bp

logger = logging.getLogger(__name__)
user_op = UserOperation()


def _coding_part(test_key):
    try:
        from routes.exam_platform.placement_exam_portal.tcs_portal import models as tcs_models
        from routes.exam_platform.placement_exam_portal.coding_portal import models as cp_models
        exam = tcs_models.exam_for_aptitude_key(test_key)
        if not exam or not exam.get('coding_test_id'):
            return None
        rows = [r for r in cp_models.get_section_totals(exam['coding_test_id']) if int(r.get('question_count') or 0) > 0]
        if not rows:
            return None
        return {
            'label': exam.get('coding_label') or 'Coding',
            'minutes': int(exam.get('coding_minutes') or 0),
            'questions': sum(int(r['question_count'] or 0) for r in rows),
            'marks': sum(int(r['marks'] or 0) for r in rows),
            'parts': [{'title': r['title'], 'questions': int(r['question_count'] or 0), 'marks': int(r['marks'] or 0)} for r in rows],
        }
    except Exception:
        logger.exception(f"INSTRUCTIONS: could not read the coding part behind {test_key}")
        return None


def _blocked_after_termination(email, test_key, section_id, course_code, unique_code):
    if session.get(f"terminated:{email}:{test_key}"):
        logger.warning(f"INSTRUCTION BLOCKED: [{email}] returned to instructions after termination of {test_key}")
        flash('Your previous attempt was terminated. Start the test again from your dashboard.', 'test_error')
        return redirect(url_for('users.open_mock_test_section', section_id=section_id,
                                course_code=course_code, unique_code=unique_code))

    status = (user_op.get_test_status_for_user(email, test_key) or {}).get('status')
    if status not in ('in_progress', 'unperformed'):
        logger.warning(f"INSTRUCTION BLOCKED: [{email}] status={status!r} for {test_key}; sending to dashboard")
        flash('This test session is no longer active. Please start it again from your dashboard.', 'test_error')
        return redirect(url_for('users.open_mock_test_section', section_id=section_id,
                                course_code=course_code, unique_code=unique_code))
    return None

@users_bp.route('/test-instruction/<section_id>/<test_key>/<course_code>/<unique_code>', methods=['GET'])
@secure_access_required(('course_code', 'unique_code'))
def test_instruction(section_id, test_key, course_code, unique_code):
    email, username, user_is_authenticated = get_user_session()

    blocked = _blocked_after_termination(email, test_key, section_id, course_code, unique_code)
    if blocked:
        return blocked

    test = user_op.get_test_details(test_key)

    if not test:
        return redirect_if_test_not_found(test, 'purchase_dashboard', course_code=course_code, unique_code=unique_code)

    coding = _coding_part(test_key)
    return render_template('users/exam_platform/competitive_exam_platform/test_instructions/instruction.html',
                           section_id=section_id, test_key=test_key, course_code=course_code, unique_code=unique_code,
                           username=username, email=email,
                           total_duration_minutes=(test['total_duration_minutes'] or 0) + (coding['minutes'] if coding else 0))

@users_bp.route('/paper-instruction/<section_id>/<test_key>/<course_code>/<unique_code>', methods=['GET'])
@secure_access_required(('course_code', 'unique_code'))
def paper_instruction(section_id, test_key, course_code, unique_code):
    email, username, user_is_authenticated = get_user_session()

    blocked = _blocked_after_termination(email, test_key, section_id, course_code, unique_code)
    if blocked:
        return blocked

    test = user_op.get_test_details(test_key)

    if not test:
        return redirect_if_test_not_found(test, 'purchase_dashboard', course_code=course_code, unique_code=unique_code)

    sections = user_op.get_test_sections(test_key)
    coding = _coding_part(test_key)
    section_count = len(sections) + (1 if coding else 0)
    return render_template('users/exam_platform/competitive_exam_platform/test_instructions/paper_instruction.html',
                           section_id=section_id, test_key=test_key, course_code=course_code, unique_code=unique_code,
                           username=username, email=email,
                           total_questions=(test['total_questions'] or 0) + (coding['questions'] if coding else 0),
                           total_marks=(test['total_marks'] or 0) + (coding['marks'] if coding else 0),
                           num_sections_text=f"{section_count} section{'s' if section_count != 1 else ''}",
                           section_count=section_count, coding=coding,
                           total_duration_minutes=(test['total_duration_minutes'] or 0) + (coding['minutes'] if coding else 0),
                           sections=sections)