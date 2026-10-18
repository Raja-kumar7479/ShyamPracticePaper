from flask import (
    jsonify,
    session,
)
from routes import users_bp
from routes.courses_platform.payment.purchased_payment.databases.payment_handler_db import UserOperation
from extensions import user_login_required, limiter
from routes.courses_platform.utils.utils_secure_code import secure_access_required
from routes.courses_platform.utils.utils_token import csrf_protected
from routes.courses_platform.payment.purchased_payment.utils.utils_cart import get_discount_percent, effective_price
import logging
import razorpay
import os
from routes.courses_platform.payment.purchased_payment.utils.utils_success import get_session_user, is_valid_session, calculate_final_price

logger = logging.getLogger(__name__)

user_op = UserOperation()

RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID")
RAZORPAY_SECRET = os.environ.get("RAZORPAY_SECRET")

if not RAZORPAY_KEY_ID or not RAZORPAY_SECRET:
    logger.critical("Razorpay credentials are not configured. Payment routes will be disabled.")
    razorpay_client = None
else:
    try:
        razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_SECRET))
    except Exception as e:
        logger.critical(f"Razorpay Client initialization failed: {e}")
        razorpay_client = None


def revalidate_session_coupon(email, cart_total):
    coupon_code = session.get('coupon_applied')
    if not coupon_code:
        session.pop('discount', None)
        return True
    coupons = user_op.get_coupon_by_code(coupon_code, email)
    coupon = coupons[0] if coupons else None
    if not coupon or cart_total < float(coupon['min_purchase']):
        for key in ['discount', 'coupon_applied', 'coupon_expiry']:
            session.pop(key, None)
        session.modified = True
        return False
    session['discount'] = float(coupon['discount'])
    session.modified = True
    return True


@users_bp.route('/create_payment_order/<course_code>/<unique_code>', methods=['POST'])
@limiter.limit("10 per minute")
@secure_access_required(('course_code', 'unique_code'))
@user_login_required
@csrf_protected
def create_payment_order(course_code, unique_code):
    username, email, phone = get_session_user()

    if not is_valid_session(username, email, phone):
        logger.warning(f"Invalid session for payment order creation for user {email}.")
        return jsonify({"error": "Session expired. Please login again."}), 401

    if not razorpay_client:
        return jsonify({"error": "Payment system unavailable. Please try again later."}), 503

    user_cart_key = f'user_{email}_cart'
    cart_courses = session.get(user_cart_key)

    if not cart_courses:
        logger.warning(f"Empty cart for payment order creation for user {email}.")
        return jsonify({"error": "No items in your cart."}), 400

    verified_cart = []
    for item in cart_courses:
        db_item = user_op.get_content_by_code_title_subtitle(
            course_code, item.get('title'), item.get('subtitle', '')
        )
        if not db_item or db_item.get('price') is None or float(db_item['price']) <= 0:
            logger.warning(f"Cart item no longer purchasable for user {email}: {item.get('title')!r}")
            return jsonify({"error": "An item in your cart is no longer available. Please review your cart."}), 400

        payable, saved = effective_price(db_item['price'], db_item.get('discount'))
        if payable <= 0:
            logger.warning(f"Cart item priced at zero after discount for user {email}: {item.get('title')!r}")
            return jsonify({"error": "An item in your cart is priced incorrectly. Please contact support."}), 400

        logger.info(
            f"ORDER ITEM: '{item.get('title')}' list={db_item['price']} "
            f"discount={db_item.get('discount')}% -> charging {payable}"
        )
        verified_cart.append({
            'title': item.get('title'),
            'subtitle': item.get('subtitle', ''),
            'price': payable,
            'list_price': float(db_item['price'] or 0),
            'item_discount': float(db_item.get('discount') or 0),
            'saved': saved,
            'section': db_item.get('section'),
            'section_id': db_item.get('section_id')
        })

    cart_total = sum(c['price'] for c in verified_cart)
    if not revalidate_session_coupon(email, cart_total):
        logger.warning(f"Coupon no longer valid at checkout for user {email}. Discount removed.")
        return jsonify({"error": "Your coupon is no longer valid. Please review your cart total and try again."}), 409

    discount = get_discount_percent()
    total_price, discount_amount, final_amount = calculate_final_price(verified_cart, discount)
    amount_in_paise = int(round(final_amount * 100))

    if amount_in_paise <= 0:
        logger.warning(f"Invalid payment amount (<=0) for user {email}.")
        return jsonify({"error": "Invalid payment amount."}), 400

    try:
        razorpay_order = razorpay_client.order.create({
            'amount': amount_in_paise,
            'currency': 'INR',
            'payment_capture': 1,
            'notes': {'email': email, 'course_code': course_code}
        })
    except Exception as e:
        logger.error(f"Razorpay order creation failed for user {email}: {e}")
        return jsonify({"error": "Payment gateway error. Try again."}), 500

    from routes.courses_platform.payment.purchased_payment.payment_orders import record_content_order
    if not record_content_order(email, username, phone, course_code, unique_code, razorpay_order['id'],
                                amount_in_paise, verified_cart, discount, total_price):
        logger.error(f"Order {razorpay_order['id']} for {email} could not be stored - refusing checkout")
        return jsonify({"error": "Payment could not be started. Please try again."}), 500

    session['pending_purchase'] = {
        'razorpay_order_id': razorpay_order['id'],
        'amount_in_paise': amount_in_paise,
        'course_code': course_code,
        'unique_code': unique_code,
        'cart': verified_cart,
        'discount': discount,
        'total_price': total_price,
        'final_amount': final_amount
    }
    session[user_cart_key] = verified_cart
    session.modified = True

    logger.info(f"Razorpay order {razorpay_order['id']} created for user {email}.")

    return jsonify({
        "status": "success",
        "razorpay_order_id": razorpay_order['id'],
        "razorpay_key_id": RAZORPAY_KEY_ID,
        "amount": amount_in_paise,
        "username": username,
        "email": email,
        "phone": phone,
        "course_code": course_code,
        "unique_code": unique_code
    })
