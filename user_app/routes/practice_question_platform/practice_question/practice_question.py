import json
import logging
from flask import render_template, request, session, redirect, url_for, jsonify, Blueprint
from routes.practice_question_platform.databases.question_handler_db import UserOperation
from routes.practice_question_platform.utils.utils_question import get_user_session,secure_access_required,has_question_access


from routes import users_bp

logger = logging.getLogger(__name__)

user_op = UserOperation()


def prepare_questions_for_display(questions):
    for q in questions or []:
        letters = []
        if q.get('question_image') and q.get('option_regions'):
            try:
                raw = q['option_regions']
                data = json.loads(raw) if isinstance(raw, str) else raw
                letters = sorted(k.upper() for k in (data or {}) if k in ('a', 'b', 'c', 'd'))
            except (ValueError, TypeError, AttributeError):
                letters = []
        q['image_option_letters'] = letters
    return questions

@users_bp.route('/questions/topic/<course_code>')
def browse_by_topic(course_code):
    user_email, user_username, user_is_authenticated = get_user_session()

    unique_code = None
    if user_is_authenticated:
        unique_code = user_op.get_unique_code(user_email, course_code)
    
    if not unique_code:
        unique_code = user_op.get_guest_access_code(course_code)
    
    if not unique_code:
        unique_code = f"{course_code.lower()}Gst4XyZ" 

    return redirect(url_for('users.browse_by_topic_with_code', unique_code=unique_code, course_code=course_code))

@users_bp.route('/questions/topic/<unique_code>/<course_code>')
@secure_access_required(('course_code', 'unique_code'))
def browse_by_topic_with_code(unique_code, course_code):
    try:
        user_email, user_username, user_is_authenticated = get_user_session()
        logger.info(f"User '{user_email}' fetching subjects for course: {course_code}")
        subjects = user_op.get_subjects_by_course(course_code)
        return render_template('users/practice_question_platform/topic_select.html', subjects=subjects, course_code=course_code, username=user_username, email=user_email, unique_code=unique_code, user_is_authenticated=user_is_authenticated)
    except Exception:
        logger.exception(f"Error fetching subjects for course: {course_code}")
        return "An internal server error occurred.", 500

@users_bp.route('/questions/topic/<unique_code>/<course_code>/<subject>')
@secure_access_required(('course_code', 'unique_code'))
def browse_topic_subject(unique_code, course_code, subject):
    try:
        user_email, user_username, user_is_authenticated = get_user_session()
        logger.info(f"User '{user_email}' fetching topics for subject: {subject}, course: {course_code}")
        topics = user_op.get_topics_by_subject(course_code, subject)
        return render_template('users/practice_question_platform/topic_list.html', topics=topics, subject=subject, course_code=course_code, username=user_username, email=user_email, unique_code=unique_code, user_is_authenticated=user_is_authenticated)
    except Exception:
        logger.exception(f"Error fetching topics for subject: {subject}, course: {course_code}")
        return "An internal server error occurred.", 500

@users_bp.route('/questions/topic/<unique_code>/<course_code>/<subject>/<topic>')
@secure_access_required(('course_code', 'unique_code'))
def show_topic_questions(unique_code, course_code, subject, topic):
    try:
        user_email, user_username, user_is_authenticated = get_user_session()
        page = request.args.get('page', 1, type=int)
        logger.info(f"User '{user_email}' viewing questions for topic: {topic}, page: {page}")
        per_page = 8
        
        total_result = user_op.get_question_count_topic(course_code, subject, topic)
        if total_result is None:
            logger.error(f"Failed to fetch question count for topic: {topic}")
            return "Could not retrieve question count.", 500
        total = total_result['total']
        
        offset = (page - 1) * per_page
        questions = prepare_questions_for_display(user_op.get_questions_topic(course_code, subject, topic, per_page, offset))
        total_pages = (total + per_page - 1) // per_page
        
        return render_template('users/practice_question_platform/display_questions.html', questions=questions, section='topic', subject=subject, topic=topic, course_code=course_code, page=page, total_pages=total_pages, username=user_username, email=user_email, unique_code=unique_code, user_is_authenticated=user_is_authenticated)
    except Exception:
        logger.exception(f"Error showing topic questions for topic: {topic}")
        return "An internal server error occurred.", 500

