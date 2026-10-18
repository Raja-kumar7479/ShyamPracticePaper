from flask import jsonify, render_template, request, session, redirect, url_for, Blueprint
from routes.exam_platform.competitive_exam_platform.databases.test_handler_db import TestHandler

from routes.exam_platform.competitive_exam_platform.databases.main_handler_db import UserOperation
from routes.exam_platform.competitive_exam_platform.utils.utils_test_dashboard import get_user_session
from routes.exam_platform.competitive_exam_platform.utils.utils_secure_code import secure_access_required
from routes import users_bp
import json
import os
import logging
from flask_mail import Mail
user_op = UserOperation()
logger = logging.getLogger(__name__)

@users_bp.route('/test_feedback/<section_id>/<test_key>/<course_code>/<unique_code>')
@secure_access_required(('course_code', 'unique_code'))
def test_feedback(section_id, test_key, course_code, unique_code):
    email, username, user_is_authenticated = get_user_session()
    test_details = user_op.get_test_details(test_key)
    return render_template('users/exam_platform/competitive_exam_platform/test_results/test_feedback_form.html',
                           test_key=test_key, 
                           course_code=course_code, 
                           unique_code=unique_code,
                           email=email, 
                           username=username, 
                           section_id=section_id,
                           test_id=test_details.get('test_id'))

@users_bp.route('/submit_feedback/<section_id>/<test_key>/<course_code>/<unique_code>', methods=['POST'])
@secure_access_required(('course_code', 'unique_code'))
def submit_feedback(section_id, test_key, course_code, unique_code):
    email, username, user_is_authenticated = get_user_session()
    try:
        feedback_data = request.get_json(silent=True)
        if not isinstance(feedback_data, dict):
            return jsonify({"status": "error", "message": "Send the feedback as JSON."}), 400
        test_details = user_op.get_test_details(test_key)
        if not test_details or not test_details.get('test_id'):
            return jsonify({"status": "error", "message": "That test does not exist."}), 404
        test_id = test_details.get('test_id')
        
        query = """
            INSERT INTO test_feedback (test_id, test_key, email, feedback_software, feedback_content, feedback_speed, suggestions)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        user_op.execute_query(query, (
            test_id, test_key, email, 
            feedback_data.get('software_feedback'), 
            feedback_data.get('content_feedback'), 
            feedback_data.get('speed_feedback'), 
            feedback_data.get('suggestions')
        ))
        
        dashboard_url = url_for('users.open_mock_test_section', section_id=section_id,
                                course_code=course_code, unique_code=unique_code)

        return jsonify({
            "status": "success",
            "message": "Feedback submitted successfully!",
            "redirect_url": dashboard_url
        }), 200
    except Exception as e:
        logger.exception(f"Failed to submit feedback for test {test_key} by user {email}: {e}")
        return jsonify({"status": "error", "message": "Failed to submit feedback."}), 500