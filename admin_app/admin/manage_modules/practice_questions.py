import logging
from flask import jsonify, render_template, request, Blueprint, flash
from .content_db import UserOperation
from extensions import admin_login_required, admin_owner_required, can_manage
from admin import admin_bp

logger = logging.getLogger(__name__)

user_op = UserOperation()

@admin_bp.route('/admin/practice_questions', methods=['GET', 'POST'])
@admin_login_required
def manage_practice_questions():
    try:
        if request.method == 'POST':
            code = request.form.get('code')
            section = request.form.get('section')
            title = request.form.get('title')

            logger.info(f"Attempting to create a new practice question with title: '{title}'")

            section = (section or '').strip()
            title = (title or '').strip()
            if len(section) > 100:
                return jsonify({'success': False, 'message': 'Section name must be 100 characters or fewer.'}), 400
            if not all([code, section, title]):
                logger.warning("Validation failed: One or more fields are missing for new practice question.")
                flash('All fields are required.', 'admin_error')
                return jsonify({'success': False, 'message': 'All fields are required.'}), 400

            for row in user_op.get_questions_by_code(code) or []:
                if row.get('section') == section and (row.get('title') or '').strip().lower() == title.strip().lower():
                    return jsonify({'success': False, 'message': f'"{title}" already exists for {code} ({section}). Nothing was added.'}), 409
            new_id = user_op.insert_question(code, section, title)
            if not new_id:
                logger.error(f"Database insertion failed for practice question with title: '{title}'")
                flash('Failed to save question to the database.', 'admin_error')
                return jsonify({'success': False, 'message': 'Failed to save question to the database.'}), 500

            new_question = user_op.get_question_by_id(new_id)
            logger.info(f"Successfully created practice question with ID {new_id}.")
            flash('Question added successfully!', 'admin_success')
            return jsonify({'success': True, 'question': new_question})

        logger.info("Fetching data for the practice questions management page.")
        course_codes = user_op.get_distinct_course_codes()
        section_options = ['Topic-wise', 'Subject-wise', 'Year-wise']

        return render_template('admin/manage_modules/practice_questions.html',
                               course_codes=course_codes,
                               section_options=section_options)

    except Exception as e:
        logger.exception(f"An unexpected error occurred in manage_practice_questions (Method: {request.method}).")
        flash('An internal server error occurred.', 'admin_error')
        return jsonify({'success': False, 'message': 'An internal server error occurred.'}), 500

@admin_bp.route('/api/questions_by_code', methods=['GET'])
@admin_login_required
def get_questions_by_code():
    code = request.args.get('code')
    if not code:
        return jsonify({'success': False, 'message': 'Course code is required.'}), 400
    
    logger.info(f"Fetching questions for course code: {code}")
    questions = user_op.get_questions_by_code(code)
    return jsonify({'success': True, 'questions': questions})

@admin_bp.route('/admin/practice_questions/update/<int:question_id>', methods=['POST'])
@admin_login_required
def update_practice_question(question_id):
    data = request.get_json()
    field = data.get('field')
    value = data.get('value')

    logger.info(f"Attempting to update question ID {question_id}: setting field '{field}'")

    if not all([field, value is not None]):
        return jsonify({'success': False, 'message': 'Field and value are required.'}), 400
    
    success = user_op.update_question_field(question_id, field, value)
    if success:
        logger.info(f"Successfully updated question ID {question_id}.")
        return jsonify({'success': True, 'message': 'Question updated successfully.'})
    else:
        logger.error(f"Database update failed for question ID {question_id}.")
        return jsonify({'success': False, 'message': 'Database update failed.'}), 500

@admin_bp.route('/admin/practice_questions/delete/<int:question_id>', methods=['POST'])
@admin_login_required
def delete_practice_question(question_id):
    if not can_manage():
        return jsonify({'success': False, 'message': 'Permission Denied.'}), 403
    logger.info(f"Attempting to delete question with ID {question_id}.")
    success = user_op.delete_question(question_id)
    if success:
        logger.info(f"Successfully deleted question ID {question_id}.")
        return jsonify({'success': True, 'message': 'Question deleted successfully.'})
    else:
        logger.error(f"Database deletion failed for question ID {question_id}.")
        return jsonify({'success': False, 'message': 'Database deletion failed.'}), 500