@users_bp.route('/questions/subject/<unique_code>/<course_code>')
@secure_access_required(('course_code', 'unique_code'))
def browse_by_subject(unique_code, course_code):
    try:
        user_email, user_username, user_is_authenticated = get_user_session()
        logger.info(f"User '{user_email}' starting subject-wise browse for course: {course_code}")
        subjects = user_op.get_subjects_by_course(course_code)
        return render_template('users/practice_question_platform/subject_select.html', subjects=subjects, course_code=course_code, username=user_username, email=user_email, unique_code=unique_code, user_is_authenticated=user_is_authenticated)
    except Exception:
        logger.exception(f"Error in browse_by_subject for course: {course_code}")
        return "An internal server error occurred.", 500

@users_bp.route('/questions/subject/<unique_code>/<course_code>/<subject>')
@secure_access_required(('course_code', 'unique_code'))
def show_subject_questions(unique_code, course_code, subject):
    try:
        user_email, user_username, user_is_authenticated = get_user_session()
        page = request.args.get('page', 1, type=int)
        logger.info(f"User '{user_email}' viewing questions for subject: {subject}, page: {page}")
        per_page = 8
        
        total_result = user_op.get_question_count_subject(course_code, subject)
        if total_result is None:
            logger.error(f"Failed to fetch question count for subject: {subject}")
            return "Could not retrieve question count.", 500
        total = total_result['total']
        
        offset = (page - 1) * per_page
        questions = prepare_questions_for_display(user_op.get_questions_subject(course_code, subject, per_page, offset))
        total_pages = (total + per_page - 1) // per_page
        
        return render_template('users/practice_question_platform/display_questions.html', questions=questions, section='subject', subject=subject, course_code=course_code, page=page, total_pages=total_pages, username=user_username, email=user_email, unique_code=unique_code, user_is_authenticated=user_is_authenticated)
    except Exception:
        logger.exception(f"Error showing subject questions for subject: {subject}")
        return "An internal server error occurred.", 500

@users_bp.route('/questions/year/<unique_code>/<course_code>')
@secure_access_required(('course_code', 'unique_code'))
def browse_by_year(unique_code, course_code):
    try:
        user_email, user_username, user_is_authenticated = get_user_session()
        logger.info(f"User '{user_email}' starting year-wise browse for course: {course_code}")
        years = user_op.get_years_by_course(course_code)
        return render_template('users/practice_question_platform/year_select.html', years=years, course_code=course_code, username=user_username, email=user_email, unique_code=unique_code, user_is_authenticated=user_is_authenticated)
    except Exception:
        logger.exception(f"Error in browse_by_year for course: {course_code}")
        return "An internal server error occurred.", 500

@users_bp.route('/questions/year/<unique_code>/<course_code>/<int:year>')
@secure_access_required(('course_code', 'unique_code'))
def show_year_questions(unique_code, course_code, year):
    try:
        user_email, user_username, user_is_authenticated = get_user_session()
        page = request.args.get('page', 1, type=int)
        logger.info(f"User '{user_email}' viewing questions for year: {year}, page: {page}")
        per_page = 8
        total_result = user_op.get_question_count_year(course_code, year)
        if total_result is None:
            logger.error(f"Failed to fetch question count for year: {year}")
            return "Could not retrieve question count.", 500
        total = total_result['total']
        
        offset = (page - 1) * per_page
        questions = prepare_questions_for_display(user_op.get_questions_year(course_code, year, per_page, offset))
        total_pages = (total + per_page - 1) // per_page
        
        return render_template('users/practice_question_platform/display_questions.html', questions=questions, section='year', year=year, course_code=course_code, page=page, total_pages=total_pages, username=user_username, email=user_email, unique_code=unique_code, user_is_authenticated=user_is_authenticated)
    except Exception:
        logger.exception(f"Error showing year questions for year: {year}")
        return "An internal server error occurred.", 500

