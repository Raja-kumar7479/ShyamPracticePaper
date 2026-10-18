import logging
import datetime
from flask import flash, jsonify, redirect, render_template, request, session, url_for
from routes.exam_platform.competitive_exam_platform.databases.main_handler_db import UserOperation
from routes.exam_platform.competitive_exam_platform.utils.utils_test_dashboard import get_user_session
from routes.exam_platform.competitive_exam_platform.utils.utils_secure_code import secure_access_required
from routes import users_bp

logger = logging.getLogger(__name__)
user_op = UserOperation()


@users_bp.route('/test-login/<section_id>/<test_key>/<course_code>/<unique_code>', methods=['GET', 'POST'])
@secure_access_required(('course_code', 'unique_code'))
def test_login(section_id, test_key, course_code, unique_code):
    email, username, user_is_authenticated = get_user_session()
    logger.info(f"TEST LOGIN 1: [{request.method}] user={email} test_key={test_key} section_id={section_id}")

    if not user_is_authenticated or not email:
        logger.warning(f"TEST LOGIN BLOCKED: unauthenticated request for test {test_key}")
        if request.method == 'POST':
            return jsonify({"success": False, "message": "Your session expired. Please log in again."}), 401
        flash('Please log in to start the test.', 'login_warning')
        return redirect(url_for('users.user_login'))

    if request.method == 'GET':
        from routes.exam_platform.active_test_lock import active_test_redirect, blocked_message
        running = active_test_redirect(email, ignore_test_key=test_key)
        if running:
            flash(blocked_message(), 'test_error')
            return redirect(url_for('users.open_mock_test_section', section_id=section_id,
                                    course_code=course_code, unique_code=unique_code))

    from routes.exam_platform.competitive_exam_platform.utils.utils_test_access import test_access_denied
    denied = test_access_denied(email, section_id, test_key, course_code, unique_code)
    if denied:
        logger.warning(f"TEST LOGIN BLOCKED: [{email}] {denied['reason']} needed for test {test_key}")
        if request.method == 'POST':
            return jsonify({"success": False, "message": denied['message'],
                            "redirect": denied['redirect_url']}), 403
        flash(denied['message'], 'warning')
        return redirect(denied['redirect_url'])

    test_details = user_op.get_test_details(test_key)
    logger.info(f"TEST LOGIN 2: test_details {'found' if test_details else 'NOT FOUND'} for key={test_key}")

    if not test_details:
        logger.warning(f"TEST LOGIN BLOCKED: no test_description row for key={test_key} (user {email})")
        if request.method == 'POST':
            return jsonify({
                "success": False,
                "message": "This test has no description set up yet. Please contact your administrator."
            }), 404
        flash('Test not found. The link may be invalid.', 'test_error')
        return redirect(url_for('users.open_mock_test_section', section_id=section_id, course_code=course_code, unique_code=unique_code))

    if request.method == 'POST':
        submitted_key = request.form.get('test_key')
        logger.info(f"TEST LOGIN 3: submitted_key={submitted_key!r} expected={test_key!r}")

        if test_key == submitted_key:
            logger.info(f"TEST LOGIN 4: key matched for user {email}")

            test_status_info = user_op.get_test_status_for_user(email, test_key) or {}
            current_status = test_status_info.get('status')
            logger.info(f"TEST LOGIN 5: current status for {email} = {current_status!r}")

            if current_status == 'completed':
                logger.warning(f"User {email} attempted to retake completed test {test_key}.")
                return jsonify({
                    "success": False,
                    "message": "You have already completed this test."
                }), 403
            
            from routes.exam_platform.active_test_lock import get_active_test, blocked_message
            other = get_active_test(email, ignore_test_key=test_key)
            if other:
                logger.warning(f"TEST LOGIN BLOCKED: [{email}] has active {other['portal']} test {other['test_key']}")
                return jsonify({"success": False, "message": blocked_message(other)}), 409

            if current_status == 'in_progress':
                last_heartbeat = test_status_info.get('last_heartbeat')
                attempt_number = test_status_info.get('attempt_number')
                
                is_active_session = False
                if last_heartbeat:
                    time_diff = (datetime.datetime.now() - last_heartbeat).total_seconds()
                    if time_diff <= 30:
                        is_active_session = True
                
                if is_active_session:
                    logger.warning(f"User {email} attempted to start test {test_key} that is actively in progress.")
                    return jsonify({
                        "success": False,
                        "message": "This test is already in progress in another window. Please complete or close that session."
                    }), 403
                else:
                    logger.info(f"Found stale 'in_progress' session for user {email}, test {test_key}. Terminating it.")
                    user_op.terminate_user_test_log(email, test_key, attempt_number)

            session.pop(f"terminated:{email}:{test_key}", None)
            session.pop(f"violations:{email}:{test_key}", None)

            try:
                attempt_number = user_op.store_user_test_start(email, test_key, username)
                logger.info(f"TEST LOGIN 6: attempt {attempt_number} recorded for {email}")
            except Exception as e:
                logger.exception(f"TEST LOGIN FAILED: could not record attempt for {email} on {test_key}: {e}")
                return jsonify({
                    "success": False,
                    "message": "Could not start the test. Please try again or contact support."
                }), 500

            if not attempt_number:
                logger.error(f"TEST LOGIN FAILED: store_user_test_start returned {attempt_number!r} for {email}")
                return jsonify({
                    "success": False,
                    "message": "Could not start the test. Please try again."
                }), 500

            session['test_popup_initiated'] = True
            session['current_test_attempt_number'] = attempt_number
            session.modified = True

            instruction_url = url_for('users.test_instruction', section_id=section_id, test_key=test_key, course_code=course_code, unique_code=unique_code)
            logger.info(f"TEST LOGIN 7: sending {email} to {instruction_url}")

            return jsonify({
                "success": True,
                "instructionUrl": instruction_url
            })
        else:
            logger.warning(f"TEST LOGIN BLOCKED: invalid key from {email} for test {test_key}")
            return jsonify({
                "success": False,
                "message": "Invalid Test Key!"
            }), 401

    test_status_info = user_op.get_test_status_for_user(email, test_key) or {}
    if test_status_info.get('status') == 'in_progress':
        last_heartbeat = test_status_info.get('last_heartbeat')
        if last_heartbeat and (datetime.datetime.now() - last_heartbeat).total_seconds() <= 30:
            logger.info(f"TEST LOGIN 8a: {email} has test {test_key} open in the exam window; showing notice")
            return render_template(
                'users/exam_platform/competitive_exam_platform/test_window/test_open_notice.html',
                test=test_details,
                section_id=section_id,
                test_key=test_key,
                course_code=course_code,
                unique_code=unique_code,
                username=username
            )

    logger.info(f"TEST LOGIN 8: rendering login page for {email}, test {test_key}")
    return render_template(
        'users/exam_platform/competitive_exam_platform/test_window/test_login.html',
        test=test_details,
        test_key=test_key,
        course_code=course_code,
        unique_code=unique_code,
        username=username,
        section_id=section_id
    )