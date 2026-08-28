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

    # A premium subscription is a purchase too. Redirecting on "no course
    # purchases" sent anyone who had only subscribed straight to the shop, so
    # they could never see the plan they paid for or download its receipt.
    subs = []
    try:
        from routes.exam_platform.placement_exam_portal.practice_coding import models as pcp_models
        subs = pcp_models.subscription_history(user_email)
    except Exception:
        logger.exception("PURCHASES: could not read practice subscriptions")

    if not purchases and not subs:
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

        # purchase.section is a snapshot taken at checkout, so it can still hold
        # a pre-enum spelling; taxonomy.normalize handles those.
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

        expiry_date = purchase.get('validity_expires_at')
        purchase['is_expired'] = False
        purchase['is_expiring_soon'] = False

        if expiry_date:
            if expiry_date < now:
                purchase['is_expired'] = True
            elif now <= expiry_date <= threshold:
                purchase['is_expiring_soon'] = True
                expiring_soon_count += 1

    # Grouped under the catalog's display label, so the dashboard says
    # "Coding Test" instead of the raw section key stored at checkout.
    grouped_purchases = defaultdict(list)
    for p in purchases:
        grouped_purchases[taxonomy.label_for(p.get('section'))].append(p)
    
    initials = "".join([name[0] for name in user_username.split()]).upper()

    # A practice-coding subscription is a purchase too, so it appears here as
    # its own card linking straight to the unlocked premium problems.
    practice_premium = None
    # Read once above; every subscription ever paid for stays listed so a
    # lapsed plan and its receipt remain in the student's own record.
    subscription_history = subs
    try:
        from routes.exam_platform.placement_exam_portal.practice_coding import models as pcp_models
        practice_premium = pcp_models.active_subscription(user_email)
    except Exception:
        logger.exception("PURCHASES: could not read practice subscription")

    logger.info(f"Displaying purchase dashboard for user {user_email}.")

    return render_template(
        'users/courses_platform/payment/purchase.html',
        practice_premium=practice_premium,
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