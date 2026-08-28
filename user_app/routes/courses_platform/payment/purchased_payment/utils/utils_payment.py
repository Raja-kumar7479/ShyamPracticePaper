import logging
import random
import string
from flask import session, flash, redirect, url_for
from routes.courses_platform.payment.purchased_payment.databases.payment_handler_db import UserOperation

user_op = UserOperation()
logger = logging.getLogger(__name__)


def is_user_logged_in():
    user_username = session.get('user_username')
    user_email = session.get('user_email')
    if not user_username or not user_email:
        logger.warning("Session expired: user is not logged in.")
        flash("Session expired. Please login again.", "login")
        return False, user_username, user_email
    logger.info(f"User {user_email} is logged in.")
    return True, user_username, user_email

def get_session_user():
    return session.get('user_username'), session.get('user_email'), session.get('validated_phone')

def is_valid_session(username, email, phone):
    return all([username, email, phone])

def calculate_final_price(cart_courses, discount=0):
    total = sum(c['price'] for c in cart_courses)
    discount_amount = round(total * discount / 100, 2)
    final_amount = round(total - discount_amount, 2)
    return total, discount_amount, final_amount

def generate_purchase_code(length=10):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


def clear_payment_session(user_cart_key):
    keys_to_clear = [
        user_cart_key,
        'razorpay_order_id',
        'current_course_payment',
        'discount',
        'coupon_applied',
        'coupon_expiry'
    ]

    for key in keys_to_clear:
        session.pop(key, None)
    logging.info(f"Cleared payment session keys including cart: {user_cart_key}")