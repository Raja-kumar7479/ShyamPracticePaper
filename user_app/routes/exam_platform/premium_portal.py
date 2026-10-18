import logging

from flask import jsonify, redirect, render_template, request, session, url_for

from routes import users_bp
from routes.db_pool import get_connection
from routes.exam_platform.competitive_exam_platform.utils.utils_secure_code import secure_access_required
from routes.exam_platform.placement_exam_portal.practice_coding import models
from routes.exam_platform.placement_exam_portal.practice_coding.auth import (
    csrf_protect, current_user, login_required)
from routes.exam_platform.placement_exam_portal.practice_coding.routes_billing import (
    confirm_subscription_payment, start_subscription_order, subscription_receipt_file)
from extensions import limiter

logger = logging.getLogger(__name__)

SUBSCRIBE_TOKEN = '[[SUBSCRIBE]]'

PREMIUM_LINK_TOKEN = '[[PREMIUM]]'


def render_premium_links(html, course_code, unique_code, section_id=None, label='Premium details', enabled=True):
    text = html or ''
    if PREMIUM_LINK_TOKEN not in text:
        return text
    if not enabled:
        return text.replace(PREMIUM_LINK_TOKEN, '')
    from flask import url_for
    from markupsafe import escape
    kwargs = {'course_code': course_code, 'unique_code': unique_code}
    if section_id:
        kwargs['from'] = section_id
    link = ('<a class="cd-premium-link" href="%s"><i class="fas fa-crown"></i> %s</a>'
            % (escape(url_for('users.premium_details_page', **kwargs)), escape(label)))
    return text.replace(PREMIUM_LINK_TOKEN, link)


def _clean_copy(html):
    return (html or '').replace(SUBSCRIBE_TOKEN, '')


def _course_name(course_code):
    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT name FROM courses WHERE code = %s LIMIT 1", (course_code,))
        row = cursor.fetchone()
        return (row or {}).get('name') or course_code
    except Exception:
        return course_code
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@users_bp.route('/courses/<course_code>/<unique_code>/premium')
@secure_access_required(('course_code', 'unique_code'))
def premium_details_page(course_code, unique_code):
    user = current_user()
    if not user:
        return redirect(url_for('users.user_login', next=request.url))

    from routes.exam_platform.placement_exam_portal.practice_coding import models_quiz
    from config import Config

    from routes.exam_platform.premium_catalog import premium_offer, renewal_state
    offer = premium_offer(course_code)
    if not offer['plans']:
        logger.info("PREMIUM PAGE: [%s] %s has no plan yet - coming soon shown", user['email'], course_code)
    copy = _clean_copy(offer['details'])
    current = models.active_subscription(user['email'], course_code)
    renewal = renewal_state(current) if current else {'days_left': None}
    dashboard_url = url_for('users.view_course_dashboard', course_code=course_code, unique_code=unique_code)
    logger.info("PREMIUM PAGE: [%s] opened premium for %s (catalog: %s)",
                user['email'], course_code, 'custom' if offer['custom'] else 'defaults')
    return render_template(
        'users/exam_platform/placement_exam_portal/practice_coding/premium.html',
        user=user, plans=offer['plans'],
        best_key=(offer['cheapest'] or {}).get('key'),
        subscription=current, days_left=renewal['days_left'],
        quiz_count=models_quiz.premium_quiz_count(),
        course_mode=True, course_code=course_code, course_name=_course_name(course_code), premium_copy=copy,
        premium_headline=offer['headline'],
        back_url=dashboard_url, back_label='Back to your course', from_course=True,
        next_url=dashboard_url,
        order_url=url_for('users.premium_order'),
        verify_url=url_for('users.premium_verify'),
        razorpay_key=getattr(Config, 'RAZORPAY_KEY_ID', '') or '')


@users_bp.route('/courses/<course_code>/<unique_code>/premium/subscribe')
def premium_plans_page(course_code, unique_code):
    return redirect(url_for('users.premium_details_page', course_code=course_code,
                            unique_code=unique_code, **request.args.to_dict()))


@users_bp.route('/api/premium/order', methods=['POST'])
@login_required
@csrf_protect
@limiter.limit('10 per minute')
def premium_order(**kwargs):
    body, status = start_subscription_order(current_user(), request.get_json(silent=True) or {})
    return jsonify(body), status


@users_bp.route('/api/premium/verify', methods=['POST'])
@login_required
@csrf_protect
@limiter.limit('10 per minute')
def premium_verify(**kwargs):
    body, status = confirm_subscription_payment(current_user(), request.get_json(silent=True) or {})
    return jsonify(body), status


@users_bp.route('/premium/receipt/<payment_id>')
@login_required
def premium_receipt(payment_id):
    return subscription_receipt_file(current_user(), payment_id)
