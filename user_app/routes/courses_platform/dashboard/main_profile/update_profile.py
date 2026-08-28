import re
from flask import jsonify, request, session
from routes.courses_platform.databases.profile_db import ProfileOperation
from extensions import user_login_required, limiter
from routes.courses_platform.utils.utils_token import csrf_protected
import logging
from routes import users_bp
import bcrypt
from routes.auth.utils.utils_login import verify_password
from routes.auth.utils.utils_signup import is_password_secure

profile_op = ProfileOperation()

logger = logging.getLogger(__name__)

USERNAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 ._-]{1,28}[A-Za-z0-9]$')


@users_bp.route('/api/profile/check-username', methods=['POST'])
@limiter.limit("30 per minute")
@user_login_required
@csrf_protected
def api_check_username():
    email = session.get('user_email')
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()

    if len(username) < 3:
        return jsonify({"status": "invalid", "message": "Too short"})

    if not USERNAME_RE.match(username):
        return jsonify({"status": "invalid", "message": "Only letters, numbers, spaces, dots, dashes (3-30 chars)."})
    
    is_taken = profile_op.is_username_taken(username, exclude_email=email)
    
    if is_taken:
        return jsonify({"status": "taken", "message": "Username is taken"})
    else:
        return jsonify({"status": "available", "message": "Username is available"})

@users_bp.route('/api/profile/last-active', methods=['GET'])
@user_login_required
def api_get_last_active():
    email = session.get('user_email')
    last_active = profile_op.get_last_active_time(email)
    return jsonify({"last_active": last_active})


@users_bp.route('/api/profile/update-username', methods=['POST'])
@limiter.limit("10 per minute")
@user_login_required
@csrf_protected
def api_profile_update_username():
    email = session.get('user_email')
    new_username = request.form.get('username', '').strip()

    if not new_username or len(new_username) < 3:
        return jsonify({"status": "error", "message": "Username must be at least 3 characters."})

    if not USERNAME_RE.match(new_username):
        return jsonify({"status": "error", "message": "Only letters, numbers, spaces, dots, dashes (3-30 chars)."})

    if profile_op.is_username_taken(new_username, exclude_email=email):
        return jsonify({"status": "error", "message": "Username is already taken."})

    try:
        profile_op.update_username(email, new_username)
        session['user_username'] = new_username 
        return jsonify({"status": "success", "message": "Username updated successfully!", "new_username": new_username})
    except Exception as e:
        logger.error(f"Error updating username for {email}: {e}")
        return jsonify({"status": "error", "message": "An error occurred."})

@users_bp.route('/api/profile/change-password', methods=['POST'])
@limiter.limit("5 per minute")
@user_login_required
@csrf_protected
def api_profile_update_password():
    email = session.get('user_email')
    current_pass = request.form.get('current_password')
    new_pass = request.form.get('new_password')
    confirm_pass = request.form.get('confirm_password')

    if not current_pass or not new_pass or not confirm_pass:
        return jsonify({"status": "error", "message": "All password fields are required."})

    user = profile_op.get_user_by_email(email)
    if not user or not user.get('password'):
        return jsonify({"status": "error", "message": "No password set for this account."})
    
    if not verify_password(current_pass, user['password']):
        return jsonify({"status": "error", "message": "Incorrect current password."})

    if new_pass != confirm_pass:
        return jsonify({"status": "error", "message": "New passwords do not match."})

    if not is_password_secure(new_pass):
        return jsonify({"status": "error", "message": "Password must be 8+ chars, 1 uppercase, 1 digit, 1 special char."})

    try:
        hashed_pw = bcrypt.hashpw(new_pass.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        profile_op.update_user_password(email, hashed_pw)
        return jsonify({"status": "success", "message": "Password updated successfully!"})
    except Exception as e:
        logger.error(f"Error updating password for {email}: {e}")
        return jsonify({"status": "error", "message": "Server error. Please try again."})

@users_bp.route('/api/profile/set-password', methods=['POST'])
@limiter.limit("5 per minute")
@user_login_required
@csrf_protected
def api_profile_set_password():
    email = session.get('user_email')
    new_pass = request.form.get('new_password')
    confirm_pass = request.form.get('confirm_password')

    if not new_pass or not confirm_pass:
        return jsonify({"status": "error", "message": "All fields are required."})

    user = profile_op.get_user_by_email(email)
    if user and user.get('password'):
        return jsonify({"status": "error", "message": "Password already exists."})

    if new_pass != confirm_pass:
        return jsonify({"status": "error", "message": "Passwords do not match."})

    if not is_password_secure(new_pass):
        return jsonify({"status": "error", "message": "Password not secure enough."})

    try:
        hashed_pw = bcrypt.hashpw(new_pass.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        profile_op.set_user_password(email, hashed_pw)
        return jsonify({"status": "success", "message": "Password set successfully!", "reload": True})
    except Exception as e:
        logger.error(f"Error setting password for {email}: {e}")
        return jsonify({"status": "error", "message": "Server error."})