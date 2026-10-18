import logging
from flask import render_template, request, url_for, flash, session, jsonify
from extensions import admin_login_required, can_manage
from admin.manage_course.enroll_course_db import UserOperation
from admin.manage_catalog.catalog_db import CatalogDB
from admin import admin_bp, taxonomy

logger = logging.getLogger(__name__)

user_op = UserOperation()
catalog_db = CatalogDB()


def _taxonomy_context():
    return {
        'groups': taxonomy.groups(),
        'group_codes': taxonomy.group_codes_map(),
        'catalog_groups': catalog_db.groups(),
        'catalog_codes': catalog_db.codes(),
    }


@admin_bp.route('/courses')
@admin_login_required
def manage_courses():
    try:
        courses = user_op.get_all_courses()
        return render_template('admin/manage_course/enroll_course.html',
                               courses=courses, **_taxonomy_context())
    except Exception as e:
        logger.error(f"Error loading the manage courses page: {e}")
        flash("An unexpected error occurred while loading the page.", "error")
        return render_template('admin/manage_course/enroll_course.html',
                               courses=[], **_taxonomy_context())

@admin_bp.route('/courses/add', methods=['POST'])
@admin_login_required
def add_course():
    if not can_manage():
        logger.warning(f"Unauthorized attempt to add course by {session.get('admin_email')}")
        return jsonify({'status': 'error', 'message': 'You are not authorized to perform this action.'}), 403

    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({'status': 'error', 'message': 'Invalid request body. Expected JSON.'}), 400
        code = (data.get('code') or '').strip()
        name = (data.get('name') or '').strip()
        subgroup = (data.get('subgroup') or '').strip()
        description = (data.get('description') or '').strip()

        if not code or not name or not description:
            return jsonify({'status': 'error', 'message': 'Code, group name and description are required.'}), 400

        if len(code) > 100 or len(name) > 255 or len(subgroup) > 100:
            return jsonify({'status': 'error',
                            'message': 'Code (max 100), group name (max 255) or subgroup (max 100) is too long.'}), 400

        if not taxonomy.is_valid_group(name):
            return jsonify({'status': 'error',
                            'message': f"Group must be one of: {', '.join(taxonomy.groups())}."}), 400
        if not taxonomy.is_valid_pair(name, code):
            allowed = ', '.join(taxonomy.codes_for_group(name))
            return jsonify({'status': 'error',
                            'message': f"Code '{code}' is not valid for {name}. Allowed codes: {allowed}."}), 400

        if user_op.get_course_by_code(code):
            logger.warning(f"Attempt to add duplicate course with code: {code}")
            return jsonify({'status': 'error', 'message': f"A course with code '{code}' already exists."}), 409

        if user_op.insert_course(code, name, description, subgroup):
            logger.info(f"Course '{code}' added by {session.get('admin_email')}")
            return jsonify({
                'status': 'success',
                'message': f"Course '{code}' added.",
                'course': {'code': code, 'name': name, 'subgroup': subgroup, 'description': description}
            }), 201
        else:
            return jsonify({'status': 'error', 'message': 'Failed to add course due to a database error.'}), 500

    except Exception as e:
        logger.error(f"Error adding course: {e}")
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred.'}), 500

