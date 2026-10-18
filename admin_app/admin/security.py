import hmac
import logging
import secrets
from flask import flash, jsonify, redirect, request, session, url_for
from admin import admin_bp

logger = logging.getLogger(__name__)

CSRF_SESSION_KEY = '_admin_csrf_token'
SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}


def generate_csrf_token():
    if CSRF_SESSION_KEY not in session:
        session[CSRF_SESSION_KEY] = secrets.token_hex(32)
    return session[CSRF_SESSION_KEY]


@admin_bp.app_context_processor
def inject_csrf_token():
    return {'csrf_token': generate_csrf_token}


def _supplied_token():
    token = request.headers.get('X-CSRFToken')
    if token:
        return token
    token = request.form.get('_csrf_token')
    if token:
        return token
    if request.is_json:
        data = request.get_json(silent=True)
        if isinstance(data, dict):
            return data.get('_csrf_token')
    return None


def _wants_json():
    if request.path.startswith('/api') or request.is_json:
        return True
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    accept = request.accept_mimetypes
    return accept['application/json'] >= accept['text/html'] and accept['application/json'] > 0


@admin_bp.before_request
def csrf_protect():
    if request.method in SAFE_METHODS:
        return None
    expected = session.get(CSRF_SESSION_KEY)
    supplied = _supplied_token()
    if expected and supplied and hmac.compare_digest(str(expected), str(supplied)):
        return None
    who = session.get('admin_email', 'anonymous')
    reason = 'missing' if not supplied else 'mismatch'
    logger.warning(f"CSRF BLOCKED: [{who}] {request.method} {request.path} (token {reason})")
    if _wants_json():
        return jsonify({'success': False,
                        'error': 'This request was blocked for security. Refresh the page and try again.'}), 403
    flash('Your session expired or the form was blocked for security. Please try again.', 'admin_error')
    return redirect(request.referrer or url_for('admin.admin_login'))
