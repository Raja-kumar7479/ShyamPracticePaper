from flask import flash, redirect, request, session, url_for
from routes.exam_platform.competitive_exam_platform.databases.main_handler_db import UserOperation
from routes.exam_platform.competitive_exam_platform.utils.utils_test_dashboard import get_user_session
from routes.exam_platform.competitive_exam_platform.utils.utils_secure_code import secure_access_required
from routes import users_bp

user_op = UserOperation()

@users_bp.route('/process-readiness/<section_id>/<test_key>/<course_code>/<unique_code>', methods=['POST'])
@secure_access_required(('course_code', 'unique_code'))
def process_readiness(section_id, test_key, course_code, unique_code):
    email, username, user_is_authenticated = get_user_session()
    is_checkbox_checked = request.form.get('readiness_checkbox') == 'on'
    if not is_checkbox_checked:
        flash('You must acknowledge the instructions before proceeding.', 'test_error')
        return redirect(url_for('users.paper_instruction', section_id=section_id, test_key=test_key, course_code=course_code, unique_code=unique_code))

    user_op.store_user_test_start(email, test_key, username, is_checkbox_checked=True, ready_to_begin=True)
    flash('You are now ready to begin the test.', 'test_success')
    return redirect(url_for('users.start_test', section_id=section_id, test_key=test_key, course_code=course_code, unique_code=unique_code))