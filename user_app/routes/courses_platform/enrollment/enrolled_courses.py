import uuid
import logging
import os
import hmac
import hashlib
import re
from flask import jsonify, redirect, request, session, url_for
from routes.courses_platform.databases.enrollment_db import UserOperation
from routes.courses_platform.utils.utils_token import generate_secure_code, csrf_protected
from extensions import user_login_required, limiter
from routes import users_bp
from routes.email_service import send_enrollment_email
from routes.courses_platform.payment.purchased_payment.utils.utils_success import get_session_user

logger = logging.getLogger(__name__)

user_op = UserOperation()

_DEFAULT_MAX_ENROLLMENTS = max(1, int(os.environ.get('MAX_ENROLLMENTS', '3')))


def _enrollment_cap():
    try:
        value = user_op.get_platform_setting('max_enrollments')
        if value is not None:
            return max(1, int(value))
    except Exception:
        logger.exception("Could not read the enrollment cap; using the default")
    return _DEFAULT_MAX_ENROLLMENTS
_MAX_CAPTCHA_TRIES = 5
_COURSE_CODE_RE    = re.compile(r'^[A-Z0-9_-]{2,20}$')


def _get_active_enrollments(email):
    rows = user_op.get_enrolled_courses(email)
    return [r for r in rows if r.get('payment_status') in ('Paid', 'FREE')]


def _sanitize_course_code(raw):
    code = (raw or '').strip().upper()
    if not _COURSE_CODE_RE.match(code):
        return None
    return code


def _track_captcha_attempts(email):
    key   = f'captcha_fails_{email}'
    count = session.get(key, 0) + 1
    session[key] = count
    session.modified = True
    return count


def _reset_captcha_attempts(email):
    session.pop(f'captcha_fails_{email}', None)
    session.modified = True


@users_bp.route('/api/enrollment/start', methods=['GET'])
@user_login_required
def start_enrollment_captcha():
    try:
        email = session.get('user_email', '')
        if session.get(f'captcha_fails_{email}', 0) >= _MAX_CAPTCHA_TRIES:
            logger.warning(f"CAPTCHA: Rate limit hit for {email}")
            return jsonify({"error": "Too many failed attempts. Please log out and back in."}), 429

        session.pop('captcha_value', None)
        captcha = str(uuid.uuid4())[:6].upper()
        session['captcha_value'] = captcha
        session.modified = True
        return jsonify({"captcha": captcha})
    except Exception as e:
        logger.error(f"start_enrollment_captcha error: {e}")
        return jsonify({"error": "Failed to generate CAPTCHA."}), 500


@users_bp.route('/api/courses/explore-preview', methods=['POST'])
@csrf_protected
def explore_course_preview():
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"status": "error", "message": "Invalid request."}), 400

        course_code = _sanitize_course_code(data.get('course_code', ''))
        if not course_code:
            return jsonify({"status": "error", "message": "Invalid course code."}), 400

        unique_code = user_op.get_guest_access_code(course_code)
        if not unique_code:
            return jsonify({"status": "error", "message": "Preview not available for this course."}), 404

        redirect_url = url_for('users.view_course_dashboard', course_code=course_code, unique_code=unique_code)
        return jsonify({"status": "success", "redirect_url": redirect_url})
    except Exception as e:
        logger.error(f"explore_course_preview error: {e}")
        return jsonify({"status": "error", "message": "Internal Server Error"}), 500


@users_bp.route('/api/enrollment/check', methods=['GET'])
@user_login_required
def check_enrollment_status():
    email = session.get('user_email')
    if not email:
        return jsonify({"error": "Session expired."}), 403

    course_code = _sanitize_course_code(request.args.get('course_code', ''))
    if not course_code:
        return jsonify({"error": "Invalid course code."}), 400

    try:
        active = _get_active_enrollments(email)
        count  = len(active)

        if any(r['code'] == course_code for r in active):
            return jsonify({"status": "already_enrolled"})

        if count >= _enrollment_cap():
            return jsonify({"status": "limit_reached", "limit": _enrollment_cap()})

        return jsonify({
            "status":           "continue",
            "payment_required": False,
            "enrollment_count": count,
            "limit":            _enrollment_cap(),
            "message":          ""
        })
    except Exception as e:
        logger.error(f"check_enrollment_status error for {email}: {e}")
        return jsonify({"error": "Internal Server Error"}), 500