@users_bp.route('/check_answer/<int:question_id>', methods=['POST'])
def check_answer_form(question_id):
    user_email, user_username, user_is_authenticated = get_user_session()
    try:
        data = request.get_json()
        if not data:
            logger.warning(f"User '{user_email}' sent empty payload for question_id: {question_id}")
            return jsonify({'error': 'Bad request. No data received.'}), 400
        
        selected_option = data.get('selected_option')
        logger.info(f"User '{user_email}' checking answer for question_id: {question_id} with option: {selected_option}")
        
        question = user_op.get_question_by_id(question_id)
        if not question:
            logger.warning(f"Question not found for id: {question_id} attempt by user: '{user_email}'")
            return jsonify({'error': 'Question not found.'}), 404

        course_code = question.get('paper_code') or question.get('code')
        if not has_question_access(course_code):
            logger.warning(f"SECURITY: '{user_email}' denied answer for QID {question_id} "
                           f"(no access to course {course_code!r}).")
            return jsonify({'error': 'You do not have access to this question.'}), 403

        correct_option = question['correct_option']
        question_type = question['question_type']
        answer_text = question.get('answer_text', '')
        explanation_link = question.get('explanation_link', '')
        is_correct = False

        if question_type == 'MCQ':
            is_correct = selected_option == correct_option
        elif question_type == 'MSQ':
            if isinstance(selected_option, list):
                selected_set = set(opt.upper().strip() for opt in selected_option)
                correct_set = set(opt.strip().upper() for opt in correct_option.split(','))
                is_correct = selected_set == correct_set
        elif question_type == 'NAT':
            try:
                selected_str = str(selected_option).strip().lower()
                correct_str = correct_option.strip().lower()
                is_correct = selected_str == correct_str
            except Exception:
                logger.warning(f"Invalid NAT input for question_id: {question_id} from user: '{user_email}'", exc_info=True)
                return jsonify({
                    'error': 'Invalid input for NAT question.',
                    'correct_option': correct_option,
                    'answer_text': answer_text,
                    'explanation_link': explanation_link,
                    'is_correct': False
                })

        logger.info(f"Answer for QID:{question_id} by user '{user_email}' was {'correct' if is_correct else 'incorrect'}.")
        return jsonify({
            'is_correct': is_correct,
            'correct_option': correct_option,
            'answer_text': answer_text,
            'explanation_link': explanation_link
        })
    except Exception:
        logger.exception(f"Fatal error in check_answer_form for QID: {question_id}, user: '{user_email}'")
        return jsonify({'error': 'An internal server error occurred.'}), 500

@users_bp.route('/report_issue/<int:question_id>', methods=['POST'])
def report_issue(question_id):
    user_email, user_username, user_is_authenticated = get_user_session()
    try:
        data = request.get_json()
        problem_description = data.get('problem')
        
        if not problem_description or not isinstance(problem_description, str) or len(problem_description.strip()) < 10:
            logger.warning(f"Insufficient problem description for QID: {question_id}.")
            return jsonify({'error': 'Please provide a detailed description of the issue (minimum 10 characters).'}), 400

        if len(problem_description) > 2000:
            problem_description = problem_description[:2000]

        report_question = user_op.get_question_by_id(question_id)
        if not report_question:
            return jsonify({'error': 'Question not found.'}), 404
        course_code = report_question.get('paper_code') or report_question.get('code')
        if not has_question_access(course_code):
            logger.warning(f"SECURITY: '{user_email}' denied report for QID {question_id} "
                           f"(no access to course {course_code!r}).")
            return jsonify({'error': 'You do not have access to this question.'}), 403

        logger.info(f"Reporting issue for question ID: {question_id} by user '{user_email}'.")
        
        success = user_op.report_question_issue(question_id, problem_description.strip(), user_email)
        
        if success:
            logger.info(f"Successfully recorded issue for QID: {question_id}.")
            return jsonify({'message': 'Your report has been submitted successfully. Thank you for your feedback!'})
        else:
            logger.error(f"Failed to record issue for QID: {question_id}.")
            return jsonify({'error': 'We could not process your report at this time. Please try again later.'}), 500
            
    except Exception:
        logger.exception(f"Fatal error in report_issue for QID: {question_id}")
        return jsonify({'error': 'An internal server error occurred.'}), 500