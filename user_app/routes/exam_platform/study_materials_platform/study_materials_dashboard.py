from flask import abort, redirect, render_template, request, url_for, send_file, current_app, session, flash
from werkzeug.exceptions import HTTPException
import os
from collections import defaultdict
from routes.exam_platform.competitive_exam_platform.databases.main_handler_db import UserOperation
from routes.exam_platform.competitive_exam_platform.utils.utils_test_dashboard import get_user_session
from routes.exam_platform.competitive_exam_platform.databases.question_handler_db import ContentOperation

from routes.courses_platform.utils.utils_secure_code import secure_access_required
from extensions import user_login_required
from routes import users_bp
import logging

user_op = UserOperation()
content_op = ContentOperation()

logger = logging.getLogger(__name__)


def structure_notes_data(notes):
    structured_data = {}
    for note in notes:
        headings = structured_data.setdefault(note['type'], {})
        sub_headings = headings.setdefault(note['heading'], {})
        titles = sub_headings.setdefault(note['sub_heading'], {})
        
        title_key = note['title']
        if title_key not in titles:
            titles[title_key] = {'subtitles': []}

        if not note.get('sub_title'):
            titles[title_key]['main_path'] = note['file_path']
        else:
            titles[title_key]['subtitles'].append({
                'name': note['sub_title'],
                'path': note['file_path']
            })
    return structured_data

@users_bp.route('/open/hnotes/<section_id>/<course_code>/<unique_code>')
@user_login_required
@secure_access_required(('course_code', 'unique_code'))
def open_hnotes_section(section_id, course_code, unique_code):
    email, username, user_is_authenticated = get_user_session()

    if not user_is_authenticated:
        logger.warning("STUDY NOTES: Unauthenticated access blocked")
        flash('Please log in to continue.', 'warning')
        return redirect(url_for('users.user_login', next=request.url))

    section_details = content_op.get_course_section_details(section_id)
    if not section_details:
        abort(404, "Course section not found.")

    section_label = section_details.get('label', 'Free')
    section_title = section_details.get('title', 'Notes Dashboard')

    notes = content_op.get_notes_for_display(section_id)
    logger.info(f"STUDY NOTES: [{email}] opened section {section_id} ({section_label}) in {course_code}")

    structured_data = structure_notes_data(notes)

    return render_template(
        'users/exam_platform/study_materials_platform/notes_dashboard.html', 
        structured_data=structured_data, 
        section_label=section_label,
        section_title=section_title,
        test_id=section_id,
        username=username,
        email=email,
        user_is_authenticated=user_is_authenticated,
        course_code=course_code,
        unique_code=unique_code
    )

@users_bp.route('/view_note_file/<path:filepath>')
def view_note_file(filepath):
    try:
        email, username, user_is_authenticated = get_user_session()

        note = (content_op.get_note_course_and_label(filepath)
                or content_op.get_note_course_and_label('/' + filepath.lstrip('/')))
        label = (note or {}).get('label', 'Paid')
        note_code = (note or {}).get('code')

        if label == 'Paid':
            if not user_is_authenticated:
                flash("Please log in to view this premium file.", "info")
                logger.warning("STUDY NOTES: paid file blocked for unauthenticated user.")
                return redirect(url_for('users.user_login', next=request.url))
            if not note_code or not content_op.get_user_unique_code(email, note_code):
                logger.warning(
                    f"STUDY NOTES: [{email}] denied paid file for course "
                    f"{note_code!r} (not enrolled). path={filepath}")
                abort(403)

        rel = filepath.lstrip('/\\')
        if rel.lower().startswith('static/') or rel.lower().startswith('static\\'):
            rel = rel[len('static/'):]
        static_root = os.path.realpath(current_app.static_folder)
        file_path = os.path.realpath(os.path.join(static_root, rel))
        if os.path.commonpath([static_root, file_path]) != static_root:
            logger.error(f"STUDY NOTES: path traversal blocked: {filepath}")
            abort(404)

        if not os.path.isfile(file_path):
            logger.error(f"STUDY NOTES: file not found: {file_path}")
            abort(404)

        logger.info(f"STUDY NOTES: [{email}] serving file {file_path}")
        return send_file(file_path, as_attachment=False)
    except HTTPException:
        raise
    except Exception:
        logger.exception("STUDY NOTES: error serving note file.")
        abort(500, "An internal server error occurred.")