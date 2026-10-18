import hashlib
import hmac
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta

from flask import jsonify, request, session, url_for
from markupsafe import escape

from routes import users_bp
from routes.courses_platform.payment.purchased_payment.databases.payment_handler_db import UserOperation
from routes.courses_platform.payment.purchased_payment.utils.utils_success import process_cart_purchases
from routes.courses_platform.payment.purchased_payment.utils.utils_receipt import generate_pdf_receipt
from routes.courses_platform.utils.utils_token import csrf_protected
from routes.db_pool import get_connection
from extensions import user_login_required, limiter
from config import Config

logger = logging.getLogger(__name__)
user_op = UserOperation()

RECONCILE_LOCK = 'spp_payment_reconcile'
MIN_AGE_MINUTES = 3
GIVE_UP_DAYS = 7


def _all(sql, params=()):
    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute(sql, params)
        return cursor.fetchall()
    except Exception:
        logger.exception("PAYMENT ORDERS: read failed")
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _one(sql, params=()):
    rows = _all(sql + " LIMIT 1", params)
    return rows[0] if rows else None


def _write(sql, params=()):
    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()
        return cursor.rowcount
    except Exception:
        logger.exception("PAYMENT ORDERS: write failed")
        if conn:
            conn.rollback()
        return 0
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def gateway():
    from routes.courses_platform.payment.purchased_payment.create_payment_order import razorpay_client
    return razorpay_client


