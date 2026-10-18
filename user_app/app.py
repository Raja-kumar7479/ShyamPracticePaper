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

from flask import (Flask, abort, flash, jsonify, redirect, render_template, request, session,
                   send_from_directory, url_for)
from werkzeug.routing import BuildError
from flask_mail import Mail
from flask_session import Session
from extensions import init_limiter, limiter, socketio, is_redis_available, redis_url, redis_pool
from redis import Redis
from config import Config
from routes import users_bp

app = Flask(__name__)
app.config.from_object(Config)


if not app.config.get('SECRET_KEY'):
    logger.critical("SECRET_KEY is not set. Refusing to start without it.")
    raise RuntimeError("SECRET_KEY environment variable is required.")

app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024

SHARED_UPLOADS = Config.UPLOAD_BASE

_is_production = Config.IS_PRODUCTION
app.config['TEMPLATES_AUTO_RELOAD'] = not _is_production
if not _is_production:
    app.jinja_env.auto_reload = True

if _is_production:
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
    app.config['PREFERRED_URL_SCHEME'] = 'https'

init_limiter(app)
mail = Mail(app)


@app.url_defaults
def _static_cache_bust(endpoint, values):
    if endpoint != 'static' or 'filename' not in values:
        return
    filename = values['filename']
    if not filename.endswith(('.js', '.css')):
        return
    path = os.path.join(app.static_folder, filename)
    try:
        values['v'] = int(os.stat(path).st_mtime)
    except OSError:
        pass

async_mode = 'gevent' if (os.environ.get('SPP_ASYNC_MODE') or '').strip().lower() == 'gevent' else 'threading'
logger.info("Socket.IO async mode: %s", async_mode)

_socket_origins = [o.strip() for o in
                   (os.environ.get('SOCKETIO_ORIGINS') or '').split(',') if o.strip()]
if not _socket_origins:
    _socket_origins = ["http://127.0.0.1:5002", "http://localhost:5002"]
    site = (os.environ.get('WEBSITE_URL') or '').strip().rstrip('/')
    if site:
        _socket_origins.append(site)
logger.info("Socket.IO allowed origins: %s", _socket_origins)

socketio.init_app(
    app,
    cors_allowed_origins=_socket_origins,
    async_mode=async_mode,
    ping_timeout=60,
    ping_interval=25
)

if is_redis_available:
    logger.info("Redis detected. Using server-side Redis sessions.")
    app.config.update({
        'SESSION_TYPE': 'redis',
        'SESSION_REDIS': Redis(connection_pool=redis_pool) if redis_pool is not None else Redis.from_url(redis_url),
        'SESSION_COOKIE_SECURE': _is_production,
        'SESSION_COOKIE_HTTPONLY': True,
        'SESSION_COOKIE_SAMESITE': 'Lax',
        'SESSION_PERMANENT': True,
        'PERMANENT_SESSION_LIFETIME': timedelta(minutes=30)
    })
    Session(app)
else:
    if _is_production:
        logger.critical("PRODUCTION WITHOUT REDIS: rate limits are per-worker, Socket.IO events "
                        "do not cross workers, and sessions live on local disk. Set REDIS_URL "
                        "for a multi-worker deployment.")
    logger.info("Redis not found. Using server-side filesystem sessions.")
    app.config.update({
        'SESSION_TYPE': 'filesystem',
        'SESSION_FILE_DIR': os.path.join(os.path.dirname(os.path.abspath(__file__)), '.flask_session'),
        'SESSION_FILE_THRESHOLD': int(os.environ.get('SESSION_FILE_THRESHOLD', '200000')),
        'SESSION_COOKIE_SECURE': _is_production,
        'SESSION_COOKIE_HTTPONLY': True,
        'SESSION_COOKIE_SAMESITE': 'Lax',
        'SESSION_PERMANENT': True,
        'PERMANENT_SESSION_LIFETIME': timedelta(minutes=30)
    })
    Session(app)


PRIVATE_UPLOAD_PREFIXES = ('user_responses/', 'verification/', 'proctor_snaps/', 'audio_checks/')

