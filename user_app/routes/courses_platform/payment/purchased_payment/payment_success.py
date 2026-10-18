from io import BytesIO
import logging
from flask import flash, redirect, request, send_file, session, url_for
from markupsafe import escape
from routes.courses_platform.payment.purchased_payment.databases.payment_handler_db import UserOperation
from routes.courses_platform.payment.purchased_payment.utils.utils_success import (get_session_user, is_payment_info_valid,
                                         validate_unique_code, process_cart_purchases,
                                         clear_payment_session, verify_hmac_signature, calculate_final_price)
from routes.courses_platform.payment.purchased_payment.create_payment_order import RAZORPAY_SECRET, razorpay_client
from extensions import user_login_required, limiter
from routes.courses_platform.payment.purchased_payment.utils.utils_receipt import generate_pdf_receipt, verify_download_token
from routes.courses_platform.utils.utils_secure_code import secure_access_required
from routes.courses_platform.utils.utils_token import csrf_protected
from routes import users_bp
from routes.email_service import render_email, send_email

user_op = UserOperation()
logger = logging.getLogger(__name__)


@users_bp.route('/payment_success/<course_code>/<unique_code>', methods=['POST'])
@limiter.limit("15 per minute")
@secure_access_required(('course_code', 'unique_code'))
@user_login_required
@csrf_protected
def payment_success(course_code, unique_code):
    username, email, phone = get_session_user()
    if not all([username, email, phone]):
        flash("Your session has expired. Please log in and try again.", "login_warning")
        logger.warning("Session expired during payment success processing.")
        return redirect(url_for('users.user_login'))

    payment_id = request.form.get('razorpay_payment_id')
    order_id = request.form.get('razorpay_order_id')
    signature = request.form.get('razorpay_signature')

    if not all([payment_id, order_id, signature]):
        flash("Payment information is missing. Please do not refresh the page after payment.", "payment_error")
        logger.warning(f"Missing payment information for user {email}.")
        return redirect(url_for('users.course_shop', course_code=course_code, unique_code=unique_code))

    if not verify_hmac_signature(order_id, payment_id, signature, RAZORPAY_SECRET):
        flash("Payment verification failed. Your payment was not successful. Please contact support if money was deducted.", "payment_error")
        logger.error(f"HMAC signature verification failed for user {email}, payment_id: {payment_id}.")
        return redirect(url_for('users.course_shop', course_code=course_code, unique_code=unique_code))

    pending = session.get('pending_purchase')
    if not pending or pending.get('razorpay_order_id') != order_id:
        flash("Payment session mismatch. Please contact support with your payment ID.", "payment_error")
        logger.critical(f"SECURITY: order mismatch for user {email}. expected={pending.get('razorpay_order_id') if pending else None} got={order_id}")
        return redirect(url_for('users.course_shop', course_code=course_code, unique_code=unique_code))

    if pending.get('course_code') != course_code:
        flash("Payment session mismatch. Please contact support with your payment ID.", "payment_error")
        logger.critical(f"SECURITY: course mismatch for user {email}. order_course={pending.get('course_code')} url_course={course_code}")
        return redirect(url_for('users.course_shop', course_code=course_code, unique_code=unique_code))

    existing = user_op.get_purchase_by_payment_id(email, payment_id)
    if existing:
        logger.info(f"Idempotent re-entry: payment_id {payment_id} already processed for user {email}.")
        clear_payment_session(f'user_{email}_cart')
        session.pop('pending_purchase', None)
        return redirect(url_for('users.purchase_dashboard', course_code=course_code, unique_code=unique_code))

    try:
        payment_details = razorpay_client.payment.fetch(payment_id)
        payment_method = payment_details.get('method', 'N/A')
        payment_status = payment_details.get('status')
        paid_amount = int(payment_details.get('amount', 0))
        paid_order_id = payment_details.get('order_id')
    except Exception as e:
        logger.error(f"Could not fetch payment details from Razorpay for {payment_id}: {e}")
        flash("Could not confirm payment details. Please contact support.", "payment_error")
        return redirect(url_for('users.course_shop', course_code=course_code, unique_code=unique_code))

    if paid_order_id != order_id or paid_amount != int(pending.get('amount_in_paise', -1)):
        flash("Payment amount could not be verified. Please contact support with your payment ID.", "payment_error")
        logger.critical(f"SECURITY: amount/order tamper for user {email}. paid_order={paid_order_id} order={order_id} paid={paid_amount} expected={pending.get('amount_in_paise')}")
        return redirect(url_for('users.course_shop', course_code=course_code, unique_code=unique_code))

    if payment_status != 'captured':
        flash(f"Payment status is '{payment_status}'. Only successful payments are processed. Please contact support.", "payment_warning")
        logger.warning(f"Payment status not 'captured' for user {email}, payment_id: {payment_id}. Status: {payment_status}")
        return redirect(url_for('users.course_shop', course_code=course_code, unique_code=unique_code))

    if not is_payment_info_valid(email, username, payment_id):
        flash("Invalid payment attempt detected.", "payment_error")
        logger.warning(f"Invalid payment info for user {email}, payment_id: {payment_id}.")
        return redirect(url_for('users.course_shop', course_code=course_code, unique_code=unique_code))

    if not validate_unique_code(user_op, email, course_code, unique_code):
        flash("Unauthorized access detected! Mismatch in security codes.", "payment_error")
        logger.warning(f"Unique code validation failed for user {email}, course {course_code}.")
        return redirect(url_for('users.course_shop', course_code=course_code, unique_code=unique_code))

    from routes.courses_platform.payment.purchased_payment.payment_orders import content_order, fulfil_content_order
    order = content_order(order_id)
    if not order or order['email'] != email:
        flash("Payment session mismatch. Please contact support with your payment ID.", "payment_error")
        logger.critical(f"SECURITY: no stored order for {order_id} ({email}), payment {payment_id}")
        return redirect(url_for('users.course_shop', course_code=course_code, unique_code=unique_code))
    if paid_amount != int(order.get('amount_paise') or -1):
        flash("Payment amount could not be verified. Please contact support with your payment ID.", "payment_error")
        logger.critical(f"SECURITY: stored order amount mismatch for {email}. paid={paid_amount} order={order.get('amount_paise')} payment_id={payment_id}")
        return redirect(url_for('users.course_shop', course_code=course_code, unique_code=unique_code))

    ok, purchases = fulfil_content_order(order, payment_id, payment_method, 'browser', email_receipt=False)
    if not ok:
        flash("A critical error occurred while saving your purchase. Please contact support immediately with your payment ID.", "payment_error")
        logger.error(f"Transactional purchase save failed for user {email}, payment_id: {payment_id}.")
        return redirect(url_for('users.course_shop', course_code=course_code, unique_code=unique_code))

    user_cart_key = f'user_{email}_cart'
    clear_payment_session(user_cart_key)
    session.pop('pending_purchase', None)
    session.modified = True
    logger.info(f"Payment successful and purchases saved for user {email}, payment_id: {payment_id}.")

    from routes.courses_platform.payment.purchased_payment.payment_orders import send_content_receipt
    try:
        sent = send_content_receipt(order, purchases, payment_id, payment_method)
    except Exception:
        logger.exception(f"Receipt email failed for {payment_id}")
        sent = False
    if sent:
        flash("Payment successful! A receipt has been sent to your email.", "purchase_notification")
    else:
        flash("Payment successful, but we couldn't send the receipt email. You can download it from your dashboard.", "purchase_notification")

    return redirect(url_for('users.purchase_dashboard', course_code=course_code, unique_code=unique_code))


