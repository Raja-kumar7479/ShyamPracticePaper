import logging
from flask import jsonify, request, session, url_for
from routes import users_bp
from routes.courses_platform.databases.profile_db import ProfileOperation
from routes.courses_platform.dashboard.main_profile.utils_delete_account import (
    send_delete_account_otp,
    verify_delete_account_otp,
    clear_delete_account_otp,
)
from routes.courses_platform.utils.utils_token import csrf_protected
from routes.email_service import render_email, send_email
from extensions import user_login_required, limiter

logger = logging.getLogger(__name__)

profile_op = ProfileOperation()

CONFIRM_PHRASE = 'DELETE'


def _session_user():
    return session.get('user_email'), session.get('user_username')


@users_bp.route('/api/profile/delete/summary', methods=['GET'])
@limiter.limit("20 per hour")
@user_login_required
def api_delete_account_summary():
    email, _ = _session_user()
    if not email:
        return jsonify({"status": "error", "message": "Session expired."}), 401

    counts = profile_op.get_account_footprint(email)
    return jsonify({
        "status": "success",
        "email": email,
        "summary": {
            "enrollments": counts.get('enrollment', 0),
            "purchases": counts.get('purchase', 0),
            "test_attempts": counts.get('user_test_log', 0) + counts.get('comm_user_log', 0),
            "results": counts.get('test_result', 0),
        }
    })


@users_bp.route('/api/profile/delete/send-otp', methods=['POST'])
@limiter.limit("5 per hour")
@user_login_required
@csrf_protected
def api_delete_account_send_otp():
    email, username = _session_user()
    if not email:
        return jsonify({"status": "error", "message": "Session expired. Please log in again."}), 401

    logger.info(f"DELETE OTP 1: code requested by {email}.")

    payload = request.get_json(silent=True) or request.form
    acknowledged = str(payload.get('acknowledge', '')).lower() in ('true', '1', 'on', 'yes')

    if not acknowledged:
        logger.warning(f"DELETE OTP 2: acknowledgement checkbox missing for {email}; blocked.")
        return jsonify({
            "status": "error",
            "message": "Please tick the confirmation box before continuing."
        }), 400

    try:
        ok, message = send_delete_account_otp(email, username)
    except Exception as e:
        logger.error(f"DELETE OTP 3: unexpected error sending code to {email}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Could not send the code. Please try again."}), 500

    if not ok:
        logger.warning(f"DELETE OTP 3: code not sent to {email}: {message}")
        return jsonify({"status": "error", "message": message}), 429

    logger.info(f"DELETE OTP 4: code sent to {email}.")

    masked = email
    if '@' in email:
        name, domain = email.split('@', 1)
        masked = (name[:2] + '*' * max(len(name) - 2, 1)) + '@' + domain

    return jsonify({"status": "success", "message": message, "sent_to": masked})


@users_bp.route('/api/profile/delete/confirm', methods=['POST'])
@limiter.limit("10 per hour")
@user_login_required
@csrf_protected
def api_delete_account_confirm():
    email, username = _session_user()
    if not email:
        return jsonify({"status": "error", "message": "Session expired. Please log in again."}), 401

    logger.info(f"DELETE ROUTE 1: confirmation request received for {email}.")

    payload = request.get_json(silent=True) or request.form
    otp = str(payload.get('otp', '')).strip()
    confirm_text = str(payload.get('confirm_text', '')).strip().upper()
    acknowledged = str(payload.get('acknowledge', '')).lower() in ('true', '1', 'on', 'yes')

    if not acknowledged:
        logger.warning(f"DELETE ROUTE 2: acknowledgement checkbox missing for {email}; blocked.")
        return jsonify({"status": "error", "message": "Please tick the confirmation box before continuing."}), 400

    if confirm_text != CONFIRM_PHRASE:
        logger.warning(f"DELETE ROUTE 3: confirmation phrase mismatch for {email}; blocked.")
        return jsonify({
            "status": "error",
            "message": f"Type {CONFIRM_PHRASE} exactly to confirm."
        }), 400

    if not otp:
        logger.warning(f"DELETE ROUTE 4: no code supplied by {email}; blocked.")
        return jsonify({"status": "error", "message": "Enter the code sent to your email."}), 400

    verified, message = verify_delete_account_otp(email, otp)
    if not verified:
        logger.warning(f"DELETE ROUTE 5: code verification failed for {email}: {message}")
        return jsonify({"status": "error", "message": message}), 400

    logger.critical(f"DELETE ROUTE 6: verified request for {email}. Beginning permanent deletion.")

    try:
        deleted_ok, rows = profile_op.delete_account_completely(email)
    except Exception as e:
        logger.error(f"DELETE ROUTE 7: unexpected error deleting {email}: {e}", exc_info=True)
        deleted_ok, rows = False, {}

    if not deleted_ok:
        logger.error(f"DELETE ROUTE 7: deletion FAILED for {email}. Nothing was removed; code kept so the user can retry.")
        return jsonify({
            "status": "error",
            "message": "We could not complete the deletion. Nothing has been removed. Please try again or contact support."
        }), 500

    clear_delete_account_otp()
    logger.info(f"DELETE ROUTE 8: deletion succeeded for {email}. Rows: {rows}")

    try:
        body = (
            f"<p>Hi {username or 'there'},</p>"
            "<p>Your ShyamPracticePaper account has been <strong>permanently deleted</strong> as you requested.</p>"
            "<p>Your profile, enrollments, purchases, test attempts and results have all been removed from our "
            "systems and cannot be recovered.</p>"
            "<p style='color:#8a7a74;font-size:13px;'>If you did not request this, contact us immediately.</p>"
        )
        send_email("Your account has been deleted", email,
                   render_email("Account deleted", body, preheader="Your account has been removed"))
        logger.info(f"DELETE ROUTE 9: confirmation email sent to {email}.")
    except Exception as e:
        logger.warning(f"DELETE ROUTE 9: could not send confirmation email to {email}: {e}")

    session.clear()
    logger.info(f"DELETE ROUTE 10: session cleared for {email}.")

    logger.critical(f"ACCOUNT DELETION COMPLETE for {email}. Rows removed: {rows}")

    return jsonify({
        "status": "success",
        "message": "Your account and all associated data have been permanently deleted.",
        "redirect_url": url_for('users.index')
    })
