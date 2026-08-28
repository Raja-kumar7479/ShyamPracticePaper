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
import razorpay
from routes.courses_platform.payment.purchased_payment.utils.utils_success import get_session_user

logger = logging.getLogger(__name__)

user_op = UserOperation()

RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID")
RAZORPAY_SECRET = os.environ.get("RAZORPAY_SECRET")

try:
    razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_SECRET))
except Exception as e:
    logger.critical(f"Razorpay Client init failed: {e}")
    razorpay_client = None

_MAX_ENROLLMENTS   = 10
_FREE_TIER_LIMIT   = 3
_MAX_CAPTCHA_TRIES = 5
PLATFORM_FEE       = float(os.environ.get('PLATFORM_FEE', '99'))
_COURSE_CODE_RE    = re.compile(r'^[A-Z0-9_-]{2,20}$')


def _get_active_enrollments(email):
    rows = user_op.get_enrolled_courses(email)
    return [r for r in rows if r.get('payment_status') in ('Paid', 'FREE')]


def _verify_payment_intent(pending, email):
    if not pending or not email:
        return False
    if not pending.get('course_code') or not pending.get('razorpay_order_id'):
        return False
    if pending.get('locked_email') != email:
        return False
    return True


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

        if count >= _MAX_ENROLLMENTS:
            return jsonify({"status": "limit_reached", "limit": _MAX_ENROLLMENTS})

        if count < _FREE_TIER_LIMIT:
            return jsonify({
                "status":           "continue",
                "payment_required": False,
                "enrollment_count": count,
                "message":          ""
            })

        price            = PLATFORM_FEE
        payment_required = True
        message = f"You already have {count} courses. A one-time platform fee of ₹{price:.2f} applies to this enrollment."
        return jsonify({
            "status":           "continue",
            "payment_required": payment_required,
            "price":            price,
            "enrollment_count": count,
            "message":          message
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

        if count >= _MAX_ENROLLMENTS:
            return jsonify({"success": False, "error": f"Enrollment limit of {_MAX_ENROLLMENTS} reached."})

        payment_required = count >= _FREE_TIER_LIMIT
        final_price      = PLATFORM_FEE if payment_required else 0.00

        if not payment_required:
            unique_code   = generate_secure_code(email, course_code, captcha_input)
            payment_id    = f"FREE_{uuid.uuid4().hex[:10].upper()}_{course_code}"
            enrollment_id = user_op.enroll_user(email, course_code, course_name, unique_code, payment_id)

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
            logger.info(f"FREE enrollment: {email} -> {course_code} (count was {count})")
            return jsonify({"success": True, "redirect_url": redirect_url, "payment_required": False})

        session['pending_enrollment'] = {
            'course_code':       course_code,
            'course_name':       course_name,
            'captcha':           captcha_input,
            'locked_email':      email,
            'locked_count':      count,
            'razorpay_order_id': None,
            'server_amount':     None,
            'server_price':      None,
        }
        session.modified = True
        logger.info(f"Pre-check passed: {email} -> {course_code} @ ₹{final_price:.2f} (count={count})")
        return jsonify({"success": True, "payment_required": True, "price": final_price})

    except Exception as e:
        logger.error(f"complete_enrollment_pre_check error: {e}")
        return jsonify({"success": False, "error": "Server error. Please try again."}), 500


@users_bp.route('/api/enrollment/payment/create_order', methods=['POST'])
@limiter.limit("10 per minute")
@user_login_required
@csrf_protected
def create_enrollment_order():
    username, email, phone = get_session_user()
    pending = session.get('pending_enrollment')

    if not email or not username:
        return jsonify({"error": "Session expired."}), 401

    if not pending or pending.get('locked_email') != email or not pending.get('course_code'):
        logger.warning(f"create_order: bad pending_enrollment for {email}")
        return jsonify({"error": "Invalid session. Please restart enrollment."}), 400

    if not razorpay_client:
        return jsonify({"error": "Payment system unavailable."}), 503

    course_code = _sanitize_course_code(pending.get('course_code', ''))
    if not course_code:
        return jsonify({"error": "Invalid course code in session."}), 400

    active = _get_active_enrollments(email)
    count  = len(active)

    if any(r['code'] == course_code for r in active):
        session.pop('pending_enrollment', None)
        return jsonify({"error": "Already enrolled in this course."}), 400

    if count >= _MAX_ENROLLMENTS:
        session.pop('pending_enrollment', None)
        return jsonify({"error": f"Enrollment limit of {_MAX_ENROLLMENTS} reached."}), 400

    if count < _FREE_TIER_LIMIT:
        session.pop('pending_enrollment', None)
        logger.warning(f"SECURITY: create_order called for free-tier user {email} (count={count})")
        return jsonify({"error": "This enrollment is free — no payment required."}), 400

    price = PLATFORM_FEE
    amount_in_paise = int(round(price * 100))
    receipt_id      = f"ENR_{uuid.uuid4().hex[:12].upper()}_{course_code}"

    try:
        razorpay_order = razorpay_client.order.create({
            'amount':          amount_in_paise,
            'currency':        'INR',
            'receipt':         receipt_id,
            'payment_capture': 1,
            'notes':           {'course_code': course_code, 'email': email}
        })
    except Exception as e:
        logger.error(f"Razorpay order creation failed for {email}: {e}")
        return jsonify({"error": "Payment gateway error. Please try again."}), 500

    pending['razorpay_order_id'] = razorpay_order['id']
    pending['server_amount']     = amount_in_paise
    pending['server_price']      = price
    session['pending_enrollment'] = pending
    session.modified = True

    logger.info(f"Order {razorpay_order['id']} created: {email} -> {course_code} @ ₹{price:.2f}")
    return jsonify({
        "status":            "success",
        "razorpay_order_id": razorpay_order['id'],
        "razorpay_key_id":   RAZORPAY_KEY_ID,
        "amount":            amount_in_paise,
        "username":          username,
        "email":             email,
        "phone":             phone or '',
        "course_code":       course_code,
    })


@users_bp.route('/api/enrollment/payment/success', methods=['POST'])
@limiter.limit("15 per minute")
@user_login_required
@csrf_protected
def enrollment_payment_success():
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"success": False, "error": "Invalid request."}), 400

        rzp_payment_id = (data.get('razorpay_payment_id') or '').strip()
        rzp_order_id   = (data.get('razorpay_order_id')   or '').strip()
        rzp_signature  = (data.get('razorpay_signature')  or '').strip()

        if not all([rzp_payment_id, rzp_order_id, rzp_signature]):
            return jsonify({"success": False, "error": "Incomplete payment details."}), 400

        email   = session.get('user_email')
        pending = session.get('pending_enrollment')

        if not _verify_payment_intent(pending, email):
            logger.warning(f"payment_success: Invalid intent for email={email}")
            return jsonify({"success": False, "error": "Session mismatch. Contact support with your payment ID."}), 400

        if pending.get('razorpay_order_id') != rzp_order_id:
            logger.critical(f"SECURITY: Order ID mismatch. Expected={pending.get('razorpay_order_id')} Got={rzp_order_id} email={email}")
            session.pop('pending_enrollment', None)
            return jsonify({"success": False, "error": "Order ID mismatch. Possible tampering detected."}), 400

        if not razorpay_client:
            return jsonify({"success": False, "error": "Payment system unavailable."}), 503

        try:
            razorpay_client.utility.verify_payment_signature({
                'razorpay_order_id':   rzp_order_id,
                'razorpay_payment_id': rzp_payment_id,
                'razorpay_signature':  rzp_signature
            })
        except Exception:
            logger.warning(f"SECURITY: Signature FAILED order={rzp_order_id} email={email}")
            return jsonify({"success": False, "error": "Payment signature invalid. Contact support."}), 400

        try:
            payment_details = razorpay_client.payment.fetch(rzp_payment_id)
        except Exception as e:
            logger.error(f"Could not fetch payment {rzp_payment_id} from Razorpay: {e}")
            return jsonify({"success": False, "error": "Could not confirm payment. Contact support."}), 502

        if payment_details.get('order_id') != rzp_order_id:
            logger.critical(f"SECURITY: payment/order mismatch. payment={rzp_payment_id} order={rzp_order_id} email={email}")
            return jsonify({"success": False, "error": "Payment verification failed. Contact support."}), 400

        if payment_details.get('status') != 'captured':
            logger.warning(f"Payment {rzp_payment_id} not captured (status={payment_details.get('status')}) email={email}")
            return jsonify({"success": False, "error": "Payment not completed. Contact support if money was deducted."}), 400

        if int(payment_details.get('amount', 0)) != int(pending.get('server_amount') or 0):
            logger.critical(f"SECURITY: paid amount mismatch. paid={payment_details.get('amount')} expected={pending.get('server_amount')} email={email}")
            return jsonify({"success": False, "error": "Payment amount mismatch. Contact support."}), 400

        course_code = _sanitize_course_code(pending.get('course_code', ''))
        course_name = (pending.get('course_name') or '').strip()
        captcha_val = pending.get('captcha', 'SECURE')
        username    = session.get('user_username') or email

        if not course_code or not course_name:
            return jsonify({"success": False, "error": "Corrupt session data. Contact support."}), 400

        active = _get_active_enrollments(email)
        count  = len(active)

        existing_code = user_op.get_user_unique_code(email, course_code)
        if existing_code:
            session.pop('pending_enrollment', None)
            redirect_url = url_for('users.view_course_dashboard', course_code=course_code, unique_code=existing_code)
            logger.info(f"payment_success: Idempotent re-entry for {email} -> {course_code}")
            return jsonify({"success": True, "redirect_url": redirect_url})

        if count < _FREE_TIER_LIMIT:
            logger.critical(f"SECURITY: payment_success for free-tier user {email} (count={count}). BLOCKED.")
            session.pop('pending_enrollment', None)
            return jsonify({"success": False, "error": "Unexpected payment for free tier."}), 400

        if count >= _MAX_ENROLLMENTS:
            session.pop('pending_enrollment', None)
            return jsonify({"success": False, "error": "Enrollment limit reached."}), 400

        price         = PLATFORM_FEE
        server_amount = pending.get('server_amount', 0)
        expected_amount = int(round(PLATFORM_FEE * 100))

        if server_amount != expected_amount:
            logger.critical(f"SECURITY: Amount tamper detected. expected={expected_amount} Session={server_amount} email={email}")
            session.pop('pending_enrollment', None)
            return jsonify({"success": False, "error": "Payment amount mismatch. Contact support."}), 400

        final_unique_code = generate_secure_code(email, course_code, captcha_val)
        enrollment_id     = user_op.enroll_user(email, course_code, course_name, final_unique_code, rzp_payment_id)

        if not enrollment_id:
            logger.error(f"payment_success: DB insert failed for {email} payment={rzp_payment_id}")
            return jsonify({
                "success": False,
                "error":   f"Enrollment save failed. Contact support with payment ID: {rzp_payment_id}"
            }), 500

        logged = user_op.log_enrollment_payment(
            enrollment_id=enrollment_id,
            email=email,
            username=username,
            course_code=course_code,
            amount_paid=price,
            payment_id=rzp_payment_id,
            razorpay_order_id=rzp_order_id,
            payment_method='Razorpay',
            payment_status='Paid'
        )

        if not logged:
            logger.critical(
                f"RECONCILE MANUALLY: payment captured but enrollment_payment insert failed. "
                f"email={email} course={course_code} razorpay_payment_id={rzp_payment_id} "
                f"order={rzp_order_id} amount={price:.2f} enrollment_id={enrollment_id}"
            )

        session.pop('pending_enrollment', None)
        try:
            send_enrollment_email(
                email, username, course_name, final_unique_code,
                url_for('users.view_course_dashboard', course_code=course_code, unique_code=final_unique_code, _external=True),
                paid=True, amount=f"{price:.2f}"
            )
        except Exception as mail_err:
            logger.warning(f"Paid enrollment email failed for {email}: {mail_err}")
        logger.info(f"PAID enrollment: {email} -> {course_code} @ ₹{price:.2f} payment={rzp_payment_id}")
        redirect_url = url_for('users.view_course_dashboard', course_code=course_code, unique_code=final_unique_code)
        return jsonify({"success": True, "redirect_url": redirect_url})

    except Exception as e:
        logger.error(f"enrollment_payment_success unhandled: {e}")
        return jsonify({"success": False, "error": "Server error. Please contact support."}), 500


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