import logging
from flask import flash, redirect, render_template, url_for
from routes.exam_platform.competitive_exam_platform.databases.result_handler_db import ResultHandler
from routes.exam_platform.competitive_exam_platform.databases.main_handler_db import UserOperation
from routes.exam_platform.competitive_exam_platform.utils.utils_test_dashboard import get_user_session
from routes.exam_platform.competitive_exam_platform.utils.utils_secure_code import secure_access_required
from routes import users_bp

logger = logging.getLogger(__name__)
result_handler = ResultHandler()
user_op = UserOperation()

@users_bp.route('/test_overview/<section_id>/<test_key>/<course_code>/<unique_code>')
@secure_access_required(('course_code', 'unique_code'))
def test_overview(section_id, test_key, course_code, unique_code):
    email, username, user_is_authenticated = get_user_session()
    
    summary_data = result_handler.get_test_summary_details(test_key, email)
    
    if not summary_data:
        flash("Test overview data not found.", "test_error")
        logger.warning(f"Test overview data not found for test_key: {test_key}, user: {email}")
        return redirect(url_for('users.purchase_dashboard', course_code=course_code, unique_code=unique_code))
        
    logger.info(f"User {email} is viewing test overview for test_key: {test_key}")
    
    return render_template('users/exam_platform/competitive_exam_platform/test_results/test_overview.html',
                           overview_table_data=summary_data.get('overall', {}),
                           test_key=test_key, 
                           test_id=section_id, 
                           course_code=course_code, 
                           unique_code=unique_code, 
                           username=username,
                           user_is_authenticated=user_is_authenticated)

@users_bp.route('/test_result/<section_id>/<test_key>/<course_code>/<unique_code>')
@secure_access_required(('course_code', 'unique_code'))
def test_result(section_id, test_key, course_code, unique_code):
    email, username, user_is_authenticated = get_user_session()
    
    summary_data = result_handler.get_test_summary_details(test_key, email)
    
    if not summary_data:
        flash("Could not retrieve test result details.", "test_error")
        logger.warning(f"Test result details not found for test_key: {test_key}, user: {email}")
        return redirect(url_for('users.open_mock_test_section', section_id=section_id, course_code=course_code, unique_code=unique_code))
        
    logger.info(f"User {email} is viewing test result for test_key: {test_key}")
    
    return render_template('users/exam_platform/competitive_exam_platform/test_results/test_result.html',
                           summary=summary_data, 
                           test_key=test_key, 
                           section_id=section_id,
                           course_code=course_code,
                           unique_code=unique_code, 
                           username=username, 
                           current_user_email=email,
                           user_is_authenticated=user_is_authenticated)

@users_bp.route('/test_analysis/<section_id>/<test_key>/<course_code>/<unique_code>')
@secure_access_required(('course_code', 'unique_code'))
def test_analysis(section_id, test_key, course_code, unique_code):
    email, username, user_is_authenticated = get_user_session()
    
    summary_data = result_handler.get_test_summary_details(test_key, email)
    
    if not summary_data:
        flash("Could not retrieve detailed test analysis.", "test_error")
        logger.warning(f"Test analysis data not found for test_key: {test_key}, user: {email}")
        return redirect(url_for('users.test_result', section_id=section_id, test_key=test_key, course_code=course_code, unique_code=unique_code))
        
    questions_by_section = {}
    for q in summary_data.get('details', []):
        section_name = q.get('section_name', 'Default Section')
        if section_name not in questions_by_section:
            questions_by_section[section_name] = []
        questions_by_section[section_name].append(q)
        
    logger.info(f"User {email} is viewing test analysis for test_key: {test_key}")
    
    return render_template('users/exam_platform/competitive_exam_platform/test_results/test_analysis.html',
                           summary=summary_data, 
                           questions_by_section=questions_by_section,
                           sorted_sections=sorted(questions_by_section.keys()),
                           test_key=test_key, 
                           section_id=section_id,
                           course_code=course_code, 
                           unique_code=unique_code, 
                           username=username,
                           user_is_authenticated=user_is_authenticated)