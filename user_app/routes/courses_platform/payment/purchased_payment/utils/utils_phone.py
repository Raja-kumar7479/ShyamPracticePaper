import logging
from flask import flash, redirect, request, session, url_for
from routes import users_bp
from extensions import user_login_required
from routes.courses_platform.utils.utils_token import csrf_protected

logger = logging.getLogger(__name__)

def validate_phone_number(phone_number):
    phone_number = phone_number.strip()
    if not phone_number.isdigit() or len(phone_number) != 10 or phone_number[0] == '0':
        return False, "Invalid phone number. Please enter a valid 10-digit number starting from 1-9."
    return True, None

@users_bp.route('/validate_phone/<course_code>/<unique_code>', methods=['POST'])
@user_login_required
@csrf_protected
def validate_phone(course_code, unique_code):
    user_username = session.get('user_username')
    user_email = session.get('user_email')
    if not user_username or not user_email:
        flash("Login first.", "login")
        logger.warning("Phone validation attempt failed: user not logged in.")
        return redirect(url_for('users.user_login'))

    phone = request.form.get('phone_number', '').strip()
    valid, error = validate_phone_number(phone)
    if not valid:
        flash(error, "cart_warning")
        logger.warning(f"Phone validation failed for user {user_email}: {error}")
        return redirect(url_for('users.add_cart', course_code=course_code, unique_code=unique_code))

    session['validated_phone'] = phone
    flash("Phone number validated. Fill billing details.", "cart_notification")
    logger.info(f"Phone number validated for user {user_email}.")
    return redirect(url_for('users.add_cart', course_code=course_code, unique_code=unique_code, show_billing='true'))