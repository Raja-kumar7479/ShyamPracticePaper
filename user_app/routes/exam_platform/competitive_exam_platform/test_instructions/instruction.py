import logging
from flask import flash, redirect, render_template, session, url_for
from routes.exam_platform.competitive_exam_platform.databases.main_handler_db import UserOperation
from routes.exam_platform.competitive_exam_platform.utils.utils_test_dashboard  import get_user_session, redirect_if_test_not_found, format_section_count
from routes.exam_platform.competitive_exam_platform.utils.utils_secure_code import secure_access_required
from extensions import user_login_required
from routes import users_bp

logger = logging.getLogger(__name__)
user_op = UserOperation()


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

    return render_template('users/exam_platform/competitive_exam_platform/test_instructions/instruction.html',
                           section_id=section_id, test_key=test_key, course_code=course_code, unique_code=unique_code,
                           username=username, email=email, total_duration_minutes=test['total_duration_minutes'])

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
    return render_template('users/exam_platform/competitive_exam_platform/test_instructions/paper_instruction.html',
                           section_id=section_id, test_key=test_key, course_code=course_code, unique_code=unique_code,
                           username=username, email=email, total_questions=test['total_questions'],
                           total_marks=test['total_marks'], num_sections_text=format_section_count(sections),
                           sections=sections)