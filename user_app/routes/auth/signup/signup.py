from flask import render_template, request, redirect, url_for, flash, session, jsonify
from flask_mail import Mail
from extensions import limiter
from routes.auth.utils.utils_signup import (
    clear_signup_session, is_valid_email, is_password_secure,
    generate_otp, validate_otp, send_signup_email_otp, send_signup_success_email,
    get_pending_signup, save_pending_signup
)
from routes.auth.database.auth_db import AuthOperation
from routes.auth.utils.utils_login import is_safe_url, safe_next_url
import time
import bcrypt
from routes.auth.utils.utils_login import hash_password, verify_password
import logging
from routes import users_bp
from routes.exam_platform.competitive_exam_platform.utils.utils_test_dashboard import establish_user_session

mail = Mail()
auth_db = AuthOperation()
logger = logging.getLogger(__name__)

@users_bp.route("/api/auth/check-username", methods=['POST'])
def api_auth_check_username():
    data = request.get_json()
    username = data.get('username', '').strip()
    
    if len(username) < 3:
        return jsonify({"status": "invalid", "message": "Username must be at least 3 characters"})
    
    if auth_db.is_username_taken(username):
        return jsonify({"status": "taken", "message": "Username is already taken"})
    
    return jsonify({"status": "available", "message": "Username is available"})

@users_bp.route("/user_signup", methods=['GET', 'POST'])
def user_signup():
    try:
        if 'user_email' in session and 'user_username' in session:
            flash("You're already logged in.", 'info')
            return redirect(url_for('users.index'))

        pending = get_pending_signup() or {}
        signup_data = {
            'user_signup_username': pending.get('username'),
            'user_signup_email': pending.get('email'),
        }

        step = 'username'
        if pending.get('username'):
            step = 'email'
        if pending.get('email'):
            step = 'password'

        if request.method == 'GET':
            next_url = request.args.get('next')
            if next_url and is_safe_url(next_url):
                session['user_login_next_url'] = next_url

            if request.args.get('go_back'):
                if step == 'password':
                    save_pending_signup(email=None)
                elif step == 'email':
                    save_pending_signup(username=None)
                return redirect(url_for('users.user_signup'))

        if request.method == 'POST':
            if 'username' in request.form:
                username = request.form.get('username', '').strip()
                if not username:
                    flash("Username is required.", 'signup_warning')
                    return redirect(url_for('users.user_signup'))
                elif auth_db.is_username_taken(username):
                    flash("Username is already taken.", 'signup_error')
                    return redirect(url_for('users.user_signup'))
                else:
                    save_pending_signup(username=username)
                    return redirect(url_for('users.user_signup'))

            elif 'email' in request.form:
                email = request.form.get('email', '').strip().lower()
                if not is_valid_email(email):
                    flash("Invalid email format.", 'signup_error')
                    return redirect(url_for('users.user_signup'))
                elif auth_db.get_user_by_email(email):
                    flash("Email already exists. Please login.", 'signup_error')
                    return redirect(url_for('users.user_signup'))
                else:
                    save_pending_signup(email=email)
                    return redirect(url_for('users.user_signup'))

            elif 'password' in request.form:
                password = request.form.get('password', '').strip()
                if not is_password_secure(password):
                    flash("Password must include uppercase, number, and special character.", 'signup_warning')
                    return redirect(url_for('users.user_signup'))
                else:
                    hashed_pw = hash_password(password)
                    save_pending_signup(password_hash=hashed_pw)

                    otp_value = generate_otp()

                    if send_signup_email_otp(signup_data['user_signup_username'],
                                             signup_data['user_signup_email'],
                                             otp_value, mail):
                        flash("OTP sent to your email.", 'signup_success')
                        session['user_signup_otp_last_sent'] = time.time()
                        return redirect(url_for('users.user_email_otp_verify'))
                    else:
                        flash("Network error: Could not send OTP. Please try again.", 'signup_error')
                        return redirect(url_for('users.user_signup'))

        return render_template("users/auth/user_signup.html", step=step, signup_data=signup_data)

    except Exception as e:
        logger.error(f"Critical Signup Error: {e}")
        return render_template("users/auth/error.html", error_message="An unexpected error occurred during signup. Please try again later.")

@users_bp.route("/user_email_otp_verify", methods=['GET', 'POST'])
def user_email_otp_verify():
    try:
        pending = get_pending_signup()

        if not pending or not pending.get('password_hash'):
            flash("Session expired. Please restart signup.", 'signup_error')
            return redirect(url_for('users.user_signup'))

        signup_data = {
            'user_signup_username': pending.get('username'),
            'user_signup_email': pending.get('email'),
        }

        if request.method == 'POST':
            user_otp = request.form.get('otp', '').strip()
            is_valid, msg = validate_otp(user_otp)

            if is_valid:
                try:
                    auth_db.user_signup_insert(
                        pending['username'],
                        pending['password_hash'],
                        pending['email'],
                        is_verified=True
                    )
                    send_signup_success_email(pending['username'], pending['email'], mail)
                    establish_user_session(pending['email'], pending['username'])

                    session['user_username'] = pending['username']
                    session['user_email'] = pending['email']
                    
                    next_url = session.pop('user_login_next_url', None)
                    clear_signup_session()
                    flash("Signup successful! Welcome.", 'signup_success')
                    
                    return redirect(safe_next_url(next_url, url_for('users.index')))
                except Exception as e:
                    logger.error(f"DB Insert Error: {e}")
                    flash("Database error creating account. Please contact support.", 'signup_error')
                    return redirect(url_for('users.user_signup'))
            else:
                flash(msg, 'signup_error')
                return redirect(url_for('users.user_email_otp_verify'))

        return render_template("users/auth/user_signup.html", step='otp', signup_data=signup_data)
    except Exception as e:
        logger.error(f"OTP Verify Error: {e}")
        return render_template("users/auth/error.html", error_message="System error during verification.")

@users_bp.route("/user_resend_otp", methods=['POST'])
def user_resend_otp():
    try:
        pending = get_pending_signup()
        if not pending:
             return redirect(url_for('users.user_signup'))

        if time.time() - session.get('user_signup_otp_last_sent', 0) < 60:
            flash("Wait 60 seconds before resending OTP.", 'signup_warning')
            return redirect(url_for('users.user_email_otp_verify'))

        new_otp = generate_otp()
        session['user_signup_otp_last_sent'] = time.time()

        if send_signup_email_otp(pending['username'], pending['email'], new_otp, mail):
            flash("New OTP sent.", 'signup_success')
        else:
            flash("Failed to resend OTP.", 'signup_error')
        
        return redirect(url_for('users.user_email_otp_verify'))
    except Exception:
        return redirect(url_for('users.user_signup'))