def record_content_order(email, username, phone, course_code, unique_code, order_id, amount_paise,
                         cart, discount_pct, total_price):
    return _write("""
        INSERT INTO content_orders (email, username, phone, course_code, unique_code, razorpay_order_id,
                                    amount_paise, list_paise, discount_pct, cart_json)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (email, username, phone, course_code, unique_code, order_id, amount_paise,
          int(round(float(total_price or 0) * 100)), discount_pct, json.dumps(cart)))


def content_order(order_id):
    return _one("SELECT * FROM content_orders WHERE razorpay_order_id = %s", (order_id,))


def content_order_by_payment(payment_id):
    return _one("SELECT * FROM content_orders WHERE razorpay_payment_id = %s ORDER BY id DESC", (payment_id,))


def pending_orders_for(email, days=GIVE_UP_DAYS):
    since = datetime.now() - timedelta(days=days)
    items = _all("""
        SELECT id, razorpay_order_id, amount_paise, course_code, unique_code, cart_json, status, gateway_status, created_at
          FROM content_orders WHERE email = %s AND status = 'created' AND created_at >= %s ORDER BY id DESC
    """, (email, since))
    for it in items:
        try:
            cart = json.loads(it.get('cart_json') or '[]')
        except ValueError:
            cart = []
        it['kind'] = 'content'
        it['title'] = ', '.join(c.get('title', '') for c in cart) or 'Course content'
        it['amount'] = (it.get('amount_paise') or 0) / 100.0
    subs = _all("""
        SELECT id, razorpay_order_id, amount_paise, course_code, plan_label, plan, status, gateway_status, created_at
          FROM pcp_subscriptions WHERE email = %s AND status = 'created' AND created_at >= %s ORDER BY id DESC
    """, (email, since))
    for s in subs:
        s['kind'] = 'premium'
        s['title'] = f"Premium - {s.get('plan_label') or s.get('plan')}"
        s['amount'] = (s.get('amount_paise') or 0) / 100.0
    return sorted(items + subs, key=lambda r: r['created_at'] or datetime.min, reverse=True)


def _mark_gateway(kind, order_id, gateway_status, payment_id=None):
    table = 'content_orders' if kind == 'content' else 'pcp_subscriptions'
    if payment_id:
        _write(f"UPDATE {table} SET gateway_status = %s, razorpay_payment_id = COALESCE(razorpay_payment_id, %s) "
               f"WHERE razorpay_order_id = %s", (gateway_status, payment_id, order_id))
    else:
        _write(f"UPDATE {table} SET gateway_status = %s WHERE razorpay_order_id = %s", (gateway_status, order_id))


def mark_failed(kind, order_id, payment_id=None):
    table = 'content_orders' if kind == 'content' else 'pcp_subscriptions'
    _write(f"UPDATE {table} SET status = 'failed', gateway_status = 'failed', "
           f"razorpay_payment_id = COALESCE(razorpay_payment_id, %s) "
           f"WHERE razorpay_order_id = %s AND status = 'created'", (payment_id, order_id))


def _receipt_for(order, purchases, payment_id, method):
    if not purchases:
        return None, None
    first = purchases[0]
    total_price = (order.get('list_paise') or order.get('amount_paise') or 0) / 100.0
    final_amount = (order.get('amount_paise') or 0) / 100.0
    discount = float(order.get('discount_pct') or 0)
    pdf = generate_pdf_receipt(
        username=first['username'], email=first['email'], phone=first.get('phone') or '',
        payment_id=payment_id, purchases=purchases, discount=discount,
        original_price=total_price, final_amount=final_amount, payment_mode=method,
        status=first['status'], purchase_date=first.get('payment_date'))
    items_html = "".join(
        f"<tr><td style='padding:6px 0;color:#5c1a15;font-size:14px;'>{escape(p['title'])}</td>"
        f"<td style='padding:6px 0;color:#111827;font-size:14px;font-weight:600;text-align:right;'>"
        f"&#8377;{float(p['final_price']):.2f}</td></tr>" for p in purchases)
    body = (
        f"<p>Hi {escape(first['username'] or 'there')},</p>"
        f"<p>Thank you for your purchase! Your payment was successful and your content is now unlocked. "
        f"Your itemised receipt is attached as a PDF.</p>"
        f"<table role='presentation' width='100%' style='margin:16px 0;border-top:1px solid #e2e8f0;'>{items_html}"
        f"<tr><td style='padding:10px 0 0;border-top:1px solid #e2e8f0;font-weight:700;color:#111827;'>Total paid</td>"
        f"<td style='padding:10px 0 0;border-top:1px solid #e2e8f0;font-weight:700;color:#111827;text-align:right;'>"
        f"&#8377;{final_amount:.2f}</td></tr></table>"
        f"<p style='color:#992c25;font-size:13px;'>Payment ID: {escape(payment_id)}</p>")
    return pdf, body


def send_content_receipt(order, purchases, payment_id, method):
    from routes.email_service import render_email, send_email
    pdf, body = _receipt_for(order, purchases, payment_id, method)
    if pdf is None:
        return False
    try:
        cta = url_for('users.purchase_dashboard', course_code=order['course_code'],
                      unique_code=order.get('unique_code') or '', _external=True)
    except Exception:
        cta = None
    html = render_email("Payment successful ✅", body, cta_text="View my purchases" if cta else None,
                        cta_url=cta, preheader="Your receipt is attached")
    return bool(send_email("Your payment receipt", purchases[0]['email'], html,
                           attachments=[("receipt.pdf", "application/pdf", pdf.getvalue())]))


def fulfil_content_order(order, payment_id, method='razorpay', source='browser', email_receipt=True):
    email = order['email']
    existing = user_op.get_purchase_by_payment_id(email, payment_id)
    if existing:
        if order.get('status') != 'paid':
            _write("UPDATE content_orders SET status='paid', gateway_status='captured', razorpay_payment_id=%s, "
                   "payment_method=%s, fulfilled_by=%s, fulfilled_at=NOW() WHERE id=%s",
                   (payment_id, method, source, order['id']))
        logger.info("PAYMENT ORDERS: %s already fulfilled for %s (%s)", payment_id, email, source)
        return True, existing
    try:
        cart = json.loads(order.get('cart_json') or '[]')
    except ValueError:
        cart = []
    if not cart:
        logger.critical("PAYMENT ORDERS: order %s for %s has no cart snapshot - cannot fulfil", order['razorpay_order_id'], email)
        return False, []
    discount = float(order.get('discount_pct') or 0)
    total_price = (order.get('list_paise') or order.get('amount_paise') or 0) / 100.0
    final_amount = (order.get('amount_paise') or 0) / 100.0
    vanished = [c.get('title') for c in cart
                if not user_op.get_content_by_code_title_subtitle(order['course_code'], c.get('title'), c.get('subtitle', ''))]
    if vanished:
        logger.critical("PAYMENT RACE: [%s] paid %s for content that changed during checkout: %s. "
                        "The purchase is still recorded so the payment is never lost.", email, payment_id, vanished)
    rows = process_cart_purchases(cart_courses=cart, email=email, username=order.get('username') or email,
                                  phone=order.get('phone') or '', payment_id=payment_id,
                                  course_code=order['course_code'], amount_paid=final_amount,
                                  discount_percent=discount, payment_mode=method, status='Paid',
                                  original_price=total_price, user_op=user_op)
    if not user_op.add_purchase_transactional(rows):
        logger.error("PAYMENT ORDERS: could not save purchase rows for %s payment %s (%s)", email, payment_id, source)
        return False, []
    _write("UPDATE content_orders SET status='paid', gateway_status='captured', razorpay_payment_id=%s, "
           "payment_method=%s, fulfilled_by=%s, fulfilled_at=NOW() WHERE id=%s",
           (payment_id, method, source, order['id']))
    logger.info("PAYMENT ORDERS: FULFILLED %s for %s via %s (%d item(s), %s)", payment_id, email, source, len(rows), final_amount)
    purchases = user_op.get_purchase_by_payment_id(email, payment_id)
    if email_receipt:
        try:
            send_content_receipt(order, purchases, payment_id, method)
        except Exception:
            logger.exception("PAYMENT ORDERS: receipt email failed for %s", payment_id)
    return True, purchases


def _captured_payment(order_id, expected_paise):
    client = gateway()
    if client is None:
        return None, 'gateway unavailable'
    try:
        found = client.order.payments(order_id) or {}
    except Exception as e:
        logger.warning("PAYMENT ORDERS: could not ask Razorpay about %s: %s", order_id, str(e)[:160])
        return None, 'gateway unreachable'
    items = found.get('items') or []
    statuses = []
    for p in items:
        statuses.append(p.get('status'))
        if p.get('status') == 'captured':
            if int(p.get('amount') or 0) != int(expected_paise or 0):
                logger.critical("PAYMENT ORDERS: AMOUNT MISMATCH on %s paid=%s expected=%s",
                                order_id, p.get('amount'), expected_paise)
                return None, 'amount mismatch'
            return p, 'captured'
    if any(s == 'authorized' for s in statuses):
        return None, 'authorized'
    if items and all(s == 'failed' for s in statuses):
        return None, 'failed'
    return None, 'unpaid'


def settle_content_order(order, source):
    payment, verdict = _captured_payment(order['razorpay_order_id'], order['amount_paise'])
    if payment:
        ok, _ = fulfil_content_order(order, payment['id'], payment.get('method') or 'razorpay', source)
        return 'paid' if ok else 'error'
    if verdict in ('authorized', 'failed', 'unpaid'):
        _mark_gateway('content', order['razorpay_order_id'], verdict)
    return verdict


def settle_subscription_order(row, source):
    from routes.exam_platform.placement_exam_portal.practice_coding import models, routes_billing
    payment, verdict = _captured_payment(row['razorpay_order_id'], row['amount_paise'])
    if payment:
        starts, expires = routes_billing._period(row['email'], row.get('course_code'), row['plan'], row.get('plan_ends_at'))
        models.activate_subscription(row['razorpay_order_id'], payment['id'], starts, expires, fulfilled_by=source)
        logger.info("PAYMENT ORDERS: ACTIVATED premium %s for %s via %s", row['plan'], row['email'], source)
        try:
            user = {'email': row['email'], 'username': row.get('username') or row['email']}
            routes_billing._send_subscription_receipt(user, row, payment['id'], starts, expires)
        except Exception:
            logger.exception("PAYMENT ORDERS: premium receipt failed for %s", row['razorpay_order_id'])
        return 'paid'
    if verdict in ('authorized', 'failed', 'unpaid'):
        _mark_gateway('premium', row['razorpay_order_id'], verdict)
    return verdict


def reconcile(now=None):
    now = now or datetime.now()
    young = now - timedelta(minutes=MIN_AGE_MINUTES)
    old = now - timedelta(days=GIVE_UP_DAYS)
    report = {'checked': 0, 'paid': 0, 'failed': 0, 'expired': 0}
    for order in _all("SELECT * FROM content_orders WHERE status='created' AND created_at <= %s ORDER BY id", (young,)):
        report['checked'] += 1
        verdict = settle_content_order(order, 'reconcile')
        if verdict == 'paid':
            report['paid'] += 1
        elif verdict == 'failed' or (order['created_at'] and order['created_at'] < old and verdict == 'unpaid'):
            mark_failed('content', order['razorpay_order_id'])
            report['failed' if verdict == 'failed' else 'expired'] += 1
    for row in _all("SELECT * FROM pcp_subscriptions WHERE status='created' AND created_at <= %s ORDER BY id", (young,)):
        report['checked'] += 1
        verdict = settle_subscription_order(row, 'reconcile')
        if verdict == 'paid':
            report['paid'] += 1
        elif verdict == 'failed' or (row['created_at'] and row['created_at'] < old and verdict == 'unpaid'):
            mark_failed('premium', row['razorpay_order_id'])
            report['failed' if verdict == 'failed' else 'expired'] += 1
    if report['checked']:
        logger.info("PAYMENT ORDERS: reconcile - %s", report)
    return report


def run_reconcile_locked():
    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT GET_LOCK(%s, 0)", (RECONCILE_LOCK,))
        got = (cursor.fetchone() or [0])[0]
        if not got:
            return None
        try:
            return reconcile()
        finally:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (RECONCILE_LOCK,))
            cursor.fetchall()
    except Exception:
        logger.exception("PAYMENT ORDERS: reconcile run failed")
        return None
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def start_reconcile_scheduler(app):
    if os.environ.get('PAYMENT_RECONCILE_JOB', '1') == '0':
        logger.info("PAYMENT ORDERS: reconcile scheduler disabled by PAYMENT_RECONCILE_JOB=0")
        return None
    reloader_on = not bool(os.environ.get('RENDER') or os.environ.get('GUNICORN_CMD_ARGS') or os.environ.get('SPP_ASYNC_MODE'))
    if reloader_on and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return None
    try:
        minutes = max(1, int(os.environ.get('PAYMENT_RECONCILE_INTERVAL_MIN', '5')))
    except ValueError:
        minutes = 5

    def loop():
        time.sleep(45)
        while True:
            try:
                with app.app_context():
                    run_reconcile_locked()
            except Exception:
                logger.exception("PAYMENT ORDERS: reconcile tick failed")
            time.sleep(minutes * 60)

    t = threading.Thread(target=loop, name='payment-reconcile', daemon=True)
    t.start()
    logger.info("PAYMENT ORDERS: reconcile scheduler every %d minute(s)", minutes)
    return t


def _webhook_ok(secret):
    body = request.get_data()
    signature = request.headers.get('X-Razorpay-Signature', '')
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return bool(signature) and hmac.compare_digest(expected, signature)


@users_bp.route('/api/purchase/webhook', methods=['POST'])
@limiter.limit("1200 per minute")
def purchase_webhook():
    secret = getattr(Config, 'RAZORPAY_WEBHOOK_SECRET', None)
    if not secret:
        return jsonify({'error': 'not found'}), 404
    if not _webhook_ok(secret):
        logger.warning("PAYMENT ORDERS: webhook BAD SIGNATURE from %s", request.remote_addr)
        return jsonify({'error': 'invalid signature'}), 400
    event = request.get_json(silent=True) or {}
    name = event.get('event')
    payment = (((event.get('payload') or {}).get('payment') or {}).get('entity') or {})
    order_id, payment_id = payment.get('order_id'), payment.get('id')
    if not order_id or not payment_id:
        return jsonify({'status': 'ignored'}), 200
    order = content_order(order_id)
    kind = 'content' if order else 'premium'
    if not order:
        from routes.exam_platform.placement_exam_portal.practice_coding import models
        order = models.get_subscription_by_order(order_id)
        if not order:
            return jsonify({'status': 'ignored'}), 200
    if name == 'payment.failed':
        _mark_gateway(kind, order_id, 'failed', payment_id)
        return jsonify({'status': 'noted'}), 200
    if name not in ('payment.captured', 'order.paid'):
        return jsonify({'status': 'ignored'}), 200
    if payment.get('amount') is not None and int(payment['amount']) != int(order.get('amount_paise') or 0):
        logger.critical("PAYMENT ORDERS: webhook AMOUNT MISMATCH order %s paid=%s expected=%s",
                        order_id, payment.get('amount'), order.get('amount_paise'))
        return jsonify({'error': 'amount mismatch'}), 400
    if kind == 'content':
        if order['status'] == 'paid':
            return jsonify({'status': 'already_paid'}), 200
        ok, _ = fulfil_content_order(order, payment_id, payment.get('method') or 'razorpay', 'webhook')
        return jsonify({'status': 'fulfilled' if ok else 'error'}), (200 if ok else 500)
    if order['status'] == 'active':
        return jsonify({'status': 'already_active'}), 200
    from routes.exam_platform.placement_exam_portal.practice_coding import models, routes_billing
    starts, expires = routes_billing._period(order['email'], order.get('course_code'), order['plan'], order.get('plan_ends_at'))
    models.activate_subscription(order_id, payment_id, starts, expires, fulfilled_by='webhook')
    logger.info("PAYMENT ORDERS: WEBHOOK ACTIVATED %s for %s", order['plan'], order['email'])
    try:
        routes_billing._send_subscription_receipt({'email': order['email'], 'username': order.get('username') or order['email']},
                                                  order, payment_id, starts, expires)
    except Exception:
        logger.exception("PAYMENT ORDERS: premium receipt failed for %s", order_id)
    return jsonify({'status': 'activated'}), 200


@users_bp.route('/api/payment/check/<order_id>', methods=['POST'])
@user_login_required
@csrf_protected
@limiter.limit("12 per minute")
def payment_check(order_id):
    email = session.get('user_email')
    order = content_order(order_id)
    kind = 'content'
    if not order:
        from routes.exam_platform.placement_exam_portal.practice_coding import models
        order = models.get_subscription_by_order(order_id)
        kind = 'premium'
    if not order or order['email'] != email:
        return jsonify({'error': 'Unknown order.'}), 404
    if order['status'] in ('paid', 'active'):
        return jsonify({'status': 'paid', 'message': 'This payment is already recorded - your access is open.'})
    verdict = settle_content_order(order, 'student') if kind == 'content' else settle_subscription_order(order, 'student')
    messages = {
        'paid': 'Payment found at Razorpay - your access is open now. A receipt is on its way to your email.',
        'authorized': 'Razorpay is still processing this payment. Check again in a few minutes.',
        'failed': 'Razorpay reports this payment failed. Nothing was charged; any deduction reverses automatically.',
        'unpaid': 'Razorpay has no successful payment for this order. If money left your account, it will reverse within 5-7 days.',
        'amount mismatch': 'The amount paid does not match this order. Please contact support with your order ID.',
        'gateway unavailable': 'The payment gateway is not reachable right now. Try again shortly.',
        'gateway unreachable': 'The payment gateway is not reachable right now. Try again shortly.',
        'error': 'Payment found but it could not be recorded. Please contact support with your order ID.',
    }
    if verdict == 'failed':
        mark_failed(kind, order_id)
    logger.info("PAYMENT ORDERS: student check %s -> %s (%s)", order_id, verdict, email)
    return jsonify({'status': verdict, 'message': messages.get(verdict, verdict)})
