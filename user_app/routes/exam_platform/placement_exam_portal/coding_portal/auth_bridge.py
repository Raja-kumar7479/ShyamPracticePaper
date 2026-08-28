"""Bridges the coding portal to the application's existing session auth.

The standalone compiler shipped its own `auth.py` with a `users` table,
bcrypt login and registration. This app already has all of that (the `auth`
table plus `session['user_email']`), so instead of a second auth system the
coding portal reuses it: this module exposes the same names the ported
blueprints import (`login_required`, `current_user`) but
resolves identity from the existing session.
"""
import logging
from functools import wraps

from flask import session, jsonify, redirect, url_for, request

from routes.db_pool import get_connection

logger = logging.getLogger(__name__)


def _wants_json():
    return (request.path.startswith("/api/")
            or request.is_json
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or request.accept_mimetypes.best == "application/json")


def current_user():
    """The signed-in student as the coding portal expects: {id, username, email, role}.

    `id` is the primary key from the app's own `auth` table, so coding
    attempts/answers are tied to the same user record as everything else.
    """
    email = session.get("user_email")
    username = session.get("user_username")
    if not email or str(email).startswith("guest_"):
        return None

    # Resolve the id from the email every time rather than trusting a cached id.
    # A cached id goes stale if the account is deleted (and perhaps recreated
    # with a new id), which then breaks foreign keys when an attempt is
    # inserted. Looking it up by email keeps the session self-healing.
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT id, username, email FROM auth WHERE email = %s LIMIT 1",
                    (email,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not row:
        logger.warning("CODING AUTH: no auth row for %s", email)
        session.pop("_coding_user_id", None)
        return None

    session["_coding_user_id"] = row["id"]
    session["_coding_role"] = "candidate"
    return {"id": row["id"], "username": row["username"] or username or email,
            "email": row["email"], "role": "candidate"}


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user():
            if _wants_json():
                return jsonify({"error": "Your session expired. Please log in again."}), 401
            return redirect(url_for("users.user_login", next=request.url))
        return f(*args, **kwargs)
    return wrapper


def csrf_protect(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        from routes.courses_platform.utils.utils_token import validate_csrf_token
        token = (request.headers.get("X-CSRFToken")
                 or request.args.get("csrf")
                 or request.form.get("csrf_token"))
        if not token and request.is_json:
            data = request.get_json(silent=True)
            if isinstance(data, dict):
                token = data.get("csrf_token")
        if not validate_csrf_token(token or ""):
            logger.warning("CODING CSRF BLOCKED: %s %s from %s",
                           request.method, request.path, request.remote_addr)
            return jsonify({"error": "Session expired. Refresh the page and try again."}), 403
        return f(*args, **kwargs)
    return wrapper


# There is deliberately no admin_required here any more. It existed only to
# bolt the door shut on the ported compiler's authoring screens, and those
# screens have been removed: coding tests and questions are authored in the
# admin app, which writes the same cp_* tables this portal reads.
