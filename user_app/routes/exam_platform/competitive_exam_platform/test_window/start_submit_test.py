from flask import flash, jsonify, redirect, render_template, request, session, url_for
from routes.exam_platform.competitive_exam_platform.databases.test_handler_db import TestHandler
from routes.exam_platform.competitive_exam_platform.databases.main_handler_db import UserOperation
from routes.exam_platform.competitive_exam_platform.utils.utils_test_dashboard import get_user_session
from routes.exam_platform.competitive_exam_platform.utils.utils_secure_code import secure_access_required
from routes.exam_platform.competitive_exam_platform.utils.utils_test_token import generate_test_token, validate_test_token
from extensions import user_login_required
from routes import users_bp
import json
import os
import logging
import datetime

test_op = TestHandler()
user_op = UserOperation()
logger = logging.getLogger(__name__)

@users_bp.route('/start-test/<section_id>/<test_key>/<course_code>/<unique_code>', methods=['GET'])
@secure_access_required(('course_code', 'unique_code'))
def start_test(section_id, test_key, course_code, unique_code):
    email, username, user_is_authenticated = get_user_session()

    if not session.pop('test_popup_initiated', False):
        logger.warning(f"User {email} tried direct URL access for test {test_key}.")
        return redirect(url_for('users.test_terminated', test_key=test_key, course_code=course_code, unique_code=unique_code, violation_type='direct_url_access'))

    test_basic_info = user_op.get_test_details(test_key)
    if not test_basic_info:
        flash('Test details not found.', 'test_error')
        return redirect(url_for('users.purchase_dashboard', course_code=course_code, unique_code=unique_code))

    test_status_info = user_op.get_test_status_for_user(email, test_key)
    current_status = test_status_info.get('status')
    attempt_number = test_status_info.get('attempt_number')
    last_heartbeat = test_status_info.get('last_heartbeat')
    
    session_attempt_number = session.get('current_test_attempt_number')

    if current_status == 'completed':
        flash('Test already completed. You cannot retake it.', 'test_warning')
        logger.warning(f"User {email} tried to start completed test {test_key}.")
        return redirect(url_for('users.open_mock_test_section', section_id=section_id, course_code=course_code, unique_code=unique_code))

    if current_status == 'in_progress':
        is_active_session = False
        if last_heartbeat:
            time_diff = (datetime.datetime.now() - last_heartbeat).total_seconds()
            if time_diff <= 30:
                is_active_session = True
        
        if is_active_session and attempt_number != session_attempt_number:
            flash('This test is already in progress in another window.', 'test_error')
            logger.warning(f"User {email} tried to start test {test_key} already in progress in another session.")
            return redirect(url_for('users.open_mock_test_section', section_id=section_id, course_code=course_code, unique_code=unique_code))
        elif not is_active_session:
            logger.warning(f"User {email} starting test {test_key} with a stale 'in_progress' session. Terminating old one.")
            user_op.terminate_user_test_log(email, test_key, attempt_number)
            current_status = 'unperformed'
        else:
            logger.info(f"User {email} is refreshing the active test window for {test_key}.")

    if current_status != 'unperformed' and current_status != 'in_progress':
        flash('Invalid test session. Please try logging into the test again.', 'test_error')
        logger.error(f"User {email} reached start_test for {test_key} with invalid status: {current_status}.")
        return redirect(url_for('users.test_login', section_id=section_id, test_key=test_key, course_code=course_code, unique_code=unique_code))

    if current_status == 'unperformed':
        user_op.set_test_status_in_progress(email, test_key, attempt_number)
        logger.info(f"User {email} set test {test_key} to 'in_progress' for attempt {attempt_number}.")
    
    session['current_test_attempt_number'] = attempt_number

    course_specific_info = user_op.get_course_info_by_test_id(test_basic_info['test_id'])
    if not course_specific_info:
        flash('Course details could not be found.', 'test_error')
        return redirect(url_for('users.purchase_dashboard', course_code=course_code, unique_code=unique_code))

    test_course_info = {**test_basic_info, **course_specific_info}
    
    instructions_data = {}
    try:
        file_path = os.path.join(os.path.dirname(__file__), 'instruction_popup.json')
        with open(file_path, 'r', encoding='utf-8') as f:
            instructions_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"ERROR: Could not load instruction_popup.json. Details: {e}")
        instructions_data = {"part1": "<p>Error: Instructions could not be loaded.</p>", "part2": ""}

    duration_seconds = (test_course_info.get('total_duration_minutes') or 0) * 60
    new_token = generate_test_token(email, test_key, duration_seconds)
    session['test_token'] = new_token
    sections = user_op.get_test_sections(test_key)

    return render_template('users/exam_platform/competitive_exam_platform/test_window/test_window.html',
                           test_key=test_key,
                           section_id=section_id,
                           course_info=test_basic_info, 
                           duration_seconds=duration_seconds,
                           test_course_info=test_course_info,
                           sections_data=sections, 
                           username=username, 
                           unique_code=unique_code, 
                           course_code=course_code,
                           email=email,
                           show_calculator=bool(test_basic_info.get('show_calculator', 1)),
                           instructions=instructions_data)

