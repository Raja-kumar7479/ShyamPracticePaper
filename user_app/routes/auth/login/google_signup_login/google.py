import os
import pathlib
import requests
from flask import flash, render_template, session, abort, redirect, request, url_for
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
try:
    # The standalone package. This used to import pip's private vendored copy,
    # which breaks whenever pip changes or is absent, as in a slim image.
    import cachecontrol
except ImportError:  # pragma: no cover - last resort on older installs
    from pip._vendor import cachecontrol
import google.auth.transport.requests
import logging
from config import Config
from routes.auth.database.auth_db import AuthOperation
from routes.auth.utils.utils_login import is_safe_url, safe_next_url
from routes.exam_platform.competitive_exam_platform.utils.utils_test_dashboard import establish_user_session
from routes import users_bp
from flask_mail import Mail
from routes.auth.utils.utils_signup import send_signup_success_email

auth_db = AuthOperation()
mail = Mail()
logger = logging.getLogger(__name__)

# Allowing OAuth over plain HTTP is a local-development convenience. Forcing it
# on unconditionally also relaxed it in production, so it is gated on the same
# flag the rest of the app uses to detect a real deployment.
from config import Config as _Config
_IS_PRODUCTION = _Config.IS_PRODUCTION
if not _IS_PRODUCTION:
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

client_secrets_file = os.path.join(pathlib.Path(__file__).parent, "client_secret.json")

# Both non-OpenID scopes were malformed - "https.googleapis.com/..." has no
# "://" and "https://googleapis.com/..." is missing the www host - so Google
# rejected the request and sign-in always failed.
GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
]


def create_flow():
    return Flow.from_client_secrets_file(
        client_secrets_file=client_secrets_file,
        scopes=GOOGLE_SCOPES,
        redirect_uri=Config.REDIRECT_URI
    )

@users_bp.route('/google_login')
def google_login():
    try:
        flow = create_flow()
        next_url = request.args.get('next')
        if next_url and is_safe_url(next_url):
            session['user_login_next_url'] = next_url

        authorization_url, state = flow.authorization_url(prompt='consent', access_type='offline', include_granted_scopes='true')
        session["user_google_state"] = state
        return redirect(authorization_url)
    except Exception:
        return render_template("users/auth/error.html", error_message="Could not initialize Google Login.")

@users_bp.route("/callback")
def callback():
    try:
        if session.get("user_google_id"):
            return redirect(url_for('users.index'))

        state_from_session = session.get("user_google_state")
        state_from_request = request.args.get("state")

        if not state_from_session or state_from_session != state_from_request:
            flash("Login session invalid. Please try again.", "login_error")
            return redirect(url_for('users.user_login'))

        session.pop('user_google_state', None)
        flow = create_flow()
        flow.fetch_token(authorization_response=request.url)
        
        credentials = flow.credentials
        request_session = requests.session()
        token_request = google.auth.transport.requests.Request(session=cachecontrol.CacheControl(request_session))
        
        id_info = id_token.verify_oauth2_token(credentials._id_token, token_request, Config.GOOGLE_CLIENT_ID)
        
        if not id_info.get("email_verified"):
            abort(403, description="Email not verified")
            
        user_email = id_info.get("email")
        user_name = id_info.get("name")
        user_oauth_id = id_info.get("sub")
        
        existing_user = auth_db.get_user_by_email(user_email)
        is_new_user = False
        
        if existing_user:
            auth_type = existing_user.get("auth_type", "manual").lower()
            if auth_type == "manual":
                auth_db.update_auth_type_to_both(user_email, user_oauth_id)
        else:
            is_new_user = True
            auth_db.insert_user_google(user_name, user_email, user_oauth_id)
            try:
                send_signup_success_email(user_name, user_email, mail)
            except Exception:
                pass
                
        establish_user_session(user_email, user_name)
        from routes.auth.utils.utils_login import rebuild_session_at_login
        rebuild_session_at_login()
        session["user_google_id"] = user_oauth_id
        session['user_username'] = user_name
        session['user_email'] = user_email
        session.permanent = True
        
        next_url = session.pop('user_login_next_url', None)
        flash("Login successful via Google!", "login_success")
        
        return redirect(safe_next_url(next_url, url_for('users.index')))
    except Exception as e:
        logger.error(f"Google Callback Error: {e}")
        return render_template("users/auth/error.html", error_message="Google Login failed.")