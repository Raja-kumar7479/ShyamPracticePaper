"""Session auth for the practice platform.

Own copy rather than an import from the exam portal, so the two packages stay
fully independent as required. Resolves the logged-in student from the same
session keys the rest of the app writes.
"""
from functools import wraps

from flask import jsonify, redirect, request, session, url_for

from routes.db_pool import get_connection


def current_user():
    email = session.get("user_email")
    username = session.get("user_username")
    if not email or str(email).startswith("guest_"):
        return None
    # Resolve the id by email every time: a cached id goes stale if the account
    # is deleted/recreated, which then fails foreign keys on insert.
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
        session.pop("_pcp_user_id", None)
        return None
    session["_pcp_user_id"] = row["id"]
    return {"id": row["id"], "username": row["username"] or username or email,
            "email": row["email"]}


def _wants_json():
    # The practice APIs live under /practice-coding/api/, so a prefix check
    # on /api/ alone would send JSON callers an HTML login redirect.
    return ("/api/" in request.path
            or request.is_json
            or request.headers.get("X-Requested-With") == "XMLHttpRequest")


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            if _wants_json():
                return jsonify({"error": "Please log in to continue."}), 401
            return redirect(url_for("users.user_login", next=request.url))
        return f(*args, **kwargs)
    return wrapper


def csrf_protect(f):
    """Rejects state-changing calls whose X-CSRFToken does not match the
    session token. Pages embed the token via the app-wide csrf_token() helper;
    the JS sends it back in a header. Delegates to the app's own validator so
    one session token covers both normal forms and these APIs."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        from routes.courses_platform.utils.utils_token import validate_csrf_token
        if not validate_csrf_token(request.headers.get("X-CSRFToken", "")):
            import logging
            logging.getLogger(__name__).warning(
                "PRACTICE CSRF BLOCKED: %s %s", request.method, request.path)
            return jsonify({"error": "Session expired. Refresh the page and try again."}), 403
        return f(*args, **kwargs)
    return wrapper
