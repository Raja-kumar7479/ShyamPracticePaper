import logging
import secrets
import uuid
import hashlib
import hmac
import os
from functools import wraps
from flask import request, session, current_app, redirect, url_for, flash, jsonify
from routes.auth.database.auth_db import AuthOperation

logger = logging.getLogger(__name__)

user_op_auth = AuthOperation()

def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
        session.modified = True
    return session['_csrf_token']

def validate_csrf_token(token):
    session_token = session.get('_csrf_token')
    if not session_token or not token:
        return False
    return hmac.compare_digest(session_token, token)

def csrf_protected(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == "POST":
            token = request.headers.get('X-CSRFToken') or request.form.get('csrf_token') or request.form.get('_csrf_token')
            if not validate_csrf_token(token):
                logger.warning("CSRF: Validation failed.")
                return {"error": "CSRF validation failed"}, 403
        return f(*args, **kwargs)
    return decorated_function

def get_user_session():
    email = session.get("user_email")
    username = session.get("user_username")

    if email and username and not email.startswith("guest_"):
        try:
            user_op_auth.update_last_active(email)
        except Exception:
            pass
        return email, username, True

    logger.info("USER_SESSION: No authenticated session")
    return None, None, False

def is_user_authenticated():
    email = session.get("user_email")
    username = session.get("user_username")
    return bool(email and username and not str(email).startswith("guest_"))


def _wants_json():
    if request.is_json:
        return True
    if "/api/" in request.path:
        return True
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    accept = request.headers.get("Accept", "")
    return "application/json" in accept and "text/html" not in accept


def comm_login_required(f=None, message="Please log in to access this assessment."):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if is_user_authenticated():
                return func(*args, **kwargs)

            logger.warning("COMM AUTH: login required for %s %s", request.method, request.path)

            if _wants_json():
                return jsonify({
                    "status": "error",
                    "code": "login_required",
                    "message": "Your session has ended. Please log in again to continue.",
                    "login_url": url_for("users.user_login"),
                }), 401

            next_url = request.full_path if request.query_string else request.path
            flash(message, "test_error")
            return redirect(url_for("users.user_login", next=next_url))
        return wrapper

    if f is None:
        return decorator
    return decorator(f)
