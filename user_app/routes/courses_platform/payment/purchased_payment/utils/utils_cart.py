import logging
from flask import flash, session
from routes.courses_platform.payment.purchased_payment.databases.payment_handler_db import UserOperation

user_op = UserOperation()
logger = logging.getLogger(__name__)

MAX_CART_ITEMS = 5


def effective_price(price, discount):
    try:
        price = float(price or 0)
        discount = float(discount or 0)
    except (TypeError, ValueError):
        logger.warning(f"Unreadable price/discount pair: {price!r}/{discount!r}; treating as no discount.")
        return round(float(price or 0), 2), 0.0
    if discount <= 0 or discount >= 100:
        return round(price, 2), 0.0
    saved = round(price * discount / 100.0, 2)
    return round(price - saved, 2), saved


def price_view(item):
    list_price = float(item.get('price') or 0)
    item_discount = float(item.get('discount') or 0)
    payable, saved = effective_price(list_price, item_discount)
    return {
        'list_price': list_price,
        'discount': item_discount,
        'payable': payable,
        'saved': saved,
        'has_discount': saved > 0,
    }

def is_user_logged_in():
    user_username = session.get('user_username')
    user_email = session.get('user_email')
    if not user_username or not user_email:
        logger.warning("Session expired: user is not logged in.")
        flash("Session expired. Please login again.", "login")
        return False, user_username, user_email
    logger.info(f"User {user_email} is logged in.")
    return True, user_username, user_email

def clean_field(value):
    value = (value or '').strip()
    return '' if value in ('None', 'null') else value

def get_discount_percent():
    try:
        discount = float(session.get('discount') or 0)
    except (TypeError, ValueError):
        logger.warning(f"Discarding unreadable discount in session: {session.get('discount')!r}")
        return 0.0
    if discount < 0 or discount > 100:
        logger.warning(f"Discarding out-of-range discount in session: {discount!r}")
        return 0.0
    return discount

def refresh_cart_prices(user_cart_key, course_code):
    cart_courses = session.get(user_cart_key, [])
    if not cart_courses:
        return cart_courses
    changed = False
    kept = []
    for item in cart_courses:
        data = user_op.get_content_by_code_title_subtitle(course_code, item.get('title'), item.get('subtitle', ''))
        if not data or data.get('price') is None:
            logger.info(f"CART REFRESH: '{item.get('title')}' is no longer for sale; removed from the cart")
            flash(f"'{item.get('title')}' is no longer available and was removed from your cart.", "cart_warning")
            changed = True
            continue
        kept.append(item)
        payable, saved = effective_price(data['price'], data.get('discount'))
        fresh = {
            'price': payable,
            'list_price': float(data['price'] or 0),
            'item_discount': float(data.get('discount') or 0),
            'saved': saved,
        }
        if any(item.get(k) != v for k, v in fresh.items()):
            logger.info(f"CART REFRESH: '{item.get('title')}' {item.get('price')} -> {payable} "
                        f"(list {fresh['list_price']}, {fresh['item_discount']}% off)")
            item.update(fresh)
            changed = True
    if changed:
        session[user_cart_key] = kept
        session.modified = True
    return kept


