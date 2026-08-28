import hmac
import logging
import time
import bcrypt
from flask import render_template, request, redirect, url_for, session, flash, current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from routes.auth.database.auth_db import AuthOperation
from routes.auth.utils.utils_signup import is_password_secure
from routes.auth.utils.utils_login import reset_user_login_attempts
from routes.exam_platform.competitive_exam_platform.utils.utils_test_dashboard import establish_user_session
from routes.email_service import render_email, send_email
from routes import users_bp
from extensions import limiter

auth_db = AuthOperation()
logger = logging.getLogger(__name__)

RESET_SALT = 'user-password-reset'
RESET_MAX_AGE = 900
RESET_THROTTLE_SECONDS = 60


def _send_password_changed_alert(email, username):
    body = (
        f"<p>Hi {username or 'there'},</p>"
        "<p>This is a confirmation that the password for your account was just changed.</p>"
        "<p>If you made this change, no action is needed. "
        "<strong>If you did NOT change your password</strong>, your account may be at risk — "
        "reset your password again immediately and contact support.</p>"
    )
    html = render_email("Your password was changed", body, preheader="Security alert for your account")
    try:
        send_email("Security alert: your password was changed", email, html)
    except Exception as exc:
        logger.warning(f"Password-changed alert failed for {email}: {exc}")


def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=RESET_SALT)


def _make_token(email, password_hash):
    return _serializer().dumps({'e': email, 'h': (password_hash or '')[-12:]})


def _read_token(token):
    return _serializer().loads(token, max_age=RESET_MAX_AGE)


@users_bp.route("/user_forgot_password", methods=['GET', 'POST'])
@limiter.limit("5 per hour", exempt_when=lambda: request.method != 'POST')
def user_forgot_password():
    if 'user_username' in session:
        return redirect(url_for('users.index'))

    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()

        if time.time() - session.get('user_reset_last_sent', 0) < RESET_THROTTLE_SECONDS:
            flash("Please wait a moment before requesting another link.", 'forgot_error')
            return redirect(url_for('users.user_forgot_password'))
        session['user_reset_last_sent'] = time.time()

        if email:
            try:
                user = auth_db.get_user_by_email(email)
            except Exception:
                user = None
            if user:
                token = _make_token(user['email'], user.get('password'))
                reset_url = url_for('users.user_reset_password', token=token, _external=True)
                body = (
                    f"<p>Hi {user.get('username', 'there')},</p>"
                    "<p>We received a request to reset your password. Click the button below to choose a new one. "
                    "This link expires in 15 minutes and can be used only once.</p>"
                    "<p style='color:#992c25;font-size:13px;word-break:break-all;'>"
                    f"Or paste this link into your browser:<br>{reset_url}</p>"
                )
                html = render_email("Reset your password", body,
                                    cta_text="Reset password", cta_url=reset_url,
                                    preheader="Your password reset link")
                send_email("Reset your password", user['email'], html)
                logger.info(f"Password reset link sent to {user['email']}")

        session['user_reset_sent_to'] = email
        session.modified = True
        return redirect(url_for('users.user_forgot_password', sent=1))

    sent_to = None
    if request.args.get('sent'):
        sent_to = session.pop('user_reset_sent_to', None)
        session.modified = True

    return render_template('users/auth/forgot_password.html',
                           link_sent=bool(request.args.get('sent')),
                           sent_to=sent_to)


@users_bp.route("/user_reset_password/<token>", methods=['GET', 'POST'])
def user_reset_password(token):
    if 'user_username' in session:
        return redirect(url_for('users.index'))

    try:
        data = _read_token(token)
    except SignatureExpired:
        flash("This reset link has expired. Please request a new one.", 'forgot_error')
        return redirect(url_for('users.user_forgot_password'))
    except BadSignature:
        flash("Invalid or tampered reset link.", 'forgot_error')
        return redirect(url_for('users.user_forgot_password'))

    email = data.get('e')
    try:
        user = auth_db.get_user_by_email(email)
    except Exception:
        user = None
    if not user:
        flash("Invalid reset link.", 'forgot_error')
        return redirect(url_for('users.user_forgot_password'))

    current_hash = user.get('password') or ''
    if not hmac.compare_digest(current_hash[-12:], data.get('h', '')):
        flash("This reset link has already been used. Please request a new one.", 'forgot_error')
        return redirect(url_for('users.user_forgot_password'))

    if request.method == 'POST':
        new_pw = request.form.get('new_password') or ''
        confirm_pw = request.form.get('confirm_password') or ''
        # Redirect back to the same reset link rather than rendering, so a
        # failed attempt does not leave the browser on the POST where Back or
        # Refresh prompts to resubmit the password. The token is in the URL,
        # so the reload lands on exactly the same form.
        if new_pw != confirm_pw:
            flash("Passwords do not match.", 'forgot_error')
            return redirect(url_for('users.user_reset_password', token=token))
        if not is_password_secure(new_pw):
            flash("Password is too weak. Use 8+ characters with a mix of letters, numbers and a symbol.", 'forgot_error')
            return redirect(url_for('users.user_reset_password', token=token))
        if current_hash and bcrypt.checkpw(new_pw.encode(), current_hash.encode()):
            flash("Your new password must be different from your current password.", 'forgot_error')
            return redirect(url_for('users.user_reset_password', token=token))

        hashed = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
        auth_db.update_user_password(email, hashed)
        session.pop('user_reset_last_sent', None)
        session.pop('user_reset_sent_to', None)
        _send_password_changed_alert(email, user.get('username'))
        logger.info(f"Password reset completed for {email}")

        from routes.auth.utils.utils_login import rebuild_session_at_login
        rebuild_session_at_login()

        session['user_username'] = user['username']
        session['user_email'] = user['email']
        session.modified = True

        try:
            reset_user_login_attempts()
        except Exception as exc:
            logger.warning(f"Could not reset login attempts for {email}: {exc}")

        try:
            establish_user_session(user['email'], user['username'])
        except Exception as exc:
            logger.warning(f"Guest conversion after reset failed for {email}: {exc}")

        logger.info(f"Auto-signed in {email} after password reset; sending to main page.")
        flash(f"Password updated. Welcome back, {user['username']}!", 'login_success')
        return redirect(url_for('users.index'))

    return render_template('users/auth/reset_password.html', token=token)
