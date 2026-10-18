from flask import render_template, request, redirect, url_for, session, flash, current_app as app
from routes.auth.utils.utils_signup import is_password_secure
from routes.auth.database.auth_db import AuthOperation
from routes.auth.utils.utils_login import safe_next_url
import bcrypt
from routes.auth.utils.utils_login import hash_password, verify_password
import logging
from routes import users_bp

auth_db = AuthOperation()
logger = logging.getLogger(__name__)

@users_bp.route("/user_set_password", methods=['GET', 'POST'])
def user_set_password():
    try:
        email = session.get('user_email')

        if not email:
            flash("Please sign in with Google first, or use "
                  "'Forgot password' to set a password by email.", "login_error")
            return redirect(url_for('users.user_login'))

        user = auth_db.get_user_by_email(email)
        if not user:
            flash("User not found.", 'login_error')
            return redirect(url_for('users.user_login'))

        if user.get('auth_type') not in ['google', 'both']:
            flash("This feature is only for Google-registered users.", 'login_error')
            return redirect(url_for('users.user_login'))

        if user.get('password'):
            flash("You have already set your password.", 'login_info')
            return redirect(url_for('users.index'))

        if request.method == 'POST':
            new_password = request.form.get('new_password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()

            if not new_password or not confirm_password:
                flash("Both fields are required.", 'login_error')
                return redirect(url_for('users.user_set_password'))

            if new_password != confirm_password:
                flash("Passwords do not match.", 'login_error')
                return redirect(url_for('users.user_set_password'))

            if not is_password_secure(new_password):
                flash("Password must have 8+ characters, 1 uppercase, 1 digit, 1 special char.", 'login_error')
                return redirect(url_for('users.user_set_password'))

            try:
                hashed_pw = hash_password(new_password)
                auth_db.set_user_password(email, hashed_pw)
                
                if user.get('auth_type') == 'google':
                    auth_db.update_auth_type_to_both(email, user.get('oauth_id'))
            except Exception:
                flash("Error setting password.", "login_error")
                return redirect(url_for('users.user_set_password'))

            session['user_username'] = user['username']
            session['user_email'] = user['email']
            session.permanent = True
            session.pop('user_login_step', None)
            session.pop('user_email_pending', None)
            
            next_url = session.pop('user_login_next_url', None)

            flash("Password set successfully!", 'login_success')
            return redirect(safe_next_url(next_url, url_for('users.index')))

        return render_template("users/auth/set_password.html", email=email)
    except Exception:
        return render_template("users/auth/error.html", error_message="System error.")