@users_bp.route('/download_receipt/<payment_id>', methods=['GET'])
@limiter.limit("20 per minute")
@user_login_required
def download_receipt(payment_id):
    token = request.args.get("token")
    if not token or not verify_download_token(payment_id, token):
        flash("Invalid or expired download link.", "download_warning")
        logger.warning(f"Download token validation failed for payment_id: {payment_id}.")
        return redirect(url_for('users.purchase_dashboard', course_code="none", unique_code="none"))

    email = session.get('user_email')
    if not email:
        flash("Login required.", "login_warning")
        logger.warning("Unauthorized receipt download attempt: no user email in session.")
        return redirect(url_for('users.user_login'))

    purchases = user_op.get_purchase_by_payment_id(email, payment_id)
    if not purchases or purchases[0]['email'] != email:
        flash("Access denied.", "download_warning")
        logger.warning(f"Access denied for receipt download for user {email}, payment_id: {payment_id}.")
        return redirect(url_for('users.user_login'))

    total_price = sum(float(p['original_price']) for p in purchases)
    discount = float(purchases[0].get('discount_percent', 0))
    discount_amount = round(total_price * discount / 100, 2)
    final_amount = round(total_price - discount_amount, 2)

    payment_mode = purchases[0].get('payment_mode', 'N/A')
    status = purchases[0].get('status', 'Pending')

    pdf = generate_pdf_receipt(
        username=purchases[0]['username'],
        email=email,
        phone=purchases[0]['phone'],
        payment_id=payment_id,
        purchases=purchases,
        discount=discount,
        original_price=total_price,
        final_amount=final_amount,
        payment_mode=payment_mode,
        status=status,
        purchase_date=purchases[0].get('payment_date')
    )
    logger.info(f"Receipt downloaded for user {email}, payment_id: {payment_id}.")

    return send_file(BytesIO(pdf.getvalue()), mimetype='application/pdf', as_attachment=True, download_name='receipt.pdf')
