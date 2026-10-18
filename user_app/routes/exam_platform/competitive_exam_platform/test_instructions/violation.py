from flask import jsonify, render_template, request, session
from routes.exam_platform.competitive_exam_platform.databases.main_handler_db import UserOperation
from routes.exam_platform.competitive_exam_platform.utils.utils_test_dashboard import get_user_session
from routes.exam_platform.competitive_exam_platform.utils.utils_secure_code import secure_access_required
from extensions import user_login_required
from routes import users_bp
import logging

user_op = UserOperation()

logger = logging.getLogger(__name__)

@users_bp.route('/api/record-violation/<test_key>/<course_code>/<unique_code>', methods=['POST'])
@secure_access_required(('course_code', 'unique_code'))
def record_violation(test_key, course_code, unique_code):
    from datetime import datetime
    email, username, user_is_authenticated = get_user_session()
    if not user_is_authenticated:
        return jsonify({'status': 'error', 'message': 'Authentication required'}), 401

    data = request.get_json()
    try:
        violation_type = data.get('violationType')
        details = data.get('details')

        session_key = f"violations:{email}:{test_key}"
        violations = session.get(session_key, [])
        violations.append({
            'type': violation_type,
            'details': details,
            'timestamp': datetime.utcnow().isoformat()
        })
        session[session_key] = violations
        session.modified = True

        if len(violations) >= 5 or violation_type == 'devtools_open':
            attempt_number = session.get('current_test_attempt_number')
            if not attempt_number:
                attempt_number = user_op.get_test_status_for_user(email, test_key).get('attempt_number')
            if attempt_number:
                user_op.terminate_user_test_log(email, test_key, attempt_number)
            session.pop(session_key, None)
            session[f"terminated:{email}:{test_key}"] = True
            return jsonify({'status': 'terminated'}), 403

        return jsonify({'status': 'success'}), 200
    except Exception as e:
        logger.exception("Violation recording failed")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@users_bp.route('/api/terminate-violation/<test_key>/<course_code>/<unique_code>', methods=['POST'])
@secure_access_required(('course_code', 'unique_code'))
def terminate_violation(test_key, course_code, unique_code):
    email, username, user_is_authenticated = get_user_session()
    if not user_is_authenticated:
        return jsonify({'status': 'error', 'message': 'Authentication required'}), 401

    data = request.get_json(silent=True) or {}
    violation_type = data.get('violationType') or data.get('reason') or 'away_too_long'
    details = data.get('details', '')

    attempt_number = session.get('current_test_attempt_number')
    if not attempt_number:
        attempt_number = user_op.get_test_status_for_user(email, test_key).get('attempt_number')
    if attempt_number:
        user_op.terminate_user_test_log(email, test_key, attempt_number)

    session.pop(f"violations:{email}:{test_key}", None)
    session.pop('test_token', None)
    session.pop('current_test_attempt_number', None)
    session[f"terminated:{email}:{test_key}"] = True
    session.modified = True

    logger.warning(f"TEST TERMINATED: [{email}] test={test_key} reason={violation_type} details={details!r}")
    from flask import url_for
    return jsonify({'status': 'terminated',
                    'redirect': url_for('users.test_terminated', test_key=test_key, course_code=course_code,
                                        unique_code=unique_code, violation_type=violation_type)}), 200


@users_bp.route('/test-terminated/<test_key>/<course_code>/<unique_code>/<violation_type>')
@user_login_required
@secure_access_required(('course_code', 'unique_code'))
def test_terminated(test_key, course_code, unique_code, violation_type):
    email, _, _ = get_user_session()
    section_id = None
    try:
        details = user_op.get_test_details(test_key) or {}
        section_id = details.get('test_id') or details.get('section_id')
    except Exception:
        logger.exception(f"TEST TERMINATED page: could not resolve section for {test_key}")

    session.pop('test_token', None)
    session.pop('current_test_attempt_number', None)
    session.pop('test_popup_initiated', None)
    session.modified = True

    logger.info(f"TEST TERMINATED page shown: [{email}] test={test_key} reason={violation_type}")
    return render_template("users/exam_platform/competitive_exam_platform/test_instructions/termination.html",
                           test_key=test_key,
                           course_code=course_code,
                           unique_code=unique_code,
                           section_id=section_id,
                           violation_type=violation_type)