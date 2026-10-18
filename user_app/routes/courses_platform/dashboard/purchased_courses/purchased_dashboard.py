import logging
from flask import flash, redirect, render_template, session, url_for
from routes.courses_platform.databases.enrollment_db import UserOperation
from routes.courses_platform.payment.purchased_payment.utils.utils_receipt import generate_download_token
from routes.courses_platform.utils.utils_secure_code import secure_access_required
from extensions import user_login_required
from routes import users_bp, taxonomy
from flask_mail import Mail
from collections import defaultdict
from datetime import datetime, timedelta

mail = Mail()
user_op = UserOperation()

logger = logging.getLogger(__name__)

@users_bp.route('/purchase/<course_code>/<unique_code>', methods=['GET'])
@secure_access_required(('course_code', 'unique_code'))
@user_login_required
def purchase_dashboard(course_code, unique_code):
    user_username = session.get('user_username')
    user_email = session.get('user_email')
    
    if not all([user_username, user_email]):
        flash("Please login to access purchases.", "login_warning")
        logger.warning("Unauthorized access to purchase dashboard - user not logged in.")
        return redirect(url_for('users.user_login'))

    purchases = user_op.get_all_purchases(user_email)
    pending_orders = []
    try:
        from routes.courses_platform.payment.purchased_payment.payment_orders import pending_orders_for
        pending_orders = pending_orders_for(user_email)
    except Exception:
        logger.exception(f"PURCHASES: could not read pending orders for {user_email}")

    subs = []
    try:
        from routes.exam_platform.placement_exam_portal.practice_coding import models as pcp_models
        subs = pcp_models.subscription_history(user_email)
    except Exception:
        logger.exception("PURCHASES: could not read practice subscriptions")

    if not purchases and not subs and not pending_orders:
        flash("No purchases found.", "cart_info")
        logger.info(f"No purchases found for user {user_email}.")
        return redirect(url_for('users.course_shop', course_code=course_code, unique_code=unique_code))

    total_purchases = len(purchases)
    total_spent = 0
    expiring_soon_count = 0
    now = datetime.now()
    threshold = now + timedelta(days=7)

    course_cache = {}

    def course_context(code):
        if code not in course_cache:
            try:
                stored_code = user_op.get_user_unique_code(user_email, code)
            except Exception as e:
                logger.warning(f"Could not resolve access code for {user_email} in {code}: {e}")
                stored_code = None
            try:
                details = user_op.get_course_details(code)
            except Exception as e:
                logger.warning(f"Could not resolve course details for {code}: {e}")
                details = None
            course_cache[code] = {
                'unique_code': stored_code,
                'group_name': (details or {}).get('name') or ''
            }
        return course_cache[code]

    def build_access_url(purchase):
        item_course = (purchase.get('course_code') or '').upper()
        section = (purchase.get('section') or '').strip().lower()
        section_id = purchase.get('section_id')

        if not item_course:
            return None

        context = course_context(item_course)
        item_unique = context['unique_code']
        if not item_unique:
            logger.info(f"User {user_email} no longer enrolled in {item_course}; access link hidden.")
            return None

        url = taxonomy.open_url(section, section_id, item_course, item_unique,
                                purchase.get('title'))
        if url:
            return url

        logger.info(
            f"No content route for section {section!r} (purchase {purchase.get('payment_id')}); "
            f"open link hidden for {user_email}."
        )
        return None

    for purchase in purchases:
        purchase['download_link'] = url_for(
            'users.download_receipt',
            payment_id=purchase['payment_id'],
            token=generate_download_token(purchase['payment_id'])
        )

        purchase['access_url'] = build_access_url(purchase)

        total_spent += float(purchase.get('final_price') or 0)

        purchase['kept'] = (purchase.get('content_status') or 'active').lower() != 'active'

    for sub in subs:
        total_purchases += 1
        total_spent += float(sub.get('amount_paise') or 0) / 100.0
        sub_expiry = sub.get('expires_at')
        if sub_expiry and now <= sub_expiry <= threshold:
            expiring_soon_count += 1

    grouped_purchases = defaultdict(list)
    for p in purchases:
        grouped_purchases[taxonomy.label_for(p.get('section'))].append(p)
    
    initials = "".join([name[0] for name in user_username.split()]).upper()

    practice_premium = None
    active_premiums = []
    subscription_history = subs
    try:
        from routes.exam_platform.placement_exam_portal.practice_coding import models as pcp_models
        from routes.exam_platform.premium_catalog import renewal_state
        from routes.courses_platform.databases.enrollment_db import UserOperation as _EnrollOps
        enroll_ops = _EnrollOps()
        for sub in pcp_models.active_subscriptions(user_email):
            sub = dict(sub)
            sub.update(renewal_state(sub))
            active_premiums.append(sub)
        practice_premium = active_premiums[0] if active_premiums else None
    except Exception:
        logger.exception("PURCHASES: could not read practice subscription")

    logger.info(f"Displaying purchase dashboard for user {user_email}.")

    return render_template(
        'users/courses_platform/payment/purchase.html',
        pending_orders=pending_orders,
        practice_premium=practice_premium,
        active_premiums=active_premiums,
        now=datetime.now(),
        subscription_history=subscription_history,
        grouped_purchases=grouped_purchases,
        course_code=course_code,
        unique_code=unique_code,
        username=user_username,
        initials=initials,
        total_purchases=total_purchases,
        total_spent=total_spent,
        expiring_soon_count=expiring_soon_count
    )