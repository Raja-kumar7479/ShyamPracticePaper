import hmac
import logging
import time
import pyotp
from flask import session
from routes.email_service import render_email, send_email, code_block

logger = logging.getLogger(__name__)

OTP_TTL_SECONDS = 600
OTP_RESEND_COOLDOWN = 60
OTP_MAX_ATTEMPTS = 5

SESSION_KEY = 'delete_account_otp'


def _now():
    return time.time()


def send_delete_account_otp(email, username):
    existing = session.get(SESSION_KEY) or {}
    last_sent = existing.get('last_sent', 0)
    remaining = int(OTP_RESEND_COOLDOWN - (_now() - last_sent))
    if remaining > 0:
        return False, f"Please wait {remaining} second(s) before requesting another code."

    secret = pyotp.random_base32()
    otp = pyotp.TOTP(secret, interval=OTP_TTL_SECONDS).now()

    session[SESSION_KEY] = {
        'email': email,
        'value': otp,
        'expiry': _now() + OTP_TTL_SECONDS,
        'last_sent': _now(),
        'attempts': 0
    }
    session.modified = True

    body = (
        f"<p>Hi {username or 'there'},</p>"
        "<p>We received a request to <strong>permanently delete</strong> your account. "
        "Enter the code below to confirm. It expires in 10 minutes.</p>"
        f"{code_block(otp)}"
        "<p style='color:#992c25;font-size:14px;'><strong>This cannot be undone.</strong> Deleting your account "
        "permanently removes your profile, enrollments, purchases, test results and every course you have "
        "unlocked. Purchased content will not be restorable and is not refundable.</p>"
        "<p style='color:#8a7a74;font-size:13px;'>If you did not request this, ignore this email and change "
        "your password — your account stays exactly as it is.</p>"
    )
    html = render_email("Confirm account deletion", body,
                        preheader="Your account deletion code")

    if not send_email("Confirm your account deletion", email, html):
        session.pop(SESSION_KEY, None)
        session.modified = True
        return False, "We could not send the confirmation email. Please try again shortly."

    logger.warning(f"ACCOUNT DELETION: verification code sent to {email}.")
    return True, "A confirmation code has been sent to your email."


def verify_delete_account_otp(email, submitted_otp):
    record = session.get(SESSION_KEY)
    if not record:
        return False, "No deletion request is in progress. Please start again."

    if record.get('email') != email:
        session.pop(SESSION_KEY, None)
        session.modified = True
        logger.warning("ACCOUNT DELETION: session email mismatch; request discarded.")
        return False, "This request does not match your account. Please start again."

    if _now() > record.get('expiry', 0):
        session.pop(SESSION_KEY, None)
        session.modified = True
        return False, "Your code has expired. Please request a new one."

    attempts = record.get('attempts', 0) + 1
    record['attempts'] = attempts
    session[SESSION_KEY] = record
    session.modified = True

    if attempts > OTP_MAX_ATTEMPTS:
        session.pop(SESSION_KEY, None)
        session.modified = True
        logger.warning(f"ACCOUNT DELETION: too many failed code attempts for {email}; request discarded.")
        return False, "Too many incorrect attempts. Please start again."

    submitted = (submitted_otp or '').strip()
    if not submitted or not hmac.compare_digest(str(record.get('value', '')), submitted):
        left = OTP_MAX_ATTEMPTS - attempts
        logger.warning(f"ACCOUNT DELETION: incorrect code for {email}. {max(left, 0)} attempt(s) left.")
        if left <= 0:
            return False, "Incorrect code. Please start again."
        return False, f"Incorrect code. {left} attempt(s) remaining."

    logger.info(f"ACCOUNT DELETION: code verified for {email}.")
    return True, "Verified."


def clear_delete_account_otp():
    session.pop(SESSION_KEY, None)
    session.modified = True