PREMIUM_UPLOAD_PREFIXES = ('practice_coding/', 'practice_quiz/')


def _premium_upload_allowed(normalized):
    name = os.path.basename(normalized)
    if not name:
        return False
    like = '%' + name
    try:
        from routes.db_pool import get_connection
        conn = get_connection()
        cur = conn.cursor()
        try:
            if normalized.startswith('practice_coding/'):
                cur.execute("""
                    SELECT MAX(is_paid) FROM pcp_questions
                    WHERE statement_image LIKE %s OR input_image LIKE %s
                       OR example_image LIKE %s
                """, (like, like, like))
            else:
                cur.execute("SELECT MAX(is_paid) FROM pcq_questions "
                            "WHERE question_image LIKE %s", (like,))
            row = cur.fetchone()
        finally:
            cur.close()
            conn.close()
    except Exception:
        logger.exception("UPLOADS: premium image check failed")
        return False

    is_paid = row[0] if row and row[0] is not None else 1
    if not is_paid:
        return True

    email = session.get('user_email')
    if not email:
        return False
    try:
        from routes.exam_platform.placement_exam_portal.practice_coding.models import active_subscription
        return active_subscription(email) is not None
    except Exception:
        logger.exception("UPLOADS: subscription check failed")
        return False

def _user_folder_token(email):
    import re as _re
    import hashlib
    cleaned = _re.sub(r'[^A-Za-z0-9._-]', '_', str(email or 'unknown')).lstrip('.')
    digest = hashlib.sha1(str(email or 'unknown').encode('utf-8')).hexdigest()[:8]
    return f"{(cleaned[:60] or 'unknown')[:40]}_{digest}"


