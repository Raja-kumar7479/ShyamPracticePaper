import logging
import uuid
import hashlib
import secrets
import hmac
from functools import wraps
from flask import request, session, current_app
from routes.courses_platform.databases.profile_db import ProfileOperation

logger = logging.getLogger(__name__)

user_op = ProfileOperation()

def generate_csrf_token():
    try:
        if '_csrf_token' not in session:
            session['_csrf_token'] = secrets.token_hex(32)
            session.modified = True
            logger.info(f"CSRF: Generated new token. IP: {request.remote_addr}")
        return session['_csrf_token']
    except Exception as e:
        logger.error(f"CSRF Generation Error: {e}", exc_info=True)
        return None

def validate_csrf_token(token):
    try:
        session_token = session.get('_csrf_token')
        client_ip = request.remote_addr

        if not session_token:
            logger.warning(f"CSRF Validation Failed: No token in session (Session Expired). IP: {client_ip}")
            return False
        
        if not token:
            logger.warning(f"CSRF Validation Failed: No token provided in request. IP: {client_ip}")
            return False
            
        if not hmac.compare_digest(session_token, token):
            logger.warning(f"CSRF Validation Failed: Token mismatch. IP: {client_ip}")
            return False
        
        return True
    except Exception as e:
        logger.error(f"CSRF Validation System Error: {e}", exc_info=True)
        return False

def csrf_protected(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            token = request.headers.get('X-CSRFToken') or request.form.get('csrf_token')
            
            if not token and request.is_json:
                data = request.get_json(silent=True)
                if data and isinstance(data, dict):
                    token = data.get('csrf_token')

            if not validate_csrf_token(token):
                logger.warning(f"CSRF: Protection blocked request to {request.path} from {request.remote_addr}")
                return {"error": "CSRF validation failed", "message": "Session expired or invalid token. Please refresh."}, 403
        return f(*args, **kwargs)
    return decorated_function

def generate_guest_identity():
    try:
        unique_id = str(uuid.uuid4())
        hashed = hashlib.sha256(unique_id.encode()).hexdigest()[:12]
        guest_email = f"guest_{hashed}@shyampp.com"
        guest_username = f"Guest_{hashed[:6]}"
        return guest_email, guest_username
    except Exception as e:
        logger.error(f"Guest Identity Generation Error: {e}", exc_info=True)
        fallback = secrets.token_hex(8)
        return f"guest_{fallback}@shyampp.com", f"Guest_{fallback}"

def get_user_session():
    try:
        user_email = session.get("user_email")
        user_username = session.get("user_username")

        if user_email and user_username and not str(user_email).startswith("guest_"):
            try:
                user_op.update_last_active(user_email)
            except Exception as db_e:
                logger.error(f"DB Warning: Failed to update last_active for {user_email}: {db_e}")
            
            return user_email, user_username, True
        
        return None, None, False

    except Exception as e:
        logger.critical(f"CRITICAL SESSION ERROR: {e}", exc_info=True)
        return None, None, False