@admin_bp.route('/courses/update/<code>', methods=['POST'])
@admin_login_required
def update_course(code):
    if not can_manage():
        logger.warning(f"Unauthorized attempt to update course {code} by {session.get('admin_email')}")
        return jsonify({'status': 'error', 'message': 'You are not authorized to perform this action.'}), 403

    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({'status': 'error', 'message': 'Invalid request body. Expected JSON.'}), 400
        name = (data.get('name') or '').strip()
        subgroup = (data.get('subgroup') or '').strip()
        description = (data.get('description') or '').strip()

        if not name or not description:
            return jsonify({'status': 'error', 'message': 'Group name and description cannot be empty.'}), 400

        if len(name) > 255 or len(subgroup) > 100:
            return jsonify({'status': 'error',
                            'message': 'Group name (max 255) or subgroup (max 100) is too long.'}), 400

        existing_course = user_op.get_course_by_code(code)
        if not existing_course:
            return jsonify({'status': 'error', 'message': 'Course not found.'}), 404

        if not taxonomy.is_valid_group(name):
            return jsonify({'status': 'error',
                            'message': f"Group must be one of: {', '.join(taxonomy.groups())}."}), 400
        if not taxonomy.is_valid_pair(name, code):
            allowed = ', '.join(taxonomy.codes_for_group(name))
            return jsonify({'status': 'error',
                            'message': f"Course code '{code}' does not belong to {name}. "
                                       f"{name} uses: {allowed}."}), 400

        if (existing_course['name'] == name
                and (existing_course.get('subgroup') or '') == subgroup
                and existing_course['description'] == description):
            return jsonify({'status': 'info', 'message': 'No changes were detected.'}), 200

        if user_op.update_course(code, name, description, subgroup):
            logger.info(f"Course '{code}' updated by {session.get('admin_email')}")
            return jsonify({'status': 'success', 'message': f"Course '{code}' updated."})
        else:
            return jsonify({'status': 'error', 'message': 'Failed to update course due to a database error.'}), 500

    except Exception as e:
        logger.error(f"Error updating course {code}: {e}")
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred.'}), 500

def _summary(counts):
    return ', '.join(f"{n} {label}" if label != 'premium page text' else label for label, n in counts.items())


def _blocked_message(code, used):
    return (f"'{code}' still has {_summary(used)}, so it cannot be deleted. "
            f"Remove its content first, and keep the course while any student is enrolled, "
            f"has paid or holds a premium subscription.")


@admin_bp.route('/courses/usage/<code>', methods=['GET'])
@admin_login_required
def course_usage_api(code):
    if not can_manage():
        return jsonify({'status': 'error', 'message': 'You are not authorized to perform this action.'}), 403
    if not user_op.get_course_by_code(code):
        return jsonify({'status': 'error', 'message': 'Course not found. Refresh the page.'}), 404
    used = user_op.course_usage(code)
    extras = user_op.course_extras(code)
    return jsonify({
        'status': 'success',
        'code': code,
        'deletable': not used,
        'blocking': [{'label': label, 'count': n} for label, n in used.items()],
        'removes': [{'label': label, 'count': n} for label, n in extras.items()],
        'message': _blocked_message(code, used) if used else '',
    })


@admin_bp.route('/courses/delete/<code>', methods=['POST'])
@admin_login_required
def delete_course(code):
    if not can_manage():
        logger.warning(f"Unauthorized attempt to delete course {code} by {session.get('admin_email')}")
        return jsonify({'status': 'error', 'message': 'You are not authorized to perform this action.'}), 403

    try:
        result = user_op.delete_course(code)
        state = result.get('status')
        if state == 'missing':
            return jsonify({'status': 'error', 'message': 'Course not found. It may already be deleted.'}), 404
        if state == 'in_use':
            logger.warning(f"DELETE COURSE BLOCKED: '{code}' still has {_summary(result['used'])} "
                           f"(asked by {session.get('admin_email')})")
            return jsonify({'status': 'error', 'message': _blocked_message(code, result['used'])}), 409
        if state != 'deleted':
            return jsonify({'status': 'error', 'message': 'Failed to delete course due to a database error.'}), 500
        removed = result.get('removed') or {}
        logger.info(f"Course '{code}' deleted by {session.get('admin_email')}"
                    + (f" with {_summary(removed)}" if removed else ''))
        message = f"Course '{code}' deleted."
        if removed:
            message += f" Also removed its {_summary(removed)}."
        return jsonify({'status': 'success', 'message': message, 'removed': removed})
    except Exception as e:
        logger.error(f"Error deleting course {code}: {e}")
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred.'}), 500
