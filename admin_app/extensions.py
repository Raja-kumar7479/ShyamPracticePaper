import hmac
from functools import wraps
from flask import flash, jsonify, redirect, request, session, url_for, abort
import logging

logger = logging.getLogger(__name__)

ADMIN_SESSION_KEYS = (
    'admin_username', 'admin_email', 'admin_role', 'admin_pw_fp',
    'admin_login_step', 'admin_email_pending', 'admin_step_ts',
)


MANAGE_ROLES = ('owner', 'admin')


def can_manage():
    return session.get('admin_role') in MANAGE_ROLES


def clear_admin_session():
    for key in ADMIN_SESSION_KEYS:
        session.pop(key, None)


def admin_session_is_stale():
    from admin.auth.admin_db import UserOperation
    from admin.auth.admin_utils import password_fingerprint

    email = session.get('admin_email')
    if not email:
        return True
    try:
        found, password_hash = UserOperation().get_admin_auth_state(email)
    except Exception:
        logger.exception("Could not verify admin session against the database; allowing request")
        return False
    if not found:
        return True
    return not hmac.compare_digest(session.get('admin_pw_fp') or '', password_fingerprint(password_hash))


def _stale_session_response():
    email = session.get('admin_email')
    clear_admin_session()
    logger.info(f"Admin session invalidated after credential change: {email}")
    message = 'Your password was changed. Please log in again.'
    if _wants_json():
        return jsonify({
            'success': False,
            'error': 'session_expired',
            'message': message
        }), 401
    flash(message, "admin_warning")
    return redirect(url_for('admin.admin_login'))


def _wants_json():
    if request.path.startswith('/api') or request.is_json:
        return True
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    accept = request.accept_mimetypes
    return accept['application/json'] >= accept['text/html'] and accept['application/json'] > 0


def admin_owner_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_email' not in session or 'admin_username' not in session:
            if _wants_json():
                return jsonify({
                    'success': False,
                    'error': 'session_expired',
                    'message': 'Your session expired. Please log in again.'
                }), 401
            flash("Admin login required to access this page.", "admin_login_required")
            return redirect(url_for('admin.admin_login', next=request.url))
        if admin_session_is_stale():
            return _stale_session_response()
        if not can_manage():
            logger.warning(
                f"MANAGE-ONLY BLOCKED: [{session.get('admin_email')}] {request.method} {request.path}"
            )
            if _wants_json():
                return jsonify({
                    'success': False,
                    'error': 'forbidden',
                    'message': 'Permission Denied.'
                }), 403
            flash("You do not have permission to perform this action.", "admin_login_permission")
            return abort(403)
        return f(*args, **kwargs)
    return decorated_function


def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_email' not in session or 'admin_username' not in session:
            if _wants_json():
                return jsonify({
                    'success': False,
                    'error': 'session_expired',
                    'message': 'Your session expired. Please log in again.'
                }), 401
            flash("Admin login required to access this page.", "admin_login_required")
            return redirect(url_for('admin.admin_login', next=request.url))
        if admin_session_is_stale():
            return _stale_session_response()
        if session.get('admin_role') not in ['admin', 'owner']:
            if _wants_json():
                return jsonify({
                    'success': False,
                    'error': 'forbidden',
                    'message': 'You do not have permission to perform this action.'
                }), 403
            flash("You do not have permission to access this page.", "admin_login_permission")
            return abort(403)
        return f(*args, **kwargs)
    return decorated_function
