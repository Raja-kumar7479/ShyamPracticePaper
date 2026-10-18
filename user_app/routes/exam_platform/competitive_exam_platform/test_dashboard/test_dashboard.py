from flask import abort, flash, redirect, render_template, request, url_for
from routes.exam_platform.competitive_exam_platform.databases.main_handler_db import UserOperation
from routes.exam_platform.competitive_exam_platform.databases.question_handler_db import ContentOperation
from routes.exam_platform.competitive_exam_platform.utils.utils_test_dashboard import get_user_session
from routes.exam_platform.competitive_exam_platform.utils.utils_test_dashboard import prepare_mock_test_data_free, prepare_mock_test_data_paid,_process_tests_for_new_badge
from routes.exam_platform.competitive_exam_platform.utils.utils_secure_code import secure_access_required
from extensions import user_login_required
from routes import users_bp
from routes.content_guard import content_unavailable
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
        return content_unavailable(course_code, unique_code, section_id, email)

    section_kind = content_op.fetch_one("SELECT section FROM course_content WHERE section_id = %s", (section_id,))
    if section_kind and section_kind.get('section') == 'tcs_test':
        return redirect(url_for('tcs.dashboard', course_code=course_code, unique_code=unique_code, section_id=section_id))

    data = {}
    dashboard_type = ''

    if section_label == 'Paid':
        if not content_op.is_section_purchased(email, section_id):
            logger.warning(f"MOCK TEST BLOCKED: [{email}] paid section {section_id} in {course_code} not purchased")
            flash('This is a paid section. Purchase it to open its tests.', 'warning')
            return redirect(url_for('users.course_shop', course_code=course_code, unique_code=unique_code))
        data = prepare_mock_test_data_paid(course_code, email, section_id)
        dashboard_type = 'paid'

    elif section_label == 'Free':
        dashboard_type = 'free'
        data = prepare_mock_test_data_free(course_code, email, section_id)

    else:
        abort(400)

    from routes.exam_platform.subscription_access import annotate_tests, premium_url as _premium_url
    if section_label == 'Paid':
        for t in data.get('display_tests', []) + data.get('completed_tests_details', []):
            t['is_locked'] = False
        subscribed = True
    else:
        subscribed = annotate_tests(data.get('display_tests', []), email,
                                    course_code=course_code, unique_code=unique_code,
                                    section_id=section_id)
        annotate_tests(data.get('completed_tests_details', []), email,
                       course_code=course_code, unique_code=unique_code, section_id=section_id)
    premium_url = _premium_url(course_code, unique_code, section_id)

    locked_paid = []

    logger.info(f"MOCK TEST: [{email}] opened {dashboard_type} section {section_id} in {course_code}")

    def access_of(t):
        if section_label == 'Paid':
            return 'paid'
        return 'premium' if (t.get('access_label') == 'paid' or t.get('is_locked')) else 'free'

    tests = []
    for t in data.get('display_tests', []):
        tests.append({
            'title': t.get('subject_title'), 'subtitle': t.get('subject_subtitle'),
            'status': 'unperformed' if t.get('user_test_status') == 'unperformed' else 'pending',
            'access': access_of(t), 'locked': bool(t.get('is_locked')),
            'unlock_url': t.get('premium_url') or premium_url, 'unlock_label': 'Unlock Premium',
            'is_new': bool(t.get('is_newly_added')),
            'meta': [{'icon': 'far fa-question-circle', 'text': f"{t.get('total_questions')} Qs"},
                     {'icon': 'far fa-check-square', 'text': f"{t.get('total_marks')} Marks"},
                     {'icon': 'far fa-clock', 'text': f"{t.get('total_duration_minutes')} Min"}],
            'action_url': url_for('users.test_login', section_id=section_id, test_key=t.get('test_key'),
                                  course_code=course_code, unique_code=unique_code),
            'action_label': 'Start Test', 'resume_label': 'Resume Test', 'launch': 'same',
        })
    completed = []
    for t in data.get('completed_tests_details', []):
        ts = t.get('submission_timestamp')
        completed.append({
            'title': t.get('subject_title'), 'subtitle': t.get('subject_subtitle'),
            'submitted_at': ts.strftime('%d %b %Y, %I:%M %p') if hasattr(ts, 'strftime') else (ts or None),
            'score': '%.2f' % float(t.get('net_score') or 0), 'percentage': '%.2f' % float(t.get('percentage') or 0),
            'result_url': url_for('users.test_result', section_id=section_id, test_key=t.get('test_key'),
                                  course_code=course_code, unique_code=unique_code),
        })
    return render_template(
        'users/exam_platform/test_list.html',
        portal_label='Mock Tests', portal_icon='fa-file-pen',
        intro=f"{data.get('course_name') or course_code} {data.get('stream') or ''} - full-length tests in the exam window.".strip(),
        tests=tests, completed=completed, paid_blocks=[],
        email=email, username=username, course_code=course_code, unique_code=unique_code,
        dashboard_type=dashboard_type, subscribed=subscribed, premium_url=premium_url,
        back_url=url_for('users.view_course_dashboard', course_code=course_code, unique_code=unique_code),
        shop_url=url_for('users.course_shop', course_code=course_code, unique_code=unique_code),
        section_id=section_id,
    )