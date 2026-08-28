import logging
import re
import time
import os
import hmac
import base64
import uuid
import hashlib
import secrets
from functools import wraps
from flask import request, session, redirect, url_for, flash, abort, current_app
from routes.auth.database.auth_db import AuthOperation
from routes.courses_platform.databases.enrollment_db import UserOperation

logger = logging.getLogger(__name__)

user_op_auth = AuthOperation()
user_op_enroll = UserOperation()

def secure_access_required(param_names=('course_code', 'unique_code')):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            course = kwargs.get(param_names[0])
            code = kwargs.get(param_names[1])

            if not course or not code:
                logger.warning(f"SECURITY: Missing params. Course: {course}, Code: {code}")
                flash("Invalid access parameters.", "error")
                return redirect(url_for('users.index'))
            
            course = course.upper().strip()
            
            if len(code) < 6 or not re.match(r'^[A-Za-z0-9_-]+$', code):
                 logger.warning(f"SECURITY: Invalid code format. Code: {code}")
                 flash("Invalid access code format.", "error")
                 return redirect(url_for('users.index'))

            user_email = session.get('user_email')
            access_granted = False

            if user_email and not user_email.startswith("guest_"):
                stored_code = user_op_enroll.get_user_unique_code(user_email, course)
                if stored_code:
                    if stored_code == code:
                        access_granted = True
                        logger.info(f"SECURITY: User access granted for {user_email} in {course}.")
                    else:
                        logger.info(f"SECURITY: Mismatch for user {user_email}. Redirecting to correct code.")
                        new_url = request.path.replace(code, stored_code)
                        return redirect(new_url)
                else:
                    logger.info(f"SECURITY: User {user_email} not enrolled in {course}.")
            
            if not access_granted:
                correct_guest_code = user_op_enroll.get_guest_access_code(course)
                if correct_guest_code and code == correct_guest_code:
                    access_granted = True
                    logger.info(f"SECURITY: Guest access granted for {course}")
                else:
                    logger.warning(f"SECURITY FAIL: Access denied. Course: {course}, Provided: {code}. User redirected.")

            if not access_granted:
                time.sleep(0.5) 
                flash("Unauthorized access. Please enroll or check the link.", "error")
                if user_email and not user_email.startswith("guest_"):
                    return redirect(url_for('users.profile_view'))
                return redirect(url_for('users.index'))

            return f(*args, **kwargs)
        return wrapped
    return decorator