from flask import flash, jsonify, redirect, render_template, request, session, url_for
from routes.courses_platform.payment.purchased_payment.databases.payment_handler_db import UserOperation
from routes.courses_platform.payment.purchased_payment.utils.utils_cart import  add_to_cart, remove_from_cart, clear_cart, apply_coupon, clean_field, get_discount_percent
from routes.courses_platform.utils.utils_secure_code import secure_access_required
from routes.courses_platform.utils.utils_token import csrf_protected
from extensions import user_login_required
from routes import users_bp
from routes.courses_platform.databases.enrollment_db import UserOperation as EnrollUserOperation
from routes.courses_platform.payment.purchased_payment.utils.utils_phone import validate_phone_number,validate_phone
import logging

logger = logging.getLogger(__name__)

user_op = UserOperation()
enroll_user_op = EnrollUserOperation()

@users_bp.route('/add_cart/<course_code>/<unique_code>', methods=['GET', 'POST'])
@secure_access_required(('course_code', 'unique_code'))
@user_login_required
@csrf_protected
def add_cart(course_code, unique_code):
    email = session.get('user_email')
    username = session.get('user_username')
    phone = session.get('validated_phone')

    if not email:
        session['redirect_after_login'] = request.url
        flash("You must be logged in to add items to your cart.", "cart_warning")
        return redirect(url_for('users.user_login'))

    stored_code = enroll_user_op.get_user_unique_code(email, course_code)

    if stored_code != unique_code:
        flash("Unauthorized access detected!", "cart_warning")
        logger.warning(f"Unauthorized access to add_cart for user {email} with invalid code.")
        return redirect(url_for('users.course_shop', course_code=course_code, unique_code=unique_code))

    user_cart_key = f'user_{email}_cart'
    cart_courses = session.get(user_cart_key, [])

    if not cart_courses:
        session.pop('show_billing', None)

    if request.method == 'POST':
        form = request.form

        if 'apply_coupon' in form:
            apply_coupon(user_cart_key, form.get('coupon_code'), email)
            logger.info(f"Coupon applied for user {email}.")
            return redirect(url_for('users.add_cart', course_code=course_code, unique_code=unique_code))

        if 'remove_coupon' in form:
            for key in ['discount', 'coupon_applied', 'coupon_expiry']:
                session.pop(key, None)
            flash("Coupon removed.", "cart_notification")
            logger.info(f"Coupon removed for user {email}.")
            return redirect(url_for('users.add_cart', course_code=course_code, unique_code=unique_code))

        if 'add_cart' in form:
            title = clean_field(form.get('title'))
            subtitle = clean_field(form.get('subtitle'))

            purchase_check = user_op.is_course_purchased_securely(email, course_code, title, subtitle)
            if purchase_check:
                flash("You have already purchased this course.", "cart_warning")
                logger.info(f"User {email} attempted to add an already purchased course to cart: {title}.")
                return redirect(url_for('users.course_shop', course_code=course_code, unique_code=unique_code))

            if add_to_cart(user_cart_key, form, course_code):
                logger.info(f"User {email} added course '{title}' to cart.")
            return redirect(url_for('users.add_cart', course_code=course_code, unique_code=unique_code))

        if 'remove' in form:
            title = form.get('course_to_remove')
            cart_courses = remove_from_cart(user_cart_key, title, email)
            logger.info(f"User {email} removed course '{title}' from cart.")

            if not cart_courses:
                session.pop('show_billing', None)
                flash("Your cart is now empty.", "cart_info")
                logger.info(f"Cart is now empty for user {email}.")
                return redirect(url_for('users.course_shop', course_code=course_code, unique_code=unique_code))
            
            return redirect(url_for('users.add_cart', course_code=course_code, unique_code=unique_code))

        if 'clear_cart' in form:
            clear_cart(user_cart_key)
            logger.info(f"Cart cleared for user {email}.")
            return redirect(url_for('users.course_shop', course_code=course_code, unique_code=unique_code))

    total_price = sum(c['price'] for c in session.get(user_cart_key, []))
    discount = get_discount_percent()
    discount_amount = round(total_price * discount / 100, 2)
    discounted_total = round(total_price - discount_amount, 2)

    available_coupons = user_op.get_all_active_coupons(email)
    for c in available_coupons:
        c['formatted_expiry'] = c['expiry_date'].strftime('%d %b %Y') if hasattr(c['expiry_date'], 'strftime') else "No expiry"

    field_labels = {
        'title': 'Course Title',
        'subtitle': 'Overview',
        'price': 'Price (INR)',
        'manage': 'Action'
    }

    logger.info(f"Rendering add_cart page for user {email}.")
    return render_template('users/courses_platform/payment/addcart.html',
        added_courses=session.get(user_cart_key, []),
        total_price=total_price,
        discount=discount,
        discount_amount=discount_amount,
        discounted_total=discounted_total,
        coupons=available_coupons,
        course_code=course_code,
        unique_code=unique_code,
        username=username,
        email=email,
        phone=phone,
        field_labels=field_labels,
        show_billing=request.args.get('show_billing', 'false'),
        coupon_applied=session.get('coupon_applied'),
        coupon_expiry=session.get('coupon_expiry')
    )