@users_bp.route('/submit-test-action/<section_id>/<test_key>/<course_code>/<unique_code>', methods=['POST'])
@secure_access_required(('course_code', 'unique_code'))
def submit_test_action(section_id, test_key, course_code, unique_code):
    email, username, user_is_authenticated = get_user_session()
    token = session.get('test_token')

    if not validate_test_token(token, email, test_key):
        return jsonify({"error": "Invalid or expired session token."}), 403

    submission_data = request.json
    if not submission_data:
        return jsonify({"error": "No submission data received."}), 400

    test_result_id, error_message = test_op.save_test_submission(email, username, test_key, submission_data)

    if error_message:
        return jsonify({"error": error_message}), 500

    session.pop('test_token', None)
    session.pop('current_test_attempt_number', None)

    if test_result_id:
        tcs_flow = session.get('tcs_flow') or {}
        if tcs_flow.get('aptitude_test_key') == test_key and tcs_flow.get('exam_id'):
            next_url = url_for('tcs.after_aptitude', exam_id=tcs_flow['exam_id'])
            return jsonify({"message": "Aptitude part submitted.", "redirect_url": next_url}), 200
        feedback_url = url_for('users.test_feedback', section_id=section_id, test_key=test_key, course_code=course_code, unique_code=unique_code)
        return jsonify({"message": "Test submitted successfully.", "redirect_url": feedback_url}), 200

    return jsonify({"error": "An unexpected error occurred."}), 500

@users_bp.route('/test-heartbeat/<test_key>', methods=['POST'])
def test_heartbeat(test_key):
    email, _, _ = get_user_session()
    token = session.get('test_token')
    
    if not email or not validate_test_token(token, email, test_key):
        return jsonify({"error": "Invalid or missing session."}), 403
    
    attempt_number = session.get('current_test_attempt_number')
    if not attempt_number:
        logger.warning(f"Heartbeat from {email} for {test_key} failed: No attempt number in session.")
        return jsonify({"error": "Invalid test session state."}), 403

    try:
        user_op.update_test_heartbeat(email, test_key, attempt_number)
        return jsonify({"success": True, "message": "Heartbeat received."}), 200
    except Exception as e:
        logger.exception(f"Error updating heartbeat for {email}, {test_key}: {e}")
        return jsonify({"error": "Server error processing heartbeat."}), 500

@users_bp.route('/release-test-window/<test_key>', methods=['POST'])
def release_test_window(test_key):
    email, _, _ = get_user_session()
    if not email:
        return jsonify({"success": False, "reason": "no_session"}), 200

    info = user_op.get_test_status_for_user(email, test_key) or {}
    if info.get('status') != 'in_progress':
        return jsonify({"success": True, "reason": "not_running"}), 200

    attempt_number = session.get('current_test_attempt_number') or info.get('attempt_number')
    if not attempt_number:
        return jsonify({"success": False, "reason": "no_attempt"}), 200

    user_op.terminate_user_test_log(email, test_key, attempt_number)
    session.pop('test_token', None)
    session.pop('current_test_attempt_number', None)
    session[f"terminated:{email}:{test_key}"] = True
    session.modified = True
    logger.info(f"WINDOW RELEASE: [{email}] closed test window for {test_key}, attempt {attempt_number}")
    return jsonify({"success": True, "reason": "released"}), 200


@users_bp.route('/terminate-test-session/<test_key>', methods=['POST'])
def terminate_test_session(test_key):
    email, _, _ = get_user_session()
    token = session.get('test_token')

    if not email or not validate_test_token(token, email, test_key):
        logger.warning(f"Invalid terminate request for {test_key}. Missing email or invalid token.")
        return jsonify({"error": "Invalid or missing session."}), 403

    attempt_number = session.get('current_test_attempt_number')
    if not attempt_number:
        logger.warning(f"Terminate request from {email} for {test_key} failed: No attempt number in session.")
        test_status_info = user_op.get_test_status_for_user(email, test_key)
        attempt_number = test_status_info.get('attempt_number')
        if not attempt_number or test_status_info.get('status') != 'in_progress':
            return jsonify({"success": False, "message": "No active session found to terminate."}), 404
    
    test_status_info = user_op.get_test_status_for_user(email, test_key)
    
    if test_status_info.get('status') == 'in_progress' and test_status_info.get('attempt_number') == attempt_number:
        user_op.terminate_user_test_log(email, test_key, attempt_number)
        logger.info(f"User {email} terminated test session for {test_key}, attempt {attempt_number}")
        session.pop('test_token', None)
        session.pop('current_test_attempt_number', None)
        return jsonify({"success": True, "message": "Session terminated."}), 200
    elif test_status_info.get('status') == 'completed':
        logger.info(f"User {email} tried to terminate already completed test {test_key}.")
        return jsonify({"success": False, "message": "Test already completed."}), 200
    
    logger.warning(f"User {email} tried to terminate non-active session for {test_key}")
    return jsonify({"success": False, "message": "No active session found to terminate."}), 404