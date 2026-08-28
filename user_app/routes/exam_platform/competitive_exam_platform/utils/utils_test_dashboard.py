import datetime
import logging
from functools import wraps
from flask import session, redirect, url_for, flash, request
from routes.exam_platform.competitive_exam_platform.databases.question_handler_db import ContentOperation
from routes.exam_platform.competitive_exam_platform.databases.main_handler_db import UserOperation
from routes.exam_platform.competitive_exam_platform.databases.result_handler_db  import ResultHandler

user_op = UserOperation()
content_op = ContentOperation()
result_handler = ResultHandler()

logger = logging.getLogger(__name__)

def establish_user_session(actual_email, actual_username):
    session.pop('guest_email', None)
    session.pop('guest_username', None)
    session["user_email"] = actual_email
    session["user_username"] = actual_username
    session.permanent = True
    session.modified = True
    logger.info(f"USER_SESSION: Session established for {actual_email}")


def get_user_session():
    user_email = session.get("user_email")
    user_username = session.get("user_username")

    if user_email and user_username and not user_email.startswith("guest_"):
        logger.info(f"USER_SESSION: Session valid for {user_email}")
        return user_email, user_username, True

    logger.info("USER_SESSION: No authenticated session")
    return None, None, False

def check_session(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function

def redirect_if_test_not_found(test, endpoint, **kwargs):
    if not test:
        logger.warning(f"TEST_ACCESS: Test not found with provided details.")
        flash('Test details not found.', 'danger')
        return redirect(url_for(endpoint, **kwargs))
    logger.info(f"TEST_ACCESS: Test found.")
    return None

def format_section_count(sections):
    if not sections:
        return "0 sections"
    num_sections = len(sections)
    section_text = f"{num_sections} section{'s' if num_sections > 1 else ''}"
    logger.debug(f"SECTION_COUNT: Formatted section count: {section_text}")
    return section_text

def _process_tests_for_new_badge(tests):
    processed_tests = []
    three_days_ago = datetime.datetime.now() - datetime.timedelta(days=3)
    for test in tests:
        last_update_time = test.get('updated_at')
        if last_update_time:
            test['is_newly_added'] = last_update_time > three_days_ago
        else:
            test['is_newly_added'] = False
        processed_tests.append(test)
    return processed_tests

def _prepare_test_data(all_tests_basic_info, email, section_id):
    pending_tests = []
    completed_tests_details = []
    course_name = ''
    stream = ''

    completed_tests_from_db = user_op.get_completed_tests_for_user(email, section_id)
    completed_test_keys = {test['test_key'] for test in completed_tests_from_db}

    completed_tests_map = {test['test_key']: test for test in completed_tests_from_db}

    if all_tests_basic_info:
        course_name = all_tests_basic_info[0].get('course_name', '')
        stream = all_tests_basic_info[0].get('stream', '')

        for test_basic in all_tests_basic_info:
            test_key = test_basic.get('test_key')
            
            if test_key in completed_test_keys:
                completed_test_entry = completed_tests_map.get(test_key)
                if completed_test_entry:
                    completed_tests_details.append(completed_test_entry)
            else:
                pending_tests.append(test_basic)
    
    display_tests = _process_tests_for_new_badge(pending_tests)
    
    return {
        'display_tests': display_tests,
        'completed_tests_details': completed_tests_details,
        'course_name': course_name,
        'stream': stream
    }

def prepare_mock_test_data_free(course_code, email, section_id):
    all_tests_basic_info = content_op.get_mock_tests_free(section_id, course_code, email)
    return _prepare_test_data(all_tests_basic_info, email, section_id)

def prepare_mock_test_data_paid(course_code, email, section_id):
    all_tests_basic_info = content_op.get_mock_tests_paid(section_id, course_code, email)
    return _prepare_test_data(all_tests_basic_info, email, section_id)