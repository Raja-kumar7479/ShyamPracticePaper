import logging
from flask import (
    flash, redirect, render_template, request, session, url_for
)
from flask_mail import Mail
from urllib.parse import urlparse, urljoin
from routes.auth.database.auth_db import AuthOperation as AuthDb
from routes.auth.utils.utils_login import (
    increment_user_login_attempts, is_user_locked_out, reset_user_login_attempts,
    rebuild_session_at_login, verify_password
)
from routes.exam_platform.competitive_exam_platform.utils.utils_test_dashboard import establish_user_session
from extensions import limiter


auth_db = AuthDb()
mail = Mail()
logger = logging.getLogger(__name__)

from routes.auth.utils.utils_login import is_safe_url

def _login_account_key():
    email = (request.form.get('email') or session.get('user_email_pending') or '').strip().lower()
    return f"login-account:{email}" if email else f"login-ip:{request.remote_addr}"


def _login_ip_key():
    return f"login-ip:{request.remote_addr}"


@users_bp.route("/user_login", methods=['GET', 'POST'])
@limiter.limit("600 per minute", methods=['POST'], key_func=_login_ip_key)
@limiter.limit("20 per minute", methods=['POST'], key_func=_login_account_key)
def user_login():
    try:
        if 'user_username' in session:
            return redirect(url_for('users.index'))

        if is_user_locked_out():
            flash("Too many failed attempts. Try again in 5 minutes.", 'login_error')
            return redirect(url_for('users.index'))

        if request.method == 'GET':
            next_url = request.args.get('next')
            if next_url and is_safe_url(next_url):
                session['user_login_next_url'] = next_url
            if request.args.get('go_back'):
                session.pop('user_login_step', None)
                session.pop('user_email_pending', None)
                return redirect(url_for('users.user_login'))

        step = session.get('user_login_step', 'email')

        if request.method == 'POST':
            if 'email' in request.form:
                email = request.form.get('email', '').strip().lower()
                user = auth_db.get_user_by_email(email)
                
                if not user:
                    flash("No account found with this email.", 'login_error')
                    return redirect(url_for('users.user_login'))
                
                if user.get('auth_type') == 'google' and not user.get('password'):
                    flash("This account uses Google sign-in. Continue with Google, or use "
                          "'Forgot password' to set a password by email.", 'login_info')
                    return redirect(url_for('users.user_login'))

                session['user_email_pending'] = email
                session['user_login_step'] = 'password'
                return redirect(url_for('users.user_login'))

            elif 'password' in request.form:
                email = session.get('user_email_pending')
                password = request.form.get('password', '')

                if not email:
                    flash("Session expired.", 'login_error')
                    session.pop('user_login_step', None)
                    return redirect(url_for('users.user_login'))
                
                user = auth_db.get_user_by_email(email)
                if not user:
                    session.pop('user_login_step', None)
                    return redirect(url_for('users.user_login'))

                if is_user_locked_out(email, strict=True):
                    flash("Too many failed attempts. Try again in 5 minutes.", 'login_error')
                    return redirect(url_for('users.index'))

                if verify_password(password, user['password']):
                    from routes.session_guard import running_test_elsewhere
                    if running_test_elsewhere(user['email']):
                        flash("This account has a test open in another window. Finish or close that test first, "
                              "then sign in again. It can take up to a minute to free up.", 'login_error')
                        return redirect(url_for('users.user_login'))
                    session.pop('_sid', None)
                    rebuild_session_at_login()

                    session['user_username'] = user['username']
                    session['user_email'] = user['email']
                    establish_user_session(user['email'], user['username'])
                    
                    reset_user_login_attempts(email)
                    session.pop('user_login_step', None)
                    session.pop('user_email_pending', None)
                    
                    next_url = session.pop('user_login_next_url', None)
                    flash("Login successful!", 'login_success')
                    
                    return redirect(next_url if next_url and is_safe_url(next_url) else url_for('users.index'))
                else:
                    increment_user_login_attempts(email)
                    flash("Invalid password.", 'login_error')
                    return redirect(url_for('users.user_login'))

        return render_template("users/auth/user_login.html", step=step)

    except Exception as e:
        logger.error(f"Login Error: {e}")
        return render_template("users/auth/error.html", error_message="Unable to process login due to system error.")
@users_bp.route('/user_logout')
def user_logout():
    session.clear()
    flash("Logged out successfully.", 'logout_success')
    response = redirect(url_for('users.index'))
    response.set_cookie('pq_logout_trigger', '1', max_age=10)
    return response
