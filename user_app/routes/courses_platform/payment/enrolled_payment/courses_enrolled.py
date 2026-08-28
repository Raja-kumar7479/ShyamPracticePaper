from flask import jsonify, session
from routes import users_bp
from routes.courses_platform.payment.purchased_payment.databases.payment_handler_db import UserOperation
from extensions import user_login_required, limiter
from routes.courses_platform.utils.utils_secure_code import secure_access_required
from routes.courses_platform.payment.purchased_payment.utils.utils_cart import get_discount_percent, effective_price
from routes.courses_platform.utils.utils_token import csrf_protected
import logging
from routes.courses_platform.payment.purchased_payment.create_payment_order import (
    RAZORPAY_KEY_ID,
    razorpay_client,
    revalidate_session_coupon,
)
from routes.courses_platform.payment.purchased_payment.utils.utils_success import get_session_user, is_valid_session, calculate_final_price

logger = logging.getLogger(__name__)

user_op = UserOperation()


@users_bp.route('/checkout/create_order/<course_code>/<unique_code>', methods=['POST'])
@limiter.limit("10 per minute")
@user_login_required
@secure_access_required(('course_code', 'unique_code'))
@csrf_protected
def create_checkout_order(course_code, unique_code):
    username, email, phone = get_session_user()

    if not is_valid_session(username, email, phone):
        logger.warning(f"Invalid session for checkout order for user {email}.")
        return jsonify({"error": "Session expired. Please log in again."}), 401

    if not razorpay_client:
        return jsonify({"error": "Payment system unavailable. Please try again later."}), 503

    user_cart_key = f'user_{email}_cart'
    cart_courses = session.get(user_cart_key)

    if not cart_courses:
        logger.warning(f"Empty cart for checkout order for user {email}.")
        return jsonify({"error": "Your cart is empty. Please add items before checking out."}), 400

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
        logger.warning(f"Invalid payment amount ({amount_in_paise}) for user {email}.")
        return jsonify({"error": "Invalid payment amount."}), 400

    try:
        razorpay_order = razorpay_client.order.create({
            'amount':          amount_in_paise,
            'currency':        'INR',
            'payment_capture': 1,
            'notes':           {'email': email, 'course_code': course_code}
        })
    except Exception as e:
        logger.error(f"Razorpay order creation failed for user {email}: {e}")
        return jsonify({"error": "Payment gateway error. Please try again."}), 500

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
        "status":            "success",
        "razorpay_order_id": razorpay_order['id'],
        "razorpay_key_id":   RAZORPAY_KEY_ID,
        "amount":            amount_in_paise,
        "username":          username,
        "email":             email,
        "phone":             phone or '',
        "course_code":       course_code,
        "unique_code":       unique_code
    })
