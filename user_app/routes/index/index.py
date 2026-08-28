from flask import flash, jsonify, redirect, render_template, request, session, url_for, make_response
from routes.index.databases.index_handler_db import UserOperation as EnrollUserOperation
from routes.auth.database.auth_db import AuthOperation
from routes.index.utils.utils_index import get_user_session, generate_csrf_token, csrf_protected
from extensions import limiter
from routes import users_bp
import logging
import json
import os
import datetime
from urllib.parse import quote

enroll_user_op = EnrollUserOperation()
auth_op = AuthOperation()

logger = logging.getLogger(__name__)

@users_bp.route('/', methods=['GET'])
def index():
    try:
        group_names_result = enroll_user_op.get_course_groups()
        group_names = [row['name'] for row in group_names_result]
    except Exception as e:
        logger.error(f"Error fetching course groups for index: {e}")
        group_names = []

    user_email, user_username, user_is_authenticated = get_user_session()
    csrf_token = generate_csrf_token()

    db_consent = None
    if user_is_authenticated and user_email:
        db_consent = auth_op.get_cookie_consent(user_email)

    return render_template(
        'users/index/index.html',  
        group_names=group_names,
        username=user_username,
        email=user_email,
        logged_in=user_is_authenticated,
        csrf_token=csrf_token,
        db_consent=db_consent
    )

def _enrich_courses(courses, user_email, user_is_authenticated):
    enrolled_courses_dict = {}
    if user_is_authenticated:
        enrolled_courses_data = enroll_user_op.get_enrolled_courses(user_email)
        enrolled_courses_dict = {
            course['code']: {
                'unique_code': course['unique_code'],
                'payment_status': course.get('payment_status')
            }
            for course in enrolled_courses_data
            if course.get('payment_status') in ('Paid', 'FREE')
        }
    for course in courses:
        enrollment_data = enrolled_courses_dict.get(course['code'])
        if enrollment_data:
            course['is_enrolled'] = True
            course['unique_code'] = enrollment_data['unique_code']
            course['is_purchased_content'] = enrollment_data['payment_status'] == 'Paid'
        else:
            course['is_enrolled'] = False
            course['is_purchased_content'] = False
    return courses


def _user_consent(user_email, user_is_authenticated):
    if user_is_authenticated and user_email:
        try:
            return auth_op.get_cookie_consent(user_email)
        except Exception:
            return None
    return None


@users_bp.route('/courses', methods=['GET'])
def browse_courses():
    user_email, user_username, user_is_authenticated = get_user_session()
    try:
        groups = enroll_user_op.get_groups_with_counts()
    except Exception as e:
        logger.error(f"browse_courses error: {e}")
        groups = []
    return render_template(
        'users/courses_platform/enrollment/browse.html',
        level='groups', groups=groups, group_name=None, subgroup=None,
        subgroups=[], courses=[],
        username=user_username, email=user_email,
        logged_in=user_is_authenticated, csrf_token=generate_csrf_token(),
        db_consent=_user_consent(user_email, user_is_authenticated)
    )


def _split_group_layout(all_courses):
    buckets = {}
    direct = []
    for course in all_courses:
        sub = (course.get('subgroup') or '').strip()
        if sub:
            buckets.setdefault(sub, []).append(course)
        else:
            direct.append(course)

    subgroups = []
    inline = []
    for sub in sorted(buckets, key=lambda s: s.lower()):
        items = buckets[sub]
        if len(items) > 1:
            subgroups.append({'subgroup': sub, 'course_count': len(items)})
        else:
            inline.extend(items)
    return subgroups, direct + inline


@users_bp.route('/courses/<group_name>', methods=['GET'])
def browse_group(group_name):
    user_email, user_username, user_is_authenticated = get_user_session()
    sub = (request.args.get('sub') or '').strip()
    try:
        if sub:
            subgroups = []
            courses = enroll_user_op.get_courses_by_group(group_name, sub)
        else:
            subgroups, courses = _split_group_layout(
                enroll_user_op.get_courses_in_group(group_name)
            )
        courses = _enrich_courses(courses, user_email, user_is_authenticated)
    except Exception as e:
        logger.error(f"browse_group error for {group_name}: {e}")
        subgroups, courses = [], []
    return render_template(
        'users/courses_platform/enrollment/browse.html',
        level='courses' if sub else 'group',
        groups=[], group_name=group_name, subgroup=sub or None,
        subgroups=subgroups, courses=courses,
        username=user_username, email=user_email,
        logged_in=user_is_authenticated, csrf_token=generate_csrf_token(),
        db_consent=_user_consent(user_email, user_is_authenticated)
    )


@users_bp.route('/api/courses/by-group/<group_name>', methods=['GET'])
def api_get_courses_by_group(group_name):
    user_email, _, user_is_authenticated = get_user_session()
    try:
        subgroups, courses = _split_group_layout(
            enroll_user_op.get_courses_in_group(group_name)
        )
        courses = _enrich_courses(courses, user_email, user_is_authenticated)
        return jsonify({
            "success": True,
            "subgroups": subgroups,
            "has_subgroups": len(subgroups) > 0,
            "courses": courses,
            "is_authenticated": user_is_authenticated
        })
    except Exception as e:
        logger.error(f"API Error fetching courses for {group_name}: {e}")
        return jsonify({"success": False, "error": "Could not load courses."}), 500


@users_bp.route('/api/courses/by-subgroup/<group_name>/<subgroup>', methods=['GET'])
def api_get_courses_by_subgroup(group_name, subgroup):
    user_email, _, user_is_authenticated = get_user_session()
    try:
        courses = _enrich_courses(
            enroll_user_op.get_courses_by_group(group_name, subgroup),
            user_email, user_is_authenticated
        )
        return jsonify({
            "success": True,
            "courses": courses,
            "is_authenticated": user_is_authenticated
        })
    except Exception as e:
        logger.error(f"API Error fetching courses for {group_name}/{subgroup}: {e}")
        return jsonify({"success": False, "error": "Could not load courses."}), 500

@users_bp.route('/api/cookie-consent', methods=['POST'])
@limiter.limit("10 per minute")
@csrf_protected
def api_cookie_consent():
    try:
        data = request.get_json(silent=True) or {}
        consent_data = {
            'necessary': True,
            'analytics': bool(data.get('analytics', False)),
            'marketing': bool(data.get('marketing', False)),
            'timestamp': datetime.datetime.now().isoformat()
        }

        user_email = session.get('user_email')
        if user_email:
            auth_op.update_cookie_consent(user_email, consent_data)

        resp = make_response(jsonify({'status': 'success', 'message': 'Preferences saved', 'consent': consent_data}))

        one_year_seconds = 365 * 24 * 60 * 60
        is_secure = bool(os.environ.get('RENDER') or os.environ.get('GUNICORN_CMD_ARGS'))

        resp.set_cookie(
            'cookie_consent',
            quote(json.dumps(consent_data)),
            max_age=one_year_seconds,
            secure=is_secure,
            httponly=False,
            samesite='Lax'
        )

        return resp
    except Exception as e:
        logger.error(f"Cookie Consent Error: {e}")
        return jsonify({'status': 'error', 'message': 'Failed to save preferences'}), 500