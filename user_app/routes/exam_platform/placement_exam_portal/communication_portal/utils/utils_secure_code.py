import logging
import time
from functools import wraps
from flask import request, session, redirect, url_for, flash
from routes.courses_platform.databases.enrollment_db import UserOperation

logger = logging.getLogger(__name__)

user_op_enroll = UserOperation()

def secure_access_required(param_names=('course_code', 'unique_code')):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            raw_course = kwargs.get(param_names[0])
            raw_code = kwargs.get(param_names[1])

            if not raw_course or not raw_code:
                flash("Invalid access parameters.", "error")
                return redirect(url_for('users.index'))
            
            course = str(raw_course).strip().upper()
            code = str(raw_code).strip()
            
            sess_code = str(session.get('unique_code', '')).strip()
            sess_course = str(session.get('course_code', '')).strip().upper()
            user_email = session.get('user_email')

            access_granted = False

            if user_email and not user_email.startswith("guest_"):
                stored_code = user_op_enroll.get_user_unique_code(user_email, course)
                if stored_code and (stored_code == code or sess_code == code):
                    access_granted = True

            if not access_granted:
                db_guest_code = user_op_enroll.get_guest_access_code(course)
                
                if db_guest_code and str(db_guest_code).strip() == code:
                    access_granted = True
                    session['unique_code'] = code
                    session['course_code'] = course
                
                elif sess_code == code and sess_course == course:
                    access_granted = True

            if not access_granted:
                logger.warning(f"SECURITY FAIL: Access denied. Course: {course}, Provided: {code}. Session: {sess_code}")
                time.sleep(0.5) 
                flash("Unauthorized access.", "error")
                return redirect(url_for('users.index'))

            return f(*args, **kwargs)
        return wrapped
    return decorator