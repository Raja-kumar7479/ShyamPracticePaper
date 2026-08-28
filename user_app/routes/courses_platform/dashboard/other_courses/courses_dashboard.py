from flask import redirect, render_template, url_for
from routes.courses_platform.databases.enrollment_db import UserOperation
from routes.courses_platform.utils.utils_token import get_user_session
from routes.courses_platform.utils.utils_secure_code import secure_access_required
from routes import taxonomy
import logging
from datetime import datetime
from routes import users_bp

user_op = UserOperation()

logger = logging.getLogger(__name__)

@users_bp.route('/courses/<course_code>/<unique_code>')
@secure_access_required(('course_code', 'unique_code'))
def view_course_dashboard(course_code, unique_code):
    user_email, user_username, user_is_authenticated = get_user_session()
    course_code = course_code.upper()

    logger.info(f"Dashboard Access: User={user_email}, Course={course_code}")

    course_details = user_op.get_course_details(course_code)
    course_name = course_details['code'] if course_details else course_code
    group_name = course_details['name'] if course_details else ''
    
    available_practice_sections = user_op.get_practice_sections_for_code(course_code)
    question_sections = {}
    
    if 'Topic-wise' in available_practice_sections:
        question_sections['Topic-wise'] = url_for('users.browse_by_topic', unique_code=unique_code, course_code=course_code)
    if 'Subject-wise' in available_practice_sections:
        question_sections['Subject-wise'] = url_for('users.browse_by_subject', unique_code=unique_code, course_code=course_code)
    if 'Year-wise' in available_practice_sections:
        question_sections['Year-wise'] = url_for('users.browse_by_year', unique_code=unique_code, course_code=course_code)

    courses = user_op.get_free_courses_by_code(course_code)
    
    total_premium_count = len(user_op.get_paid_courses_by_code(course_code))

    purchased_titles = []
    platform_fee_paid = False
    if user_is_authenticated:
        purchased_titles = user_op.get_purchased_content_titles(user_email, course_code)
        for enr in user_op.get_enrolled_courses(user_email):
            if enr.get('code') == course_code and enr.get('payment_status') == 'Paid':
                platform_fee_paid = True
                break

    def generate_open_url(item):
        # The section decides the portal. Placement used to be routed by
        # searching the title for the word "coding", which mis-sent any test
        # whose title did not contain the expected keyword.
        section = item.get('section', '')
        url = taxonomy.open_url(section, item.get('section_id'),
                                course_code, unique_code, item.get('title'))
        if url:
            logger.info(f"Dashboard: {taxonomy.label_for(section)} URL for {item.get('title')!r}")
            return url
        logger.warning(f"Dashboard: no route for section {section!r} ({item.get('title')!r})")
        return '#'

    for c in courses:
        c['open_url'] = generate_open_url(c)
        # Practice banks and rounds are things a student attempts, so they
        # belong under Practice, not Study Materials.
        c['group'] = taxonomy.group_for(c.get('section', ''))
        # Only a proctored exam wants a window of its own; everything else
        # opened a needless new tab for every card.
        c['new_window'] = taxonomy.opens_in_new_window(c.get('section', ''))

    practice_items = [c for c in courses if c['group'] == 'practice']
    material_items = [c for c in courses if c['group'] == 'materials']
    logger.info(f"Dashboard: {course_code} split into {len(practice_items)} practice "
                f"and {len(material_items)} material resource(s)")

    current_hour = datetime.now().hour
    if 5 <= current_hour < 12:
        greeting = "Good Morning"
    elif 12 <= current_hour < 17:
        greeting = "Good Afternoon"
    elif 17 <= current_hour < 21:
        greeting = "Good Evening"
    else:
        greeting = "Hello"

    stats = {
        'total_resources': len(courses) + len(question_sections),
        'materials': len(material_items),
        'practice': len(practice_items) + len(question_sections),
        'free': len(courses),
        'premium': total_premium_count,
        'owned': len(purchased_titles)
    }

    return render_template(
        "users/courses_platform/dashboard/main.html",
        email=user_email,
        username=user_username,
        user_is_authenticated=user_is_authenticated,
        logged_in=user_is_authenticated,
        course_code=course_code,
        course_name=course_name,
        group_name=group_name,
        unique_code=unique_code,
        question_sections=question_sections,
        courses=courses,
        practice_items=practice_items,
        material_items=material_items,
        total_premium_count=total_premium_count,
        purchased_titles=purchased_titles,
        platform_fee_paid=platform_fee_paid,
        greeting=greeting,
        stats=stats
    )