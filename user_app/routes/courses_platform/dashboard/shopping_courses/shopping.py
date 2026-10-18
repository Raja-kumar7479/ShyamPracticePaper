from flask import flash, redirect, render_template, request, url_for, session
from routes.courses_platform.databases.enrollment_db import UserOperation
from routes.courses_platform.utils.utils_token import get_user_session
from routes.courses_platform.utils.utils_secure_code import secure_access_required
from routes.courses_platform.payment.purchased_payment.utils.utils_cart import MAX_CART_ITEMS
from routes import users_bp
from routes.content_guard import mark_new_content
import logging

user_op = UserOperation()
logger = logging.getLogger(__name__)

@users_bp.route('/course_shop/<course_code>/<unique_code>')
@secure_access_required(('course_code', 'unique_code'))
def course_shop(course_code, unique_code):
    user_email, user_username, user_is_authenticated = get_user_session()
    search_query = request.args.get('q', '').lower()

    try:
        all_paid_courses = user_op.get_paid_courses_by_code(course_code, include_hidden=bool(user_is_authenticated))
    except Exception:
        all_paid_courses = []
    for course in all_paid_courses:
        course['hidden'] = (course.get('status') or '').lower() != 'active'
    
    purchased_courses = []
    available_courses = []
    
    cart_titles = []
    cart_count = 0
    
    if user_is_authenticated and user_email:
        user_cart_key = f'user_{user_email}_cart'
        cart_items = session.get(user_cart_key, [])
        cart_titles = [item.get('title') for item in cart_items]
        cart_count = len(cart_items)

    if user_is_authenticated:
        for course in all_paid_courses:
            if search_query and search_query not in course.get('title', '').lower():
                continue

            try:
                is_purchased = user_op.is_course_purchased_securely(
                    user_email,
                    course_code,
                    course['title'],
                    course['subtitle']
                )
                
                if is_purchased:
                    purchased_courses.append(course)
                elif not course['hidden']:
                    available_courses.append(course)
            except Exception:
                if not course['hidden']:
                    available_courses.append(course)
    else:
        for course in all_paid_courses:
            if search_query and search_query not in course.get('title', '').lower():
                continue
            available_courses.append(course)

    try:
        course_details = user_op.get_course_details(course_code)
        course_name = course_details['code'] if course_details else course_code
    except Exception:
        course_name = course_code

    mark_new_content(available_courses)

    return render_template(
        'users/courses_platform/dashboard/shop.html',
        purchased_courses=purchased_courses,
        available_courses=available_courses,
        cart_titles=cart_titles, 
        cart_count=cart_count,
        username=user_username,
        user_is_authenticated=user_is_authenticated,
        course_code=course_code.upper(),
        course_name=course_name,
        unique_code=unique_code,
        max_cart_items=MAX_CART_ITEMS,
        cart_is_full=cart_count >= MAX_CART_ITEMS
    )