def _owns_private_upload(email, normalized):
    if os.path.basename(normalized).startswith(f"{email}_"):
        return True
    if _user_folder_token(email) in normalized.split('/')[:-1]:
        return True
    try:
        from routes.db_pool import get_connection
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT 1 FROM comm_attempt_details
                WHERE email = %s AND audio_response_path LIKE %s LIMIT 1
            """, (email, '%' + os.path.basename(normalized)))
            if cur.fetchone():
                return True
            cur.execute("""
                SELECT 1 FROM comm_proctoring_logs
                WHERE email = %s AND snapshot_path LIKE %s LIMIT 1
            """, (email, '%' + os.path.basename(normalized)))
            return cur.fetchone() is not None
        finally:
            cur.close()
            conn.close()
    except Exception:
        logger.exception("UPLOADS: ownership check failed")
        return False


@app.route('/static/uploads/<path:filename>')
def shared_uploads(filename):
    normalized = filename.replace('\\', '/')
    if any(normalized.startswith(prefix) for prefix in PRIVATE_UPLOAD_PREFIXES):
        email = session.get('user_email')
        if not email or not _owns_private_upload(email, normalized):
            logger.warning(f"UPLOADS BLOCKED: [{email or 'anonymous'}] tried to read private file {normalized!r}")
            abort(403)
    if any(normalized.startswith(prefix) for prefix in PREMIUM_UPLOAD_PREFIXES):
        if not _premium_upload_allowed(normalized):
            logger.warning(f"UPLOADS BLOCKED: [{session.get('user_email') or 'anonymous'}] "
                           f"tried to read paid question image {normalized!r}")
            abort(403)
    from routes.shared_files import ensure_local
    if not ensure_local(normalized):
        abort(404)
    response = send_from_directory(SHARED_UPLOADS, filename)
    if normalized.lower().endswith('.pdf'):
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'inline; filename="%s"' % os.path.basename(normalized)
    return response


@app.route('/healthz')
@limiter.exempt
def healthz():
    checks = {}
    status = 200
    try:
        from routes.db_pool import get_connection
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            cur.close()
        finally:
            conn.close()
        checks['database'] = 'ok'
    except Exception:
        logger.exception("HEALTHZ: database check failed")
        checks['database'] = 'down'
        status = 503
    checks['redis'] = 'ok' if is_redis_available else 'absent'
    return jsonify({'status': 'ok' if status == 200 else 'degraded', 'checks': checks}), status


_REQUIRED_PROD_VARS = ('RAZORPAY_KEY_ID', 'RAZORPAY_KEY_SECRET', 'MAIL_USERNAME',
                       'MAIL_PASSWORD', 'DATABASE_PASSWORD', 'DATABASE_NAME')

if _is_production:
    _missing = [name for name in _REQUIRED_PROD_VARS if not app.config.get(name)]
    if _missing:
        logger.critical("PRODUCTION CONFIG INCOMPLETE: %s not set. Payments or email "
                        "will fail until these are configured.", ', '.join(_missing))
    if not (os.environ.get('WEBSITE_URL') or '').strip():
        logger.warning("WEBSITE_URL is not set; emailed links fall back to the request host.")


_UNSAFE_METHODS = frozenset(('POST', 'PUT', 'PATCH', 'DELETE'))
_CROSS_SITE_ALLOWED = frozenset(('/api/purchase/webhook', '/practice-coding/api/subscribe/webhook'))


def _trusted_hosts():
    hosts = {request.host}
    site = (os.environ.get('WEBSITE_URL') or '').strip()
    if site:
        from urllib.parse import urlparse
        hosts.add(urlparse(site).netloc)
    return hosts


@app.before_request
def block_cross_site_writes():
    if request.method not in _UNSAFE_METHODS or request.path in _CROSS_SITE_ALLOWED:
        return None
    source = request.headers.get('Origin')
    if source is None:
        source = request.headers.get('Referer')
    if not source:
        return None
    from urllib.parse import urlparse
    host = urlparse(source).netloc if source != 'null' else ''
    if host and host in _trusted_hosts():
        return None
    logger.warning("CROSS-SITE WRITE BLOCKED: %s %s from %r (ip %s)", request.method, request.path, source, request.remote_addr)
    if request.is_json or request.headers.get('X-Requested-With') or request.path.startswith('/api/'):
        return jsonify({'error': 'Cross-site request blocked.'}), 403
    return 'Cross-site request blocked.', 403


_SESSION_KEYS = ('user_email', 'user_username', 'user_google_id', '_sid', 'test_token',
                 'current_test_attempt_number', 'test_popup_initiated', 'active_test_token')


@app.before_request
def enforce_single_session():
    if request.endpoint in (None, 'static') or 'user_email' not in session:
        return None
    from routes.session_guard import is_replaced
    if not is_replaced():
        return None
    email = session.get('user_email')
    for key in _SESSION_KEYS:
        session.pop(key, None)
    logger.info("SESSION GUARD: signed out an older session of %s", email)
    message = "You were signed out because this account signed in on another device."
    if request.is_json or request.headers.get('X-Requested-With') or request.path.startswith('/api/') or request.method != 'GET':
        return jsonify({'error': 'signed_out', 'message': message, 'redirect': url_for('users.user_login')}), 401
    flash(message, 'login_error')
    return redirect(url_for('users.user_login'))


@app.route('/robots.txt')
def robots_txt():
    body = "User-agent: *\nDisallow: /api/\nDisallow: /start-test/\nDisallow: /test-login/\nDisallow: /profile\nAllow: /\n"
    body += "Sitemap: %s/sitemap.xml\n" % _public_base()
    return app.response_class(body, mimetype='text/plain')


SITEMAP_ENDPOINTS = ('users.index', 'users.browse_courses', 'users.sapm_about', 'users.privacy_policy',
                     'users.terms_of_use', 'users.user_login', 'users.user_signup')


def _public_base():
    configured = (os.environ.get('WEBSITE_URL') or '').strip().rstrip('/')
    return configured or request.url_root.rstrip('/')


@app.route('/sitemap.xml')
def sitemap_xml():
    from xml.sax.saxutils import escape
    base = _public_base()
    entries = []
    for endpoint in SITEMAP_ENDPOINTS:
        try:
            entries.append('  <url><loc>%s</loc></url>' % escape(base + url_for(endpoint)))
        except BuildError:
            continue
    body = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + '\n'.join(entries) + '\n</urlset>\n')
    return app.response_class(body, mimetype='application/xml')


@app.route('/favicon.ico')
def favicon_ico():
    return redirect(url_for('static', filename='images/favicon-32.png'), code=301)


@app.after_request
def add_security_headers(response):
    path = request.path
    cacheable_static = (path.startswith('/static/')
                        and not path.startswith('/static/uploads/'))

    if cacheable_static:
        response.headers['Cache-Control'] = 'public, max-age=604800'
    else:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers.setdefault('Content-Security-Policy', "frame-ancestors 'self'; object-src 'none'; base-uri 'self'")
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), payment=(self "https://checkout.razorpay.com"), usb=()'
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


app.register_blueprint(users_bp)

try:
    from routes.exam_platform.placement_exam_portal.coding_portal import register as register_coding_portal
    register_coding_portal(app)
except Exception:
    logger.exception("Coding portal failed to register")

try:
    from routes.exam_platform.placement_exam_portal.practice_coding import register as register_practice_coding
    register_practice_coding(app)
except Exception:
    logger.exception("Practice coding platform failed to register")

try:
    from routes.exam_platform.placement_exam_portal.tcs_portal import register as register_tcs_portal
    register_tcs_portal(app)
except Exception:
    logger.exception("TCS portal failed to register")

from routes.courses_platform.utils.utils_token import generate_csrf_token


@app.context_processor
def inject_csrf_token():
    return {'csrf_token': generate_csrf_token}


try:
    from routes.courses_platform.payment.purchased_payment.payment_orders import start_reconcile_scheduler
    start_reconcile_scheduler(app)
except Exception:
    logger.exception("PAYMENT ORDERS: could not start the reconcile scheduler")

try:
    from routes.exam_platform.placement_exam_portal.coding_portal.routes.test import start_pending_grader
    start_pending_grader(app)
except Exception:
    logger.exception("PENDING GRADER: could not start")


def _safe_url(endpoint, fallback):
    try:
        return url_for(endpoint)
    except (BuildError, RuntimeError):
        logger.warning("Endpoint %s is not registered; falling back to %s", endpoint, fallback)
        return fallback


@app.context_processor
def inject_legal_urls():
    return {
        'terms_url': _safe_url('users.terms_of_use', '/terms'),
        'privacy_url': _safe_url('users.privacy_policy', '/privacy'),
    }


@app.before_request
def make_session_permanent():
    session.permanent = True


@app.before_request
def check_session_validity():
    if 'user_username' in session or 'user_email' in session:
        if not ('user_username' in session and 'user_email' in session):
            for key in ['user_username', 'user_email', 'user_google_id']:
                session.pop(key, None)
            session.modified = True
ERROR_COPY = {
    404: ("Page not found", "The page you are looking for does not exist or has moved."),
    500: ("Something went wrong", "An internal error occurred. Please try again in a moment."),
    403: ("Access denied", "You do not have permission to view this page."),
    401: ("Please sign in", "You need to be signed in to view this page."),
    400: ("Bad request", "That request could not be understood."),
    413: ("Upload too large", "That file is too large. Recordings and uploads must stay under 32 MB."),
    429: ("Too many requests", "You are doing that too often. Wait a moment and try again."),
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
        return render_template('users/auth/error.html',
                               error_code=code, error_title=title,
                               error_message=message), code
    except Exception:
        logger.exception("Could not render the %s page", code)
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


@app.errorhandler(401)
def unauthorized_error(error):
    return _error_response(401)


@app.errorhandler(400)
def handle_400(error):
    return _error_response(400)


@app.errorhandler(413)
def handle_413(error):
    return _error_response(413)


@app.errorhandler(429)
def handle_429(error):
    return _error_response(429)


if __name__ == '__main__':
    try:
        socketio.run(app, debug=False, port=5002, allow_unsafe_werkzeug=True,
                     use_reloader=not _is_production)
    except Exception as e:
        logger.exception("Failed to start the user application: %s", e)
