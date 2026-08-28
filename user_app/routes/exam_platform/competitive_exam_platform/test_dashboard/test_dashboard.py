from flask import abort, flash, redirect, render_template, request, url_for
from routes.exam_platform.competitive_exam_platform.databases.main_handler_db import UserOperation
from routes.exam_platform.competitive_exam_platform.databases.question_handler_db import ContentOperation
from routes.exam_platform.competitive_exam_platform.utils.utils_test_dashboard import get_user_session
from routes.exam_platform.competitive_exam_platform.utils.utils_test_dashboard import prepare_mock_test_data_free, prepare_mock_test_data_paid,_process_tests_for_new_badge
from routes.exam_platform.competitive_exam_platform.utils.utils_secure_code import secure_access_required
from extensions import user_login_required
from routes import users_bp
import logging

user_op = UserOperation()
content_op = ContentOperation()

logger = logging.getLogger(__name__)

@users_bp.route('/open/mock_test/<section_id>/<course_code>/<unique_code>')
@user_login_required
@secure_access_required(('course_code', 'unique_code'))
def open_mock_test_section(section_id, course_code, unique_code):
    email, username, user_is_authenticated = get_user_session()

    if not user_is_authenticated:
        logger.warning("MOCK TEST: Unauthenticated access blocked")
        flash('Please log in to continue.', 'warning')
        return redirect(url_for('users.user_login', next=request.url))

    section_label = content_op.get_section_label(section_id)

    if not section_label:
        abort(404)

    data = {}
    dashboard_type = ''

    if section_label == 'Paid':
        data = prepare_mock_test_data_paid(course_code, email, section_id)
        dashboard_type = 'paid'

    elif section_label == 'Free':
        dashboard_type = 'free'
        data = prepare_mock_test_data_free(course_code, email, section_id)

    else:
        abort(400)

    from routes.exam_platform.subscription_access import annotate_tests, PREMIUM_ENDPOINT
    subscribed = annotate_tests(data.get('display_tests', []), email)
    annotate_tests(data.get('completed_tests_details', []), email)
    premium_url = url_for(PREMIUM_ENDPOINT)

    locked_paid = []

    logger.info(f"MOCK TEST: [{email}] opened {dashboard_type} section {section_id} in {course_code}")

    return render_template(
        'users/exam_platform/competitive_exam_platform/test_dashboard/test_dashboard.html',
        tests=data.get('display_tests', []),
        completed_tests=data.get('completed_tests_details', []),
        email=email,
        username=username,
        course_code=course_code,
        course_name=data.get('course_name', ''),
        stream=data.get('stream', ''),
        unique_code=unique_code,
        dashboard_type=dashboard_type,
        locked_paid=locked_paid,
        subscribed=subscribed,
        premium_url=premium_url,
        user_is_authenticated=user_is_authenticated,
        section_id=section_id
    )