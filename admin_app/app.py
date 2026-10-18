import logging
import os
import sys
from datetime import timedelta

from dotenv import load_dotenv

from logging_config import configure_logging

load_dotenv()
configure_logging()

logger = logging.getLogger(__name__)

from db_bootstrap import ensure_schema

ensure_schema(logger)

from flask import (Flask, jsonify, redirect, render_template, request,
                   url_for, send_from_directory)
from flask_mail import Mail
from config import Config
from extensions import admin_login_required, can_manage
from admin import admin_bp

app = Flask(__name__)
app.config.from_object(Config)
if not app.config.get('SECRET_KEY'):
    logger.critical("SECRET_KEY is not set. Refusing to start without it.")
    raise RuntimeError("SECRET_KEY environment variable is required.")
app.permanent_session_lifetime = timedelta(hours=4)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
_secure_cookie_env = os.environ.get('SESSION_COOKIE_SECURE')
if _secure_cookie_env is not None:
    app.config['SESSION_COOKIE_SECURE'] = _secure_cookie_env.strip().lower() in ('1', 'true', 'yes', 'on')
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024

_is_production = bool(os.environ.get('RENDER') or os.environ.get('GUNICORN_CMD_ARGS'))
app.config['TEMPLATES_AUTO_RELOAD'] = not _is_production
if not _is_production:
    app.jinja_env.auto_reload = True

SHARED_UPLOADS = Config.UPLOAD_BASE

mail = Mail(app)

@app.context_processor
def inject_permissions():
    return {'can_manage': can_manage()}


app.register_blueprint(admin_bp)


@app.route('/')
def index():
    return redirect(url_for('admin.admin_login'))


@app.route('/static/uploads/<path:filename>')
@admin_login_required
def shared_uploads(filename):
    from admin.shared_files import ensure_local
    ensure_local(filename)
    return send_from_directory(SHARED_UPLOADS, filename)


from admin.shared_files import start_publisher
start_publisher()


@app.after_request
def add_security_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-XSS-Protection'] = '0'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    return response


ERROR_COPY = {
    400: ("Bad Request", "The request could not be understood."),
    401: ("Unauthorized", "Please log in to continue."),
    403: ("Access Denied", "You do not have permission to view this page."),
    404: ("Not Found", "The requested URL was not found on the server."),
    500: ("Internal Server Error", "An internal error occurred."),
}


def _wants_json():
    if request.path.startswith('/api') or request.is_json:
        return True
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    accept = request.accept_mimetypes
    return accept['application/json'] >= accept['text/html'] and accept['application/json'] > 0


def _error_response(code):
    title, message = ERROR_COPY.get(code, ERROR_COPY[500])
    if _wants_json():
        return jsonify({"error": f"{code} {title}", "message": message}), code
    try:
        return render_template('admin/error.html', error_code=code,
                               error_title=title, error_message=message), code
    except Exception:
        logger.exception("Could not render the %s error page", code)
        return jsonify({"error": f"{code} {title}", "message": message}), code


@app.errorhandler(404)
def not_found_error(error):
    return _error_response(404)


@app.errorhandler(500)
def internal_error(error):
    return _error_response(500)


@app.errorhandler(403)
def forbidden_error(error):
    return _error_response(403)


try:
    from admin.manage_modules.cleanup_script import start_expiry_scheduler
    start_expiry_scheduler(app)
except Exception:
    logger.exception("EXPIRY: could not start the content expiry scheduler")


if __name__ == '__main__':
    try:
        app.run(debug=False, port=5001, use_reloader=not _is_production)
    except Exception as e:
        logger.exception("Failed to start the admin application: %s", e)