def add_to_cart(user_cart_key, form, course_code):
    cart_courses = session.get(user_cart_key, [])

    title = clean_field(form.get('title'))
    subtitle = clean_field(form.get('subtitle'))

    if not title:
        flash("Invalid item.", "cart_error")
        logger.warning(f"Add to cart failed: Missing title for session {user_cart_key}.")
        return False

    if any(c['title'] == title and c.get('subtitle', '') == subtitle for c in cart_courses):
        flash("Already in your cart.", "cart_warning")
        logger.warning(f"Attempt to add duplicate course '{title}' to cart for session {user_cart_key}.")
        return False

    if len(cart_courses) >= MAX_CART_ITEMS:
        flash(f"Cart limit is {MAX_CART_ITEMS} items. Checkout or remove one first.", "cart_warning")
        logger.info(f"Cart limit of {MAX_CART_ITEMS} reached for session {user_cart_key}.")
        return False

    item_data = user_op.get_content_by_code_title_subtitle(course_code, title, subtitle)

    if not item_data:
        flash("Item no longer available.", "cart_error")
        logger.warning(f"Add to cart failed: Item '{title}' (subtitle={subtitle!r}) not found for code {course_code}, session {user_cart_key}.")
        return False

    if item_data.get('price') is None:
        flash("Item unavailable right now.", "cart_error")
        logger.warning(f"Add to cart failed: Item '{title}' has no price for session {user_cart_key}.")
        return False

    payable, saved = effective_price(item_data['price'], item_data.get('discount'))
    logger.info(
        f"CART ADD: '{title}' list={item_data['price']} discount={item_data.get('discount')}% "
        f"-> payable={payable} (saves {saved})"
    )

    cart_courses.append({
        'title': title,
        'subtitle': subtitle,
        'price': payable,
        'list_price': float(item_data['price'] or 0),
        'item_discount': float(item_data.get('discount') or 0),
        'saved': saved,
        'section': item_data.get('section') or clean_field(form.get('section')),
        'section_id': item_data.get('section_id') or clean_field(form.get('section_id'))
    })
    session[user_cart_key] = cart_courses
    for key in ['show_billing', 'discount', 'coupon_applied', 'coupon_expiry']:
        session.pop(key, None)
    flash(f"{title} added to cart.", "cart_notification")
    logger.info(f"Course '{title}' added to cart for session {user_cart_key}.")
    return True

def remove_from_cart(user_cart_key, title, email):
    cart_courses = []
    removed = False
    for c in session.get(user_cart_key, []):
        if not removed and c['title'] == title:
            removed = True
            continue
        cart_courses.append(c)
    session[user_cart_key] = cart_courses
    logger.info(f"Course '{title}' removed from cart for session {user_cart_key}.")

    total = sum(c['price'] for c in cart_courses)
    coupon_dropped = False
    if 'coupon_applied' in session:
        applied_code = session.get('coupon_applied')
        coupon = user_op.get_coupon_by_code(applied_code, email)
        if coupon and total < coupon[0]['min_purchase']:
            for key in ['discount', 'coupon_applied', 'coupon_expiry']:
                session.pop(key, None)
            coupon_dropped = True
            logger.warning(f"Coupon '{applied_code}' removed due to insufficient purchase total for session {user_cart_key}.")

    if cart_courses:
        if coupon_dropped:
            flash("Item removed. Coupon no longer applies below the minimum order.", "cart_warning")
        else:
            flash(f"{title} removed from cart.", "cart_notification")

    return cart_courses

def apply_coupon(user_cart_key, coupon_code, email):
    cart_courses = session.get(user_cart_key, [])
    total = sum(c['price'] for c in cart_courses)
    coupons = user_op.get_coupon_by_code(coupon_code, email)
    if coupons:
        coupon = coupons[0]
        if total >= coupon['min_purchase']:
            session['discount'] = float(coupon['discount'])
            session['coupon_applied'] = coupon['coupon_code']
            session['coupon_expiry'] = coupon['expiry_date'].strftime('%Y-%m-%d')
            flash("Coupon applied.", "cart_notification")
            logger.info(f"Coupon '{coupon_code}' applied successfully to cart for session {user_cart_key}.")
        else:
            flash(f"Minimum ₹{coupon['min_purchase']} required for this coupon.", "cart_warning")
            logger.warning(f"Coupon '{coupon_code}' not applied: minimum purchase not met for session {user_cart_key}.")
    else:
        flash("Invalid or expired coupon.", "cart_warning")
        logger.warning(f"Failed to apply coupon '{coupon_code}': invalid or expired.")

def clear_cart(user_cart_key):
    session[user_cart_key] = []
    for key in ['discount', 'coupon_applied', 'coupon_expiry']:
        session.pop(key, None)
    flash("Cart cleared.", "cart_notification")
    logger.info(f"Cart cleared for session {user_cart_key}.")