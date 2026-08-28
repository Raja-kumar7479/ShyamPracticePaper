import logging
import re
import os
import hmac
import base64
import uuid
import hashlib
import secrets
from functools import wraps
from flask import request, session, redirect, url_for, flash
from routes.auth.database.auth_db import AuthOperation
from routes.courses_platform.databases.enrollment_db import UserOperation

logger = logging.getLogger(__name__)

try:
    user_op_auth = AuthOperation()
except Exception as e:
    logger.critical(f"Failed to initialize AuthOperation: {e}", exc_info=True)
    raise

try:
    user_op_enroll = UserOperation()
except Exception as e:
    logger.critical(f"Failed to initialize UserOperation: {e}", exc_info=True)
    raise


def generate_csrf_token():
    try:
        if '_csrf_token' not in session:
            session['_csrf_token'] = secrets.token_hex(32)
            session.modified = True
        return session['_csrf_token']
    except Exception as e:
        logger.error(f"CSRF token generation error: {e}", exc_info=True)
        raise


def validate_csrf_token(token):
    try:
        session_token = session.get('_csrf_token')
        if not session_token:
            logger.warning(f"CSRF: No token in session. IP: {request.remote_addr}")
            return False
        if not token:
            logger.warning(f"CSRF: No token in request. IP: {request.remote_addr}")
            return False
        if not hmac.compare_digest(session_token, token):
            logger.warning(f"CSRF: Token mismatch. IP: {request.remote_addr}")
            return False
        return True
    except Exception as e:
        logger.error(f"CSRF validation error: {e}", exc_info=True)
        return False


def csrf_protected(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            token = request.headers.get('X-CSRFToken') or request.form.get('csrf_token')
            if not token and request.is_json:
                data = request.get_json(silent=True)
                if isinstance(data, dict):
                    token = data.get('csrf_token')
            if not validate_csrf_token(token):
                logger.warning(f"CSRF: Blocked {request.method} to {request.path} from {request.remote_addr}")
                return {"error": "CSRF validation failed", "message": "Session expired or invalid token. Please refresh the page."}, 403
        return f(*args, **kwargs)
    return decorated_function


def get_user_session():
    try:
        user_email    = session.get("user_email")
        user_username = session.get("user_username")

        if user_email and user_username and not user_email.startswith("guest_"):
            try:
                user_op_auth.update_last_active(user_email)
            except Exception as e:
                logger.error(f"Failed to update last_active for {user_email}: {e}")
            return user_email, user_username, True

        return None, None, False

    except Exception as e:
        logger.error(f"get_user_session error: {e}", exc_info=True)
        return None, None, False


def generate_secure_code(email, course_code, captcha):
    try:
        secret_key = os.environ.get("SECRET_KEY")
        if not secret_key:
            raise ValueError("SECRET_KEY environment variable is not set.")

        raw_data    = f"{email}:{course_code}:{captcha}:{uuid.uuid4()}".encode()
        hmac_digest = hmac.new(secret_key.encode(), raw_data, hashlib.sha512).digest()
        secure_code = base64.urlsafe_b64encode(hmac_digest).decode().rstrip('=')
        return secure_code[:40]

    except ValueError:
        raise
    except Exception as e:
        logger.error(f"generate_secure_code error for {email}: {e}", exc_info=True)
        raise