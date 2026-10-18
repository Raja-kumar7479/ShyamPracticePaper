import logging
import time
import bcrypt
from functools import wraps
from flask import (
    flash, redirect, render_template, request, session, url_for, current_app as app, Response
)
from flask_mail import Mail
from extensions import admin_login_required, clear_admin_session
from admin.auth.admin_db import UserOperation as AdminDb

from admin.auth.admin_utils import (
    increment_admin_login_attempts, is_admin_locked_out, password_fingerprint,
    reset_admin_login_attempts
)

from admin.auth.admin_utils import verify_password as verify_admin_password

from admin import admin_bp

admin_db = AdminDb()
mail = Mail()

logger = logging.getLogger(__name__)

@admin_bp.route('/admin_dashboard')
@admin_login_required
def admin_dashboard():
    username = session.get('admin_username')
    email = session.get('admin_email')
    role = session.get('admin_role')

    if not username or not email or not role:
        flash("Session expired or incomplete. Please log in again.", "admin_warning")
        return redirect(url_for('admin.admin_login'))

    return render_template('admin/admin_dashboard/admin.html', username=username, email=email, role=role)

@admin_bp.route("/admin_login", methods=['GET', 'POST'])
def admin_login():
    if 'admin_email' in session:
        flash("Already logged in as Admin.", 'admin_info')
        return redirect(url_for('admin.admin_dashboard'))

    if request.args.get('go_back'):
        session.pop('admin_login_step', None)
        session.pop('admin_email_pending', None)
        session.pop('admin_step_ts', None)
        return redirect(url_for('admin.admin_login'))

    if is_admin_locked_out():
        flash("Too many login attempts. Please try again in a few minutes.", 'admin_error')
        return render_template("admin/admin_auth/admin_login.html", step='email', locked_out=True)

    STEP_TTL_SECONDS = 600
    pending_email = session.get('admin_email_pending')
    pending_ts = session.get('admin_step_ts', 0)
    if pending_email and (time.time() - pending_ts) < STEP_TTL_SECONDS:
        step = 'password'
    else:
        session.pop('admin_email_pending', None)
        session.pop('admin_step_ts', None)
        session.pop('admin_login_step', None)
        step = 'email'

    if request.method == 'POST':
        if step == 'email':
            email = request.form.get('email', '').strip()
            if not email:
                flash("Please enter your email.", 'admin_warning')
                return redirect(url_for('admin.admin_login'))

            admin = admin_db.get_admin_by_email(email)
            if not admin:
                logger.warning(f"Admin login attempted with unknown email: {email}")
                increment_admin_login_attempts(email)
                flash("Email not found. Please check the address and try again.", 'admin_error')
                return redirect(url_for('admin.admin_login'))

            session['admin_email_pending'] = email
            session['admin_step_ts'] = time.time()
            return redirect(url_for('admin.admin_login'))

        elif step == 'password':
            password = request.form.get('password', '').strip()
            email = session.get('admin_email_pending')

            if not password or not email:
                flash("Session expired or invalid step. Start again.", 'admin_error')
                return redirect(url_for('admin.admin_login'))

            admin = admin_db.get_admin_by_email(email)
            if not admin:
                flash("Incorrect email or password.", 'admin_error')
                increment_admin_login_attempts(email)
                logger.warning(f"Invalid login attempt for email: {email}")
                return redirect(url_for('admin.admin_login'))

            admin_password = admin[3]
            admin_username = admin[1]
            admin_email = admin[2]
            admin_role = admin[4]

            if not admin_password:
                flash("This account has no password set. Use 'Forgot password' to set one.", 'admin_error')
                increment_admin_login_attempts(email)
                logger.error(f"Login blocked: admin {email} has no password hash set")
                return redirect(url_for('admin.admin_forgot_password'))

            if not verify_admin_password(password, admin_password):
                flash("Incorrect email or password.", 'admin_error')
                increment_admin_login_attempts(email)
                logger.warning(f"Failed login attempt for admin {email}")
                return redirect(url_for('admin.admin_login'))

            session.permanent = True
            session['admin_username'] = admin_username
            session['admin_email'] = admin_email
            session['admin_role'] = 'owner' if admin_role == 'owner' else 'admin'
            session['admin_pw_fp'] = password_fingerprint(admin_password)
            reset_admin_login_attempts(email)
            session.pop('admin_login_step', None)
            session.pop('admin_email_pending', None)
            session.pop('admin_step_ts', None)
            flash("Admin login successful!", 'admin_success')
            logger.info(f"Admin login successful for {email}")
            return redirect(url_for('admin.admin_dashboard'))

    return render_template("admin/admin_auth/admin_login.html", step=step)

@admin_bp.route('/admin_logout')
def admin_logout():
    clear_admin_session()
    flash("You have been successfully logged out.", 'admin_info')
    logger.info("Admin logged out")
    return redirect(url_for('admin.admin_login'))

@admin_bp.after_request
def set_security_headers(response: Response):
    if request.path.startswith('/admin'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    return response