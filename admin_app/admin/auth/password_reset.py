import hmac
import logging
import re
from flask import request, redirect, url_for, render_template, flash, current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from admin import admin_bp
from admin.auth.admin_db import UserOperation as AdminDb
from admin.auth.admin_utils import (
    hash_password, is_reset_throttled, register_reset_request, verify_password
)
from extensions import clear_admin_session
from email_service import render_email, send_email

logger = logging.getLogger(__name__)
admin_db = AdminDb()

RESET_SALT = 'admin-password-reset'
RESET_MAX_AGE = 900


def _send_password_changed_alert(email, username):
    body = (
        f"<p>Hi {username or 'Admin'},</p>"
        "<p>This is a confirmation that the password for your admin account was just changed.</p>"
        "<p>If you made this change, no action is needed. "
        "<strong>If you did NOT change your password</strong>, your account may be compromised - "
        "reset it again immediately and review admin access.</p>"
    )
    html = render_email("Your admin password was changed", body, preheader="Security alert for your admin account")
    try:
        send_email("Security alert: your admin password was changed", email, html)
    except Exception as exc:
        logger.warning(f"Admin password-changed alert failed for {email}: {exc}")


def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=RESET_SALT)


def _make_token(email, password_hash):
    return _serializer().dumps({'e': email, 'h': (password_hash or '')[-12:]})


def _read_token(token):
    return _serializer().loads(token, max_age=RESET_MAX_AGE)


def _password_ok(pw):
    if not isinstance(pw, str) or len(pw) < 8:
        return False
    special_chars = r"!@#$%^&*()-_=+[{]}\|;:'\",<.>/?`~"
    return (
        any(c.isupper() for c in pw)
        and any(c.isdigit() for c in pw)
        and any(c in special_chars for c in pw)
    )


@admin_bp.route('/admin_forgot_password', methods=['GET', 'POST'])
def admin_forgot_password():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()

        if is_reset_throttled(email):
            logger.warning(f"Admin password reset throttled for {email or '(blank)'}")
            flash("Too many reset requests. Please try again later.", 'admin_warning')
            return redirect(url_for('admin.admin_forgot_password'))
        register_reset_request(email)

        if email:
            admin = admin_db.get_admin_by_email(email)
            if admin:
                admin_username = admin[1]
                admin_email = admin[2]
                admin_password = admin[3]
                token = _make_token(admin_email, admin_password)
                reset_url = url_for('admin.admin_reset_password', token=token, _external=True)
                body = (
                    f"<p>Hi {admin_username},</p>"
                    "<p>We received a request to reset the password for your admin account. "
                    "Click the button below to choose a new password. This link expires in 15 minutes "
                    "and can be used only once.</p>"
                    "<p style='color:#64748b;font-size:13px;word-break:break-all;'>"
                    f"Or paste this link into your browser:<br>{reset_url}</p>"
                )
                html = render_email("Reset your admin password", body,
                                    cta_text="Reset password", cta_url=reset_url,
                                    preheader="Reset your admin password")
                send_email("Reset your admin password", admin_email, html)
                logger.info(f"Admin reset link sent to {admin_email}")

        flash("If an account with that email exists, a reset link has been sent.", 'admin_info')
        return redirect(url_for('admin.admin_login'))

    return render_template('admin/admin_auth/forgot_password.html')


@admin_bp.route('/admin_reset_password/<token>', methods=['GET', 'POST'])
def admin_reset_password(token):
    try:
        data = _read_token(token)
    except SignatureExpired:
        flash("This reset link has expired. Please request a new one.", 'admin_error')
        return redirect(url_for('admin.admin_forgot_password'))
    except BadSignature:
        flash("Invalid or tampered reset link.", 'admin_error')
        return redirect(url_for('admin.admin_forgot_password'))

    email = data.get('e')
    admin = admin_db.get_admin_by_email(email)
    if not admin:
        flash("Invalid reset link.", 'admin_error')
        return redirect(url_for('admin.admin_forgot_password'))

    current_hash = admin[3] or ''
    if not hmac.compare_digest(current_hash[-12:], data.get('h', '')):
        flash("This reset link has already been used. Please request a new one.", 'admin_error')
        return redirect(url_for('admin.admin_forgot_password'))

    if request.method == 'POST':
        pw = (request.form.get('password') or '').strip()
        confirm = (request.form.get('confirm_password') or '').strip()
        if pw != confirm:
            flash("Passwords do not match.", 'admin_error')
            return render_template('admin/admin_auth/reset_password.html', token=token)
        if not _password_ok(pw):
            flash("Password must be at least 8 characters and include an uppercase letter, a number and a special character.", 'admin_error')
            return render_template('admin/admin_auth/reset_password.html', token=token)
        if current_hash and verify_password(pw, current_hash):
            flash("Your new password must be different from your current password.", 'admin_error')
            return render_template('admin/admin_auth/reset_password.html', token=token)

        new_hash = hash_password(pw)
        if not new_hash or not admin_db.set_admin_password(email, new_hash):
            flash("We could not update your password. Please try again.", 'admin_error')
            return render_template('admin/admin_auth/reset_password.html', token=token)
        clear_admin_session()
        _send_password_changed_alert(admin[2], admin[1])
        logger.info(f"Admin password reset completed for {email}")
        flash("Password reset successful. Please log in with your new password.", 'admin_success')
        return redirect(url_for('admin.admin_login'))

    return render_template('admin/admin_auth/reset_password.html', token=token)