@users_bp.route('/api/enrollment/complete/pre-check', methods=['POST'])
@user_login_required
@csrf_protected
def complete_enrollment_pre_check():
    try:
        username, email, _ = get_session_user()
        if not email:
            return jsonify({"success": False, "error": "Session expired."}), 403

        if session.get(f'captcha_fails_{email}', 0) >= _MAX_CAPTCHA_TRIES:
            return jsonify({"success": False, "error": "Too many failed attempts. Please log out and back in."}), 429

        course_code   = _sanitize_course_code(request.form.get('course_code', ''))
        course_name   = (request.form.get('course_name', '') or '').strip()
        captcha_input = (request.form.get('captcha', '') or '').strip().upper()
        captcha_value = (session.get('captcha_value') or '').strip().upper()

        if not course_code:
            return jsonify({"success": False, "error": "Invalid course code."}), 400
        if not course_name:
            return jsonify({"success": False, "error": "Missing course name."}), 400
        if not captcha_input or not captcha_value:
            return jsonify({"success": False, "error": "CAPTCHA expired. Refresh and try again."}), 400

        if not hmac.compare_digest(captcha_input, captcha_value):
            fails     = _track_captcha_attempts(email)
            session.pop('captcha_value', None)
            remaining = _MAX_CAPTCHA_TRIES - fails
            if remaining <= 0:
                logger.warning(f"CAPTCHA: Max attempts reached for {email}")
                return jsonify({"success": False, "error": "Too many failed attempts. Please log out and try again."}), 429

            new_captcha = str(uuid.uuid4())[:6].upper()
            session['captcha_value'] = new_captcha
            session.modified = True
            return jsonify({
                "success":     False,
                "error":       f"Incorrect CAPTCHA. {remaining} attempt(s) remaining.",
                "new_captcha": new_captcha
            }), 400

        session.pop('captcha_value', None)
        _reset_captcha_attempts(email)

        active = _get_active_enrollments(email)
        codes  = [r['code'] for r in active]
        count  = len(codes)

        if course_code in codes:
            unique_code  = user_op.get_user_unique_code(email, course_code)
            redirect_url = url_for('users.view_course_dashboard', course_code=course_code, unique_code=unique_code) if unique_code else None
            return jsonify({"success": False, "error": "You are already enrolled in this course.", "redirect_url": redirect_url})

        if count >= _enrollment_cap():
            logger.warning(f"ENROLL BLOCKED: [{email}] already at {count}/{_enrollment_cap()}, tried {course_code}")
            return jsonify({"success": False, "error": f"You can enroll in up to {_enrollment_cap()} courses."})

        unique_code   = generate_secure_code(email, course_code, captcha_input)
        payment_id    = f"FREE_{uuid.uuid4().hex[:10].upper()}_{course_code}"
        enrollment_id = user_op.enroll_user(email, course_code, course_name, unique_code, payment_id,
                                            max_enrollments=_enrollment_cap())

        if enrollment_id == 'limit_reached':
            logger.warning(f"ENROLL BLOCKED AT DB: [{email}] at {_enrollment_cap()}, tried {course_code}")
            return jsonify({"success": False, "error": f"You can enroll in up to {_enrollment_cap()} courses."})

        if not enrollment_id:
            logger.error(f"enroll_user DB failed for {email} -> {course_code}")
            return jsonify({"success": False, "error": "Enrollment failed. Please try again."}), 500

        logged = user_op.log_enrollment_payment(
            enrollment_id=enrollment_id,
            email=email,
            username=username,
            course_code=course_code,
            amount_paid=0.00,
            payment_id=payment_id,
            razorpay_order_id=None,
            payment_method='FREE',
            payment_status='FREE'
        )

        if not logged:
            logger.critical(
                f"ENROLLMENT ROLLBACK: payment log failed for {email} -> {course_code} "
                f"(enrollment_id={enrollment_id}). Removing orphan enrollment."
            )
            user_op.delete_enrollment(enrollment_id)
            return jsonify({"success": False, "error": "Enrollment could not be completed. Please try again."}), 500

        redirect_url = url_for('users.view_course_dashboard', course_code=course_code, unique_code=unique_code)
        try:
            send_enrollment_email(
                email, username, course_name, unique_code,
                url_for('users.view_course_dashboard', course_code=course_code, unique_code=unique_code, _external=True),
                paid=False
            )
        except Exception as mail_err:
            logger.warning(f"Enrollment email failed for {email}: {mail_err}")
        logger.info(f"ENROLLED: {email} -> {course_code} ({count + 1}/{_enrollment_cap()})")
        return jsonify({"success": True, "redirect_url": redirect_url, "payment_required": False})

    except Exception as e:
        logger.error(f"complete_enrollment_pre_check error: {e}")
        return jsonify({"success": False, "error": "Server error. Please try again."}), 500


@users_bp.route('/api/courses/get-code', methods=['GET'])
@user_login_required
def get_enrolled_course_code():
    email       = session.get('user_email')
    course_code = _sanitize_course_code(request.args.get('course_code', ''))

    if not email or not course_code:
        return jsonify({"status": "error", "message": "Invalid request."}), 400

    try:
        unique_code = user_op.get_user_unique_code(email, course_code)
        if unique_code:
            redirect_url = url_for('users.view_course_dashboard', course_code=course_code, unique_code=unique_code)
            return jsonify({"status": "success", "redirect_url": redirect_url})
        return jsonify({"status": "error", "message": "Enrollment not found."}), 404
    except Exception as e:
        logger.error(f"get_enrolled_course_code error for {email}: {e}")
        return jsonify({"status": "error", "message": "Server Error"}), 500