import hashlib
import logging
import uuid
import time
import re
from functools import wraps
from flask import render_template, request, session, redirect, url_for, jsonify, Blueprint, flash
from flask import request, session, redirect, url_for, flash
from routes.practice_question_platform.databases.question_handler_db import UserOperation as PracticeUserOperation

logger = logging.getLogger(__name__)

user_op_enroll = PracticeUserOperation()

def generate_guest_identity():
    unique_id = str(uuid.uuid4())
    hashed = hashlib.sha256(unique_id.encode()).hexdigest()[:12]
    guest_email = f"guest_{hashed}@shyampp.com"
    guest_username = f"guest_{hashed[:6]}"

    return guest_email, guest_username

def get_user_session():
    user_email = session.get("user_email")
    user_username = session.get("user_username")
    user_is_authenticated = False

    if user_email and user_username and not user_email.startswith("guest_"):
        logger.info(f"USER_SESSION: Session valid for {user_email}")
        user_is_authenticated = True
        return user_email, user_username, user_is_authenticated
    else:
        if "guest_email" not in session or "guest_username" not in session:
            guest_email, guest_username = generate_guest_identity()
            session["guest_email"] = guest_email
            session["guest_username"] = guest_username
            logger.info(f"USER_SESSION: Generated new guest session {guest_email}")
        else:
            logger.info(f"USER_SESSION: Reusing existing guest session {session['guest_email']}")

        return session["guest_email"], session["guest_username"], user_is_authenticated

def check_session(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function

def _record_course_unlock(course_code):
    if not course_code:
        return
    cc = course_code.upper().strip()
    unlocked = session.get('pq_unlocked_courses') or []
    if cc not in unlocked:
        unlocked.append(cc)
        session['pq_unlocked_courses'] = unlocked
        session.modified = True


def has_question_access(course_code):
    if not course_code:
        return False
    cc = course_code.upper().strip()
    email = session.get('user_email')
    if email and not email.startswith('guest_'):
        if user_op_enroll.get_user_unique_code(email, cc):
            return True
    return cc in (session.get('pq_unlocked_courses') or [])


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
                        _record_course_unlock(course)
                        logger.info(f"SECURITY: User access granted for {user_email} in {course}.")
                    else:
                        logger.info(f"SECURITY: Mismatch for user {user_email}. Redirecting to correct code.")
                        new_url = request.path.replace(code, stored_code)
                        return redirect(new_url)
                else:
                    logger.info(f"SECURITY: User {user_email} not enrolled in {course}.")
            
            if not access_granted:
                correct_guest_code = user_op_enroll.get_guest_access_code(course)
                
                if not correct_guest_code:
                     expected_fallback = f"{course.lower()}Gst4XyZ"
                     if code == expected_fallback:
                         correct_guest_code = expected_fallback

                if correct_guest_code and code == correct_guest_code:
                    access_granted = True
                    _record_course_unlock(course)
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