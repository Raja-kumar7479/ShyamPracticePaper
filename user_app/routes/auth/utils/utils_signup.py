import hashlib
import hmac
import os
import pyotp
import secrets
import time
import re
from datetime import datetime, timedelta
from flask import session
from routes.email_service import render_email, send_email, code_block

OTP_VALIDITY_PERIOD = 300
WEBSITE_URL = (os.environ.get('WEBSITE_URL') or '').strip().rstrip('/')


def _site_url():
    if WEBSITE_URL:
        return WEBSITE_URL
    try:
        from flask import url_for
        return url_for('users.index', _external=True)
    except Exception:
        return '/'

def is_valid_email(email: str) -> bool:
    pattern = r"^[^@]+@[^@]+\.[^@]+$"
    return bool(re.fullmatch(pattern, email))

def is_password_secure(password: str) -> bool:
    special_chars = r"!@#$%^&*()-_=+[{]}\|;:'\",<.>/?`~"
    return (
        len(password) >= 8 and
        any(c.isupper() for c in password) and
        any(c.isdigit() for c in password) and
        any(c in special_chars for c in password)
    )

PENDING_TOKEN_KEY = 'signup_pending_token'
MAX_OTP_ATTEMPTS = 6


def _otp_hash(otp_value):
    secret = os.environ.get('SECRET_KEY')
    if not secret:
        raise RuntimeError("SECRET_KEY must be set to hash signup OTPs.")
    return hmac.new(secret.encode(), str(otp_value).strip().encode(),
                    hashlib.sha256).hexdigest()


def _pending_db():
    from routes.auth.database.auth_db import AuthOperation
    return AuthOperation()


def pending_token(create=False):
    token = session.get(PENDING_TOKEN_KEY)
    if not token and create:
        token = secrets.token_hex(32)
        session[PENDING_TOKEN_KEY] = token
        session.modified = True
    return token


def get_pending_signup():
    token = pending_token()
    if not token:
        return None
    try:
        return _pending_db().get_pending_signup(token)
    except Exception:
        return None


def save_pending_signup(**fields):
    token = pending_token(create=True)
    _pending_db().upsert_pending_signup(token, **fields)
    return token


def generate_otp():
    otp_secret = pyotp.random_base32()
    otp_value = pyotp.TOTP(otp_secret, interval=OTP_VALIDITY_PERIOD).now()
    save_pending_signup(otp_hash=_otp_hash(otp_value),
                        otp_expires_at=datetime.now() + timedelta(seconds=OTP_VALIDITY_PERIOD),
                        otp_attempts=0)
    return otp_value


def validate_otp(user_otp):
    row = get_pending_signup()
    if not row or not row.get('otp_hash'):
        return False, "Session expired. Please request a new OTP."

    if row.get('otp_attempts', 0) >= MAX_OTP_ATTEMPTS:
        return False, "Too many incorrect codes. Please request a new OTP."

    expires = row.get('otp_expires_at')
    if not expires or datetime.now() > expires:
        return False, "OTP has expired."

    if not hmac.compare_digest(_otp_hash(user_otp), row['otp_hash']):
        try:
            _pending_db().bump_otp_attempts(pending_token())
        except Exception:
            pass
        return False, "Invalid OTP. Please check and try again."

    return True, "Success"


def clear_signup_session():
    token = session.get(PENDING_TOKEN_KEY)
    if token:
        try:
            _pending_db().delete_pending_signup(token)
        except Exception:
            pass

    keys = [
        'user_signup_data', 'user_signup_otp_data', 'signup_otp',
        'signup_otp_secret', 'user_signup_otp_last_sent',
        'user_signup_otp_attempts', 'user_signup_username',
        'user_signup_email', 'user_signup_password', PENDING_TOKEN_KEY
    ]
    for key in keys:
        session.pop(key, None)

def send_signup_email_otp(username, email, otp_value, mail=None):
    body = (
        f"<p>Hi {username},</p>"
        f"<p>Use the verification code below to confirm your email address and finish creating your account. "
        f"This code expires in a few minutes.</p>"
        f"{code_block(otp_value)}"
        f"<p style='color:#992c25;font-size:13px;'>If you didn't request this, you can safely ignore this email.</p>"
    )
    html = render_email("Verify your email", body, preheader="Your verification code")
    return send_email("Verify your email address", email, html)

def send_signup_success_email(username, email, mail=None):
    body = (
        f"<p>Hi {username},</p>"
        f"<p>Your account is ready. Welcome aboard! You can now explore courses, enroll, take mock tests, "
        f"and track your progress — all in one place.</p>"
        f"<p>We're glad to have you with us.</p>"
    )
    html = render_email("Welcome to the platform \U0001F389", body,
                        cta_text="Go to Dashboard", cta_url=_site_url(),
                        preheader="Your account is ready")
    return send_email("Welcome! Your account is ready", email, html)