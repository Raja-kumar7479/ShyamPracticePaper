from flask import (
    jsonify,
    request,
    session,
)
from routes import users_bp
from routes.courses_platform.payment.purchased_payment.databases.payment_handler_db import UserOperation
from extensions import user_login_required, limiter
from routes.courses_platform.utils.utils_secure_code import secure_access_required
from routes.courses_platform.utils.utils_token import csrf_protected
import logging

logger = logging.getLogger(__name__)

user_op = UserOperation()

@users_bp.route('/get_coupons')
@user_login_required
def get_coupons():
    user_email = session.get('user_email')
    if not user_email:
        logger.warning("Unauthorized attempt to get coupons. User not logged in.")
        return jsonify({"error": "Unauthorized"}), 401
    coupons = user_op.get_all_active_coupons(user_email)
    formatted_coupons = []
    for coupon in coupons:
        coupon_dict = coupon.copy()
        if 'expiry_date' in coupon and coupon['expiry_date']:
            if hasattr(coupon['expiry_date'], 'strftime'):
                coupon_dict['expiry_date'] = coupon['expiry_date'].strftime('%Y-%m-%d')
        formatted_coupons.append(coupon_dict)
    logger.info(f"Coupons fetched for user {user_email}.")
    return jsonify({"coupons": formatted_coupons})

@users_bp.route('/apply_coupon/<course_code>/<unique_code>', methods=['POST'])
@limiter.limit("10 per minute")
@user_login_required
@secure_access_required(('course_code', 'unique_code'))
@csrf_protected
def apply_coupon(course_code, unique_code):
    user_email = session.get('user_email')
    if not user_email:
        logger.warning("Unauthorized attempt to apply coupon. User not logged in.")
        return jsonify({"status": "fail", "message": "Unauthorized"}), 401
    coupon_code = request.form.get('coupon_code')
    if not coupon_code:
        logger.warning("Coupon application failed: No coupon provided.")
        return jsonify({"status": "fail", "message": "No coupon provided"}), 400
    coupons = user_op.get_coupon_by_code(coupon_code, user_email)
    if not coupons:
        logger.warning(f"Coupon application failed for user {user_email}: Invalid or expired coupon code {coupon_code}.")
        return jsonify({"status": "fail", "message": "Invalid or expired coupon"}), 404
    user_cart_key = f'user_{user_email}_cart'
    cart_courses = session.get(user_cart_key, [])
    total_price = sum(c.get('price', 0) for c in cart_courses)
    valid_coupon = next((c for c in coupons if total_price >= c.get('min_purchase', 0)), None)
    if not valid_coupon:
        min_purchase = coupons[0]['min_purchase']
        logger.warning(f"Coupon application failed for user {user_email}: Minimum purchase not met for coupon {coupon_code}.")
        return jsonify({
            "status": "fail",
            "message": f"Minimum purchase ₹{min_purchase:.2f} required to apply this coupon."
        }), 400
    session['discount'] = float(valid_coupon['discount'])
    session['coupon_applied'] = valid_coupon['coupon_code']
    session['coupon_expiry'] = (
        valid_coupon['expiry_date'].strftime('%Y-%m-%d') if hasattr(valid_coupon['expiry_date'], 'strftime') else valid_coupon['expiry_date']
    )
    logger.info(f"Coupon {coupon_code} applied successfully for user {user_email}.")
    return jsonify({
        "status": "success",
        "discount": valid_coupon['discount'],
        "coupon": valid_coupon['coupon_code'],
        "expiry_date": session['coupon_expiry']
    })