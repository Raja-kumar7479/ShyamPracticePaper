import time
from flask import session
import pyotp
from routes.email_service import render_email, send_email, code_block


def send_forgot_otp_email(email, mail=None):
    if 'user_forgot_otp_secret' not in session:
        session['user_forgot_otp_secret'] = pyotp.random_base32()

    totp = pyotp.TOTP(session['user_forgot_otp_secret'], interval=300)
    otp = totp.now()
    otp_expiry = time.time() + 300
    session['user_forgot_otp'] = {'value': otp, 'expiry': otp_expiry}
    session['user_forgot_otp_last_sent'] = time.time()

    body = (
        "<p>We received a request to reset your password. "
        "Use the code below to continue. It expires in 5 minutes.</p>"
        f"{code_block(otp)}"
        "<p style='color:#992c25;font-size:13px;'>Didn't request a password reset? You can safely ignore this email; your password stays unchanged.</p>"
    )
    html = render_email("Reset your password", body, preheader="Your password reset code")
    return send_email("Reset your password", email, html)