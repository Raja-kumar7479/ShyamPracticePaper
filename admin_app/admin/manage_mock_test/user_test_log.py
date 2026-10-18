import logging
from flask import render_template, request, flash, redirect, url_for, session, jsonify
from admin.manage_mock_test.test_details_db import UserOperation
from extensions import admin_login_required
from admin import admin_bp
import math

logger = logging.getLogger(__name__)

user_op = UserOperation()

@admin_bp.route('/manage_test_logs')
@admin_login_required
def manage_test_logs():
    try:
        admin_email = session.get('admin_email', 'UnknownAdmin')
        logger.info(f"Admin [{admin_email}] accessed user test log page.")
        unique_attempts_count = user_op.count_unique_test_attempts()
        return render_template("admin/manage_mock_test/user_test_log.html", unique_attempts_count=unique_attempts_count)
    except Exception as e:
        logger.exception(f"Admin [{admin_email}] failed to load test logs page.")
        flash("An error occurred while loading the page.", "danger")
        return redirect(url_for('admin.admin_dashboard'))

def _stamp_dates(rows):
    for r in rows:
        for k, v in list(r.items()):
            if hasattr(v, 'strftime'):
                r[k] = v.strftime('%d %b %Y, %I:%M %p')
    return rows


@admin_bp.route('/api/student-logs/courses', methods=['GET'])
@admin_login_required
def student_log_courses():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    try:
        rows = _stamp_dates(user_op.get_student_log_courses())
        totals = user_op.get_student_log_totals()
        logger.info(f"STUDENT LOGS STEP 1: [{admin_email}] {len(rows)} course(s), "
                    f"{totals['unique_students']} unique student(s) overall")
        return jsonify({'courses': rows, 'totals': totals})
    except Exception:
        logger.exception(f"STUDENT LOGS STEP 1 FAILED: [{admin_email}]")
        return jsonify({'error': 'Could not load student counts.'}), 500


@admin_bp.route('/api/student-logs/details', methods=['GET'])
@admin_login_required
def student_log_details():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    course_code = (request.args.get('course_code') or '').strip()
    if not course_code:
        return jsonify({'error': 'Course code is required.'}), 400
    try:
        rows = _stamp_dates(user_op.get_student_log_details(course_code))
        logger.info(f"STUDENT LOGS STEP 2: [{admin_email}] {len(rows)} unique student(s) in {course_code}")
        return jsonify({'students': rows, 'unique_students': len(rows)})
    except Exception:
        logger.exception(f"STUDENT LOGS STEP 2 FAILED: [{admin_email}] course={course_code!r}")
        return jsonify({'error': 'Could not load student details.'}), 500


@admin_bp.route('/get_test_log_data', methods=['GET'])
@admin_login_required
def get_test_log_data():
    try:
        admin_email = session.get('admin_email', 'UnknownAdmin')
        page = request.args.get('page', 1, type=int)
        per_page = 50
        
        logger.info(f"Admin [{admin_email}] fetching user test log data for page {page}.")

        test_logs, total = user_op.get_selected_user_test_logs(page, per_page)
        total_pages = math.ceil(total / per_page)

        return jsonify({
            'test_logs': test_logs,
            'total_pages': total_pages,
            'current_page': page,
            'total_records': total
        })
    except Exception as e:
        logger.exception(f"Admin [{admin_email}] failed to fetch user test log data.")
        return jsonify({'error': 'Failed to fetch data'}), 500

@admin_bp.route('/get_unique_test_attempts_count', methods=['GET'])
@admin_login_required
def get_unique_test_attempts_count():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    try:
        count = user_op.count_unique_test_attempts()
        logger.info(f"Admin [{admin_email}] fetched unique test attempts count: {count}")
        return jsonify({"unique_attempts_count": count})
    except Exception as e:
        logger.exception(f"Admin [{admin_email}] failed to fetch unique test attempts count.")
        return jsonify({"error": "Failed to fetch count"}), 500
