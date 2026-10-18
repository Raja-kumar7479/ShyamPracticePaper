from flask import abort, flash, redirect, render_template, session, url_for
from routes.courses_platform.databases.enrollment_db import UserOperation
from routes.courses_platform.utils.utils_token import get_user_session
from routes.courses_platform.utils.utils_secure_code import secure_access_required
from routes import taxonomy
import logging
from datetime import datetime
from routes import users_bp
from routes.content_guard import content_unavailable, content_version, mark_new_content
from routes.courses_platform.payment.purchased_payment.utils.utils_cart import MAX_CART_ITEMS

user_op = UserOperation()

logger = logging.getLogger(__name__)

def _premium_card(course_code, email):
    try:
        from routes.exam_platform.premium_catalog import dashboard_premium
        return dashboard_premium(course_code, email)
    except Exception:
        logger.exception("DASHBOARD: premium card unavailable for %s", course_code)
        return None


@users_bp.route('/courses/<course_code>/<unique_code>')
@secure_access_required(('course_code', 'unique_code'))
def view_course_dashboard(course_code, unique_code):
    user_email, user_username, user_is_authenticated = get_user_session()
    course_code = course_code.upper()

    logger.info(f"Dashboard Access: User={user_email}, Course={course_code}")

    course_details = user_op.get_course_details(course_code)
    course_name = course_details['code'] if course_details else course_code
    group_name = course_details['name'] if course_details else ''
    
    question_sections = {}
    for fmt in user_op.get_practice_sections_for_code(course_code):
        section = (fmt.get('section') or '').strip()
        if not section:
            continue
        key = section.lower()
        endpoint = 'users.browse_by_year' if 'year' in key else ('users.browse_by_topic' if 'topic' in key else 'users.browse_by_subject')
        entry = question_sections.setdefault(section, {
            'link': url_for(endpoint, unique_code=unique_code, course_code=course_code), 'titles': []})
        title = (fmt.get('title') or '').strip()
        if title and title not in entry['titles']:
            entry['titles'].append(title)

    purchased_titles = []
    subscribed = False
    if user_is_authenticated:
        purchased_titles = user_op.get_purchased_content_titles(user_email, course_code) or []
        from routes.exam_platform.subscription_access import has_platform_subscription
        subscribed = bool(has_platform_subscription(user_email, course_code))

    courses = user_op.get_free_courses_by_code(course_code, include_hidden=subscribed)
    for c in courses:
        c['hidden'] = (c.get('status') or '').lower() != 'active'
    kept = sum(1 for c in courses if c['hidden'])
    if kept:
        logger.info(f"Dashboard: {user_email} keeps {kept} hidden item(s) in {course_code} through premium")

    paid_items = [p for p in user_op.get_paid_courses_by_code(course_code, include_hidden=bool(purchased_titles))
                  if (p.get('status') or '').lower() == 'active' or p.get('title') in purchased_titles]
    for p in paid_items:
        price = float(p.get('price') or 0)
        off = float(p.get('discount') or 0)
        p['hidden'] = (p.get('status') or '').lower() != 'active'
        p['bought'] = p.get('title') in purchased_titles
        p['pay'] = round(price - price * off / 100, 2) if 0 < off < 100 else price
        p['saved'] = round(price - p['pay'], 2)
    total_premium_count = len(paid_items)
    logger.info(f"Dashboard: {course_code} lists {len(paid_items)} paid item(s), "
                f"{sum(1 for p in paid_items if p['bought'])} already bought by {user_email}")

    def generate_open_url(item):
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
        c['group'] = taxonomy.group_for(c.get('section', ''))
        c['new_window'] = taxonomy.opens_in_new_window(c.get('section', ''))

    mark_new_content(courses)
    mark_new_content(paid_items)
    for p in paid_items:
        p['group'] = taxonomy.group_for(p.get('section', ''))

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
        content_version=content_version(course_code),
        premium_card=_premium_card(course_code, user_email),
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
        paid_items=paid_items,
        total_premium_count=total_premium_count,
        purchased_titles=purchased_titles,
        greeting=greeting,
        stats=stats
    )

@users_bp.route('/courses/<course_code>/<unique_code>/resource/<section_id>')
@secure_access_required(('course_code', 'unique_code'))
def view_content_details(course_code, unique_code, section_id):
    user_email, user_username, user_is_authenticated = get_user_session()

    content = user_op.get_content_by_section_id(section_id, course_code)
    if not content:
        return content_unavailable(course_code, unique_code, section_id, user_email)

    purchased_titles = user_op.get_purchased_content_titles(user_email, course_code) if user_email else []
    has_bought = content.get('title') in (purchased_titles or [])
    is_paid = (content.get('label') or '').lower() == 'paid'

    if (content.get('status') or '').lower() != 'active' and not has_bought:
        from routes.exam_platform.subscription_access import has_platform_subscription
        if not has_platform_subscription(user_email, course_code):
            return content_unavailable(course_code, unique_code, section_id, user_email, reason='hidden')

    can_open = has_bought or not is_paid
    in_cart = False
    cart_is_full = False
    if is_paid and not has_bought and user_email:
        cart_items = session.get(f'user_{user_email}_cart', []) or []
        in_cart = content.get('title') in [item.get('title') for item in cart_items]
        cart_is_full = len(cart_items) >= MAX_CART_ITEMS

    mark_new_content([content])

    from routes.exam_platform.premium_portal import render_premium_links
    content['details'] = render_premium_links(content.get('details'), course_code,
                                              unique_code, content.get('section_id'),
                                              enabled=not is_paid)

    section = content.get('section', '')
    open_url = ''
    if can_open:
        open_url = taxonomy.open_url(section, content.get('section_id'), course_code,
                                     unique_code, content.get('title')) or ''
        if not open_url:
            logger.warning(f"CONTENT PAGE: no route for section {section!r} ({content.get('title')!r})")

    logger.info(f"CONTENT PAGE: [{user_email}] opened {content.get('title')!r} ({section})")
    return render_template(
        'users/courses_platform/dashboard/content_details.html',
        content=content,
        course_code=course_code,
        unique_code=unique_code,
        username=user_username,
        logged_in=user_is_authenticated,
        section_label=taxonomy.label_for(section),
        open_url=open_url,
        is_paid=is_paid,
        can_open=can_open,
        in_cart=in_cart,
        cart_is_full=cart_is_full,
        new_window=taxonomy.opens_in_new_window(section),
        dashboard_url=url_for('users.view_course_dashboard', course_code=course_code, unique_code=unique_code),
    )


@users_bp.route('/courses/<course_code>/<unique_code>/content-version')
@secure_access_required(('course_code', 'unique_code'))
def course_content_version(course_code, unique_code):
    from flask import jsonify
    return jsonify({"version": content_version(course_code)})
