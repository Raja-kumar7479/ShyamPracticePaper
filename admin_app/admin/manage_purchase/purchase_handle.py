import csv
import logging
import os
import re
from datetime import datetime
from io import StringIO
from flask import jsonify, render_template, request, session, Response
from admin.manage_purchase.purchase_db import PurchaseOperation
from admin import admin_bp
from typing import Tuple, Any
from extensions import admin_login_required

logger = logging.getLogger(__name__)

purchase_op = PurchaseOperation()

_razorpay_client = None
_razorpay_failed = False


def _get_razorpay():
    global _razorpay_client, _razorpay_failed
    if _razorpay_client is not None or _razorpay_failed:
        return _razorpay_client
    key_id = os.environ.get('RAZORPAY_KEY_ID')
    secret = os.environ.get('RAZORPAY_SECRET')
    if not key_id or not secret:
        _razorpay_failed = True
        logger.warning("VERIFY: Razorpay credentials missing; live verification disabled")
        return None
    try:
        import razorpay
        _razorpay_client = razorpay.Client(auth=(key_id, secret))
        logger.info("VERIFY: Razorpay client ready for live verification")
    except Exception as e:
        _razorpay_failed = True
        logger.error(f"VERIFY: Razorpay client init failed: {e}")
    return _razorpay_client


_CSV_FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r')


def _csv_safe(value):
    if value is None:
        return ''
    text = str(value)
    if text.startswith(_CSV_FORMULA_PREFIXES):
        return "'" + text
    return text


def _csv_safe_row(values):
    return [_csv_safe(v) for v in values]


def _serialise(rows):
    for row in rows:
        for key, value in list(row.items()):
            if isinstance(value, datetime):
                row[key] = value.strftime('%d %b %Y, %I:%M:%S %p')
            elif hasattr(value, 'quantize'):
                row[key] = float(value)
    return rows


@admin_bp.route('/manage_purchases', methods=['GET'])
@admin_login_required
def manage_purchases():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    try:
        logger.info(f"PURCHASES PAGE: [{admin_email}] opened")
        return render_template('admin/manage_purchase/purchase_handler.html')
    except Exception as e:
        logger.exception(f"PURCHASES PAGE FAILED: [{admin_email}] {e}")
        return "<h1>An Internal Server Error Occurred</h1>", 500


@admin_bp.route('/api/purchases/courses', methods=['GET'])
@admin_login_required
def purchases_courses():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    try:
        rows = _serialise(purchase_op.get_purchase_courses())
        logger.info(f"PURCHASES STEP 1: [{admin_email}] {len(rows)} course(s) returned")
        return jsonify(rows)
    except Exception:
        logger.exception(f"PURCHASES STEP 1 FAILED: [{admin_email}]")
        return jsonify({'error': 'Could not load courses.'}), 500


@admin_bp.route('/api/purchases/buyers', methods=['GET'])
@admin_login_required
def purchases_buyers():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    course_code = (request.args.get('course_code') or '').strip()
    if not course_code:
        return jsonify({'error': 'Course code is required.'}), 400
    try:
        rows = _serialise(purchase_op.get_buyers_for_course(course_code))
        logger.info(f"PURCHASES STEP 2: [{admin_email}] {len(rows)} buyer(s) in {course_code}")
        return jsonify(rows)
    except Exception:
        logger.exception(f"PURCHASES STEP 2 FAILED: [{admin_email}] course={course_code!r}")
        return jsonify({'error': 'Could not load buyers.'}), 500


@admin_bp.route('/api/purchases/user', methods=['GET'])
@admin_login_required
def purchases_for_user():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    course_code = (request.args.get('course_code') or '').strip()
    email = (request.args.get('email') or '').strip().lower()
    if not course_code or not email:
        return jsonify({'error': 'Course code and email are both required.'}), 400
    try:
        logger.info(f"PURCHASES STEP 3: [{admin_email}] lookup {email!r} in {course_code!r}")
        purchases = purchase_op.get_user_purchases(course_code, email)
        enrollments = purchase_op.get_user_enrollment_payments(course_code, email)

        total_paid = sum(float(p.get('final_price') or 0) for p in purchases)
        total_paid += sum(float(e.get('amount_paid') or 0) for e in enrollments)
        summary = {
            'items': len(purchases),
            'enrollment_payments': len(enrollments),
            'total_paid': round(total_paid, 2),
            'username': (purchases[0].get('username') if purchases else
                         (enrollments[0].get('username') if enrollments else None)),
            'first_purchase': min((p['payment_date'] for p in purchases if p.get('payment_date')), default=None),
            'last_purchase': max((p['payment_date'] for p in purchases if p.get('payment_date')), default=None),
        }
        if isinstance(summary['first_purchase'], datetime):
            summary['first_purchase'] = summary['first_purchase'].strftime('%d %b %Y, %I:%M %p')
        if isinstance(summary['last_purchase'], datetime):
            summary['last_purchase'] = summary['last_purchase'].strftime('%d %b %Y, %I:%M %p')

        logger.info(f"PURCHASES STEP 4: [{admin_email}] {email!r}: {summary['items']} item(s), "
                    f"{summary['enrollment_payments']} enrollment payment(s), total {summary['total_paid']}")
        return jsonify({
            'purchases': _serialise(purchases),
            'enrollment_payments': _serialise(enrollments),
            'summary': summary,
        })
    except Exception:
        logger.exception(f"PURCHASES STEP 3 FAILED: [{admin_email}] {email!r}/{course_code!r}")
        return jsonify({'error': 'Could not load the purchase history.'}), 500


@admin_bp.route('/api/purchases/groups', methods=['GET'])
@admin_login_required
def purchases_groups():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    try:
        groups = purchase_op.get_groups_with_codes()
        logger.info(f"PURCHASES GROUPS: [{admin_email}] {len(groups)} group(s)")
        return jsonify(groups)
    except Exception:
        logger.exception(f"PURCHASES GROUPS FAILED: [{admin_email}]")
        return jsonify({'error': 'Could not load the course groups.'}), 500


@admin_bp.route('/api/purchases/search', methods=['GET'])
@admin_login_required
def purchases_search():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    q = (request.args.get('q') or '').strip()
    course_code = (request.args.get('course_code') or '').strip() or None
    try:
        limit = max(1, min(int(request.args.get('limit') or 25), 100))
    except ValueError:
        limit = 25
    if len(q) < 2:
        return jsonify({'error': 'Type at least 2 characters.'}), 400
    try:
        rows = _serialise(purchase_op.search_customers(q, course_code, limit))
        logger.info(f"PURCHASES SEARCH: [{admin_email}] q={q!r} course={course_code!r} -> {len(rows)}")
        return jsonify(rows)
    except Exception:
        logger.exception(f"PURCHASES SEARCH FAILED: [{admin_email}] q={q!r}")
        return jsonify({'error': 'Search failed.'}), 500


@admin_bp.route('/api/purchases/customer', methods=['GET'])
@admin_login_required
def purchases_customer():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    email = (request.args.get('email') or '').strip().lower()
    course_code = (request.args.get('course_code') or '').strip() or None
    if not email:
        return jsonify({'error': 'Email is required.'}), 400
    try:
        data = purchase_op.get_customer_overview(email, course_code)
        for key in ('purchases', 'enrollment_payments', 'subscriptions'):
            data[key] = _serialise(data[key])
        if data['account']:
            data['account'] = _serialise([data['account']])[0]
        live = [s for s in data['subscriptions'] if s.get('is_live')]
        data['summary'] = {
            'username': (data['account'] or {}).get('username')
                        or (data['purchases'][0].get('username') if data['purchases'] else None),
            'items': len(data['purchases']),
            'enrollment_payments': len(data['enrollment_payments']),
            'subscriptions': len(data['subscriptions']),
            'premium_active': bool(live),
            'premium_expires': live[0].get('expires_at') if live else None,
            'total_paid': data['total_paid'],
            'first_purchase': data['purchases'][-1].get('payment_date') if data['purchases'] else None,
            'last_purchase': data['purchases'][0].get('payment_date') if data['purchases'] else None,
        }
        logger.info(f"PURCHASES CUSTOMER: [{admin_email}] {email!r} course={course_code!r} -> "
                    f"{data['summary']['items']} purchase(s), {data['summary']['subscriptions']} subscription(s)")
        return jsonify(data)
    except Exception:
        logger.exception(f"PURCHASES CUSTOMER FAILED: [{admin_email}] {email!r}")
        return jsonify({'error': 'Could not load this customer.'}), 500


@admin_bp.route('/api/purchases/export-customer', methods=['GET'])
@admin_login_required
def purchases_export_customer():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    email = (request.args.get('email') or '').strip().lower()
    course_code = (request.args.get('course_code') or '').strip() or None
    if not email:
        return jsonify({'error': 'Email is required.'}), 400
    try:
        data = purchase_op.get_customer_overview(email, course_code)
        out = StringIO()
        writer = csv.writer(out)
        writer.writerow(['record_type', 'date', 'item', 'course', 'name', 'email', 'phone',
                         'original_price', 'discount_percent', 'amount_paid', 'payment_id',
                         'payment_mode', 'status', 'valid_until'])
        for p in _serialise(data['purchases']):
            writer.writerow(_csv_safe_row(['purchase', p.get('payment_date'), p.get('title'), p.get('course_code'),
                             p.get('username'), p.get('email'), p.get('phone'), p.get('original_price'),
                             p.get('discount_percent'), p.get('final_price'), p.get('payment_id'),
                             p.get('payment_mode'), p.get('status'), '']))
        for e in _serialise(data['enrollment_payments']):
            writer.writerow(_csv_safe_row(['enrollment_fee', e.get('completion_date'), 'Platform enrollment fee',
                             e.get('course_code'), e.get('username'), e.get('email'), '', '', '',
                             e.get('amount_paid'), e.get('razorpay_payment_id') or e.get('payment_id'),
                             e.get('payment_method'), e.get('payment_status'), '']))
        for s_ in _serialise(data['subscriptions']):
            writer.writerow(_csv_safe_row(['premium_subscription', s_.get('created_at'),
                             f"Premium ({s_.get('plan')})", '', (data['account'] or {}).get('username'),
                             email, '', '', '', s_.get('amount'), s_.get('razorpay_payment_id'),
                             'razorpay', s_.get('status'), s_.get('expires_at')]))
        logger.info(f"PURCHASES EXPORT: [{admin_email}] {email!r}")
        return Response(out.getvalue(), mimetype='text/csv',
                        headers={'Content-Disposition': f'attachment; filename=customer_{email}.csv'})
    except Exception:
        logger.exception(f"PURCHASES EXPORT FAILED: [{admin_email}] {email!r}")
        return jsonify({'error': 'Export failed.'}), 500


@admin_bp.route('/api/purchases/find', methods=['GET'])
@admin_login_required
def purchases_find_by_payment():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    payment_id = (request.args.get('payment_id') or '').strip()
    if not payment_id:
        return jsonify({'error': 'Payment ID is required.'}), 400
    try:
        logger.info(f"PURCHASES FIND: [{admin_email}] payment_id={payment_id!r}")
        purchases, enrollments = purchase_op.find_by_payment_id(payment_id)
        return jsonify({
            'purchases': _serialise(purchases),
            'enrollment_payments': _serialise(enrollments),
            'found': bool(purchases or enrollments),
        })
    except Exception:
        logger.exception(f"PURCHASES FIND FAILED: [{admin_email}] {payment_id!r}")
        return jsonify({'error': 'Could not search for this payment.'}), 500


@admin_bp.route('/api/purchases/verify/<payment_id>', methods=['GET'])
@admin_login_required
def purchases_verify_live(payment_id):
    admin_email = session.get('admin_email', 'UnknownAdmin')
    payment_id = payment_id.strip()
    logger.info(f"VERIFY 1: [{admin_email}] live check for {payment_id!r}")

    if not payment_id.startswith('pay_'):
        logger.info(f"VERIFY 2: [{admin_email}] {payment_id!r} is not a Razorpay payment (internal/free id)")
        return jsonify({
            'live': False,
            'reason': 'This is an internal reference (free enrollment or manual entry), not a Razorpay payment - there is nothing to verify at the gateway.'
        })

    client = _get_razorpay()
    if client is None:
        return jsonify({'live': False, 'reason': 'Razorpay is not configured on this server.'}), 503

    try:
        p = client.payment.fetch(payment_id)
    except Exception as e:
        text = str(e)
        logger.warning(f"VERIFY FAILED: [{admin_email}] gateway rejected {payment_id!r}: {text[:200]}")
        if 'does not exist' in text.lower() or 'invalid' in text.lower():
            return jsonify({'live': False,
                            'reason': 'Razorpay does not recognise this payment ID. It may belong to a different account or be mistyped.'})
        return jsonify({'live': False, 'reason': 'Could not reach Razorpay right now. Try again shortly.'}), 502

    status = p.get('status')
    refund_status = p.get('refund_status')
    if status == 'captured' and refund_status in ('full', 'partial'):
        verdict, verdict_kind = f"Refunded ({refund_status})", 'warning'
    elif status == 'captured':
        verdict, verdict_kind = 'Success - money received', 'success'
    elif status == 'authorized':
        verdict, verdict_kind = 'Authorized but NOT captured - money on hold, will auto-refund if not captured', 'warning'
    elif status == 'failed':
        verdict, verdict_kind = 'Failed - customer was not charged (any deduction auto-reverses)', 'danger'
    elif status == 'refunded':
        verdict, verdict_kind = 'Fully refunded', 'warning'
    else:
        verdict, verdict_kind = f"Status: {status}", 'secondary'

    created = p.get('created_at')
    created_str = datetime.fromtimestamp(created).strftime('%d %b %Y, %I:%M:%S %p') if created else None

    logger.info(f"VERIFY 3: [{admin_email}] {payment_id!r} -> {status} (refund={refund_status})")
    return jsonify({
        'live': True,
        'payment_id': p.get('id'),
        'status': status,
        'verdict': verdict,
        'verdict_kind': verdict_kind,
        'amount': round((p.get('amount') or 0) / 100.0, 2),
        'amount_refunded': round((p.get('amount_refunded') or 0) / 100.0, 2),
        'currency': p.get('currency'),
        'method': p.get('method'),
        'email': p.get('email'),
        'contact': p.get('contact'),
        'order_id': p.get('order_id'),
        'captured': bool(p.get('captured')),
        'created_at': created_str,
        'error_code': p.get('error_code'),
        'error_description': p.get('error_description'),
        'error_reason': p.get('error_reason'),
    })


@admin_bp.route('/api/purchases/export', methods=['GET'])
@admin_login_required
def purchases_export():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    course_code = (request.args.get('course_code') or '').strip()
    email = (request.args.get('email') or '').strip().lower()
    if not course_code or not email:
        return jsonify({'error': 'Course code and email are both required.'}), 400
    try:
        purchases = _serialise(purchase_op.get_user_purchases(course_code, email))
        enrollments = _serialise(purchase_op.get_user_enrollment_payments(course_code, email))
        out = StringIO()
        writer = csv.writer(out)
        writer.writerow(['record_type', 'date', 'item', 'course', 'name', 'email', 'phone',
                         'original_price', 'discount_percent', 'amount_paid', 'payment_id',
                         'payment_mode', 'status'])
        for p in purchases:
            writer.writerow(_csv_safe_row(['purchase', p.get('payment_date'), p.get('title'), p.get('course_code'),
                             p.get('username'), p.get('email'), p.get('phone'),
                             p.get('original_price'), p.get('discount_percent'), p.get('final_price'),
                             p.get('payment_id'), p.get('payment_mode'), p.get('status')]))
        for e in enrollments:
            writer.writerow(_csv_safe_row(['enrollment_fee', e.get('completion_date'), 'Platform enrollment fee',
                             e.get('course_code'), e.get('username'), e.get('email'), '',
                             '', '', e.get('amount_paid'),
                             e.get('razorpay_payment_id') or e.get('payment_id'),
                             e.get('payment_method'), e.get('payment_status')]))
        safe_email = re.sub(r'[^A-Za-z0-9]+', '_', email)
        logger.info(f"PURCHASES EXPORT: [{admin_email}] {email!r}/{course_code!r} "
                    f"-> {len(purchases)} purchase(s) + {len(enrollments)} enrollment row(s)")
        return Response(out.getvalue(), mimetype='text/csv',
                        headers={'Content-Disposition': f'attachment; filename=purchases_{course_code}_{safe_email}.csv'})
    except Exception:
        logger.exception(f"PURCHASES EXPORT FAILED: [{admin_email}] {email!r}/{course_code!r}")
        return jsonify({'error': 'Could not export the purchase history.'}), 500


@admin_bp.route('/get_all_purchases', methods=['GET'])
@admin_login_required
def get_all_purchases() -> Tuple[Any, int]:
    try:
        logger.info("Fetching all purchase details.")
        purchases = _serialise(purchase_op.get_all_purchase_details())
        return jsonify(purchases), 200
    except Exception as e:
        logger.error(f"Database error when fetching all purchases: {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred while fetching data."}), 500


@admin_bp.route('/search_purchase', methods=['GET'])
@admin_login_required
def search_purchase() -> Tuple[Any, int]:
    email = request.args.get('email')
    payment_id = request.args.get('payment_id')
    if not email or not payment_id:
        logger.warning(f"Search attempt with missing parameters from IP: {request.remote_addr}")
        return jsonify({"error": "Both email and payment_id are required for search."}), 400
    try:
        purchase = purchase_op.get_purchase_by_email_and_payment_id(email, payment_id)
        if purchase is None:
            return jsonify({"error": "A database error occurred."}), 500
        return jsonify(_serialise(purchase)), 200
    except Exception as e:
        logger.error(f"Error during purchase search for email '{email}': {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred during the search."}), 500


@admin_bp.route('/delete_purchase/<int:purchase_id>', methods=['DELETE'])
@admin_login_required
def delete_purchase(purchase_id: int) -> Tuple[Any, int]:
    admin_email = session.get('admin_email', 'UnknownAdmin')
    if purchase_id <= 0:
        return jsonify({"error": "Invalid purchase ID provided."}), 400
    try:
        logger.warning(f"PURCHASES DELETE: [{admin_email}] request for id={purchase_id}")
        success = purchase_op.delete_purchase_by_id(purchase_id)
        if success:
            return jsonify({"message": "Purchase deleted successfully"}), 200
        return jsonify({"error": "Purchase not found or it cannot be deleted (only 'Pending' rows can be removed)."}), 404
    except Exception:
        logger.exception(f"PURCHASES DELETE FAILED: [{admin_email}] id={purchase_id}")
        return jsonify({"error": "An internal server error occurred during deletion."}), 500


_LIVE_CACHE = {}
_LIVE_TTL = 60


def _live_payment(client, payment_id):
    now = datetime.now().timestamp()
    hit = _LIVE_CACHE.get(payment_id)
    if hit and now - hit[0] < _LIVE_TTL:
        return hit[1]
    try:
        p = client.payment.fetch(payment_id)
        out = {'status': p.get('status'), 'refund_status': p.get('refund_status'), 'amount': (p.get('amount') or 0) / 100.0,
               'method': p.get('method'), 'payment_id': payment_id, 'order_id': p.get('order_id'), 'known': True}
    except Exception as e:
        text = str(e).lower()
        out = {'status': 'unknown' if ('does not exist' in text or 'invalid' in text) else 'unreachable',
               'known': False, 'payment_id': payment_id}
    _LIVE_CACHE[payment_id] = (now, out)
    return out


def _live_order(client, order_id, expected_paise=None):
    now = datetime.now().timestamp()
    hit = _LIVE_CACHE.get(order_id)
    if hit and now - hit[0] < _LIVE_TTL:
        return hit[1]
    try:
        items = (client.order.payments(order_id) or {}).get('items') or []
    except Exception:
        out = {'status': 'unreachable', 'known': False, 'order_id': order_id}
        _LIVE_CACHE[order_id] = (now, out)
        return out
    out = {'status': 'unpaid', 'known': True, 'order_id': order_id, 'payment_id': None, 'attempts': len(items)}
    for pay in items:
        if pay.get('status') == 'captured':
            mismatch = expected_paise is not None and int(pay.get('amount') or 0) != int(expected_paise)
            out.update({'status': 'mismatch' if mismatch else 'captured', 'payment_id': pay.get('id'),
                        'amount': (pay.get('amount') or 0) / 100.0, 'refund_status': pay.get('refund_status'), 'method': pay.get('method')})
            break
        if pay.get('status') == 'authorized':
            out['status'] = 'authorized'; out['payment_id'] = pay.get('id')
        elif pay.get('status') == 'failed' and out['status'] == 'unpaid':
            out['status'] = 'failed'; out['payment_id'] = pay.get('id')
    _LIVE_CACHE[order_id] = (now, out)
    return out


def _verdict(gateway_status, refund_status, access):
    g = gateway_status or 'none'
    if g == 'captured' and refund_status in ('full', 'partial'):
        g = 'refunded'
    if g in ('captured',) and access == 'granted':
        return {'code': 'ok', 'kind': 'success', 'text': 'Paid and access granted', 'action': None}
    if g == 'captured' and access in ('not_granted', 'revoked'):
        return {'code': 'paid_no_access', 'kind': 'warning', 'text': 'Student PAID but has NO access - grant it', 'action': 'grant'}
    if g == 'captured' and access == 'expired':
        return {'code': 'expired', 'kind': 'secondary', 'text': 'Paid; plan period has ended', 'action': None}
    if g == 'refunded' and access == 'granted':
        return {'code': 'refunded_with_access', 'kind': 'danger', 'text': 'REFUNDED but still has access - revoke', 'action': 'revoke'}
    if g == 'refunded':
        return {'code': 'refunded', 'kind': 'secondary', 'text': 'Refunded, no access', 'action': None}
    if g == 'authorized':
        return {'code': 'authorized', 'kind': 'warning', 'text': 'Money on hold at the gateway, not captured yet', 'action': None}
    if g in ('failed', 'unpaid', 'none', 'unknown') and access == 'granted':
        return {'code': 'access_without_payment', 'kind': 'danger', 'text': 'Access granted but NO payment at gateway - revoke', 'action': 'revoke'}
    if g in ('failed', 'unpaid', 'none'):
        return {'code': 'not_paid', 'kind': 'secondary', 'text': 'No successful payment - claim is false', 'action': None}
    if g == 'mismatch':
        return {'code': 'mismatch', 'kind': 'danger', 'text': 'Amount paid does not match the order', 'action': None}
    if g == 'unknown':
        return {'code': 'unknown', 'kind': 'secondary', 'text': 'Razorpay does not know this ID', 'action': None}
    return {'code': 'unreachable', 'kind': 'secondary', 'text': 'Gateway not reachable - try again', 'action': None}


@admin_bp.route('/api/purchases/search-all', methods=['GET'])
@admin_login_required
def purchases_search_all():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify([])
    try:
        rows = purchase_op.search_everything(q, limit=30)
        logger.info(f"PURCHASES SEARCH-ALL: [{admin_email}] {q!r} -> {len(rows)} match(es)")
        return jsonify(_serialise(rows))
    except Exception:
        logger.exception(f"PURCHASES SEARCH-ALL FAILED: [{admin_email}] {q!r}")
        return jsonify({'error': 'Search failed.'}), 500


@admin_bp.route('/api/purchases/customer-detail', methods=['GET'])
@admin_login_required
def purchases_customer_detail():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    email = (request.args.get('email') or '').strip().lower()
    if not email:
        return jsonify({'error': 'Email is required.'}), 400
    try:
        data = purchase_op.get_customer_overview(email, None)
        data['subscriptions'] = purchase_op.get_subscription_detail(email)
        data['orders'] = [o for o in purchase_op.get_customer_orders(email) if o.get('status') != 'paid']
        for p in data['purchases']:
            p['access'] = 'granted' if p.get('status') == 'Paid' else ('revoked' if p.get('status') == 'Refunded' else 'not_granted')
            p['kind'] = 'paid'
        for s_ in data['subscriptions']:
            s_['access'] = 'granted' if s_.get('is_live') else ('expired' if s_.get('status') == 'active' else ('revoked' if s_.get('status') == 'refunded' else 'not_granted'))
            s_['kind'] = 'premium'
        for o in data['orders']:
            o['access'] = 'not_granted'
            o['kind'] = 'order'
            try:
                import json as _json
                o['items'] = ', '.join(c.get('title', '') for c in _json.loads(o.get('cart_json') or '[]'))
            except Exception:
                o['items'] = ''
            o.pop('cart_json', None)
        for key in ('purchases', 'enrollment_payments', 'subscriptions', 'orders'):
            data[key] = _serialise(data[key])
        if data['account']:
            data['account'] = _serialise([data['account']])[0]
        live = [x for x in data['subscriptions'] if x.get('is_live')]
        data['summary'] = {
            'username': (data['account'] or {}).get('username') or (data['purchases'][0].get('username') if data['purchases'] else None),
            'items': len(data['purchases']), 'enrollment_payments': len(data['enrollment_payments']),
            'subscriptions': len(data['subscriptions']), 'pending': len(data['orders']),
            'premium_active': bool(live), 'premium_courses': sorted({x.get('course_code') or 'all' for x in live}),
            'total_paid': data['total_paid'],
        }
        logger.info(f"PURCHASES DETAIL: [{admin_email}] {email!r} -> {data['summary']['items']} paid, "
                    f"{data['summary']['subscriptions']} premium, {data['summary']['pending']} unconfirmed")
        return jsonify(data)
    except Exception:
        logger.exception(f"PURCHASES DETAIL FAILED: [{admin_email}] {email!r}")
        return jsonify({'error': 'Could not load this customer.'}), 500


@admin_bp.route('/api/purchases/live', methods=['GET'])
@admin_login_required
def purchases_live():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    pids = [x for x in (request.args.get('payments') or '').split(',') if x.strip().startswith('pay_')][:40]
    orders = [x for x in (request.args.get('orders') or '').split(',') if x.strip().startswith('order_')][:40]
    client = _get_razorpay()
    if client is None:
        return jsonify({'live': False, 'reason': 'Razorpay is not configured on this server.', 'results': {}}), 503
    results = {}
    for pid in pids:
        info = _live_payment(client, pid)
        access = purchase_op.access_for_payment(pid)
        info['access'] = access
        info['verdict'] = _verdict(info.get('status'), info.get('refund_status'), access)
        results[pid] = info
    for oid in orders:
        row = purchase_op.content_order_by_order_id(oid) or purchase_op.subscription_by_order_id(oid)
        info = _live_order(client, oid, (row or {}).get('amount_paise'))
        access = 'not_granted'
        if row and (row.get('status') in ('paid', 'active')):
            access = 'granted'
        info['access'] = access
        info['verdict'] = _verdict(info.get('status'), info.get('refund_status'), access)
        results[oid] = info
    logger.info(f"PURCHASES LIVE: [{admin_email}] {len(pids)} payment(s), {len(orders)} order(s)")
    return jsonify({'live': True, 'results': results})


@admin_bp.route('/api/purchases/grant', methods=['POST'])
@admin_login_required
def purchases_grant():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    data = request.get_json(silent=True) or {}
    order_id = (data.get('order_id') or '').strip()
    if not order_id.startswith('order_'):
        return jsonify({'success': False, 'message': 'An order ID is required.'}), 400
    client = _get_razorpay()
    if client is None:
        return jsonify({'success': False, 'message': 'Razorpay is not configured on this server.'}), 503
    order = purchase_op.content_order_by_order_id(order_id)
    kind = 'content'
    if not order:
        order = purchase_op.subscription_by_order_id(order_id)
        kind = 'premium'
    if not order:
        return jsonify({'success': False, 'message': 'No order with that ID.'}), 404
    if order.get('status') in ('paid', 'active'):
        return jsonify({'success': False, 'message': 'This order is already fulfilled.'}), 409
    _LIVE_CACHE.pop(order_id, None)
    live = _live_order(client, order_id, order.get('amount_paise'))
    if live.get('status') != 'captured':
        logger.warning(f"GRANT REFUSED: [{admin_email}] {order_id} gateway says {live.get('status')}")
        return jsonify({'success': False, 'message': f"Razorpay does not show a captured payment for this order (status: {live.get('status')}). Nothing granted."}), 409
    payment_id = live['payment_id']
    if kind == 'content':
        n = purchase_op.grant_content_order(order, payment_id, admin_email, live.get('method') or 'razorpay')
        if not n:
            return jsonify({'success': False, 'message': 'The order has no items to grant.'}), 500
        message = f"Access granted: {n} item(s) unlocked for {order['email']} (payment {payment_id})."
    else:
        ends = purchase_op.grant_subscription(order, payment_id, admin_email)
        if not ends:
            return jsonify({'success': False, 'message': 'The plan behind this order no longer exists, so its end date is unknown. Re-create the plan in Premium Catalog, then grant again.'}), 409
        message = f"Premium activated for {order['email']} until {ends.strftime('%d %b %Y, %I:%M %p')} (payment {payment_id})."
    logger.warning(f"ADMIN ACTION by {admin_email}: GRANTED {kind} order {order_id} for {order['email']} after live check {payment_id}")
    _LIVE_CACHE.pop(payment_id, None)
    return jsonify({'success': True, 'message': message, 'payment_id': payment_id})


@admin_bp.route('/api/purchases/revoke', methods=['POST'])
@admin_login_required
def purchases_revoke():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    data = request.get_json(silent=True) or {}
    payment_id = (data.get('payment_id') or '').strip()
    if not payment_id.startswith('pay_'):
        return jsonify({'success': False, 'message': 'A payment ID is required.'}), 400
    client = _get_razorpay()
    if client is None:
        return jsonify({'success': False, 'message': 'Razorpay is not configured on this server.'}), 503
    _LIVE_CACHE.pop(payment_id, None)
    live = _live_payment(client, payment_id)
    refunded = live.get('status') == 'refunded' or live.get('refund_status') in ('full', 'partial')
    unpaid = live.get('status') in ('failed', 'unknown') or (live.get('known') and live.get('status') not in ('captured', 'authorized', 'refunded'))
    if not (refunded or unpaid or data.get('force') is True):
        return jsonify({'success': False, 'message': f"Razorpay shows this payment as {live.get('status')} - it is a real, unrefunded payment. Revoke is only for refunded or unpaid ones (send force to override)."}), 409
    n = purchase_op.revoke_payment(payment_id, admin_email)
    logger.warning(f"ADMIN ACTION by {admin_email}: REVOKED access for payment {payment_id} ({n} row(s)); gateway={live.get('status')}/{live.get('refund_status')}")
    return jsonify({'success': True, 'message': f"Access revoked for payment {payment_id} ({n} record(s) updated)."})


@admin_bp.route('/api/purchases/attention', methods=['GET'])
@admin_login_required
def purchases_attention():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    client = _get_razorpay()
    if client is None:
        return jsonify({'live': False, 'reason': 'Razorpay is not configured on this server.', 'items': []}), 503
    unconfirmed, granted = purchase_op.attention_candidates()
    items = []
    for row in unconfirmed[:40]:
        live = _live_order(client, row['razorpay_order_id'], row.get('amount_paise'))
        verdict = _verdict(live.get('status'), live.get('refund_status'), 'not_granted')
        if verdict['code'] in ('paid_no_access', 'mismatch', 'authorized'):
            items.append({**row, 'gateway': live, 'verdict': verdict})
    for row in granted[:40]:
        pid = row.get('razorpay_payment_id')
        if not pid or not str(pid).startswith('pay_'):
            continue
        live = _live_payment(client, pid)
        verdict = _verdict(live.get('status'), live.get('refund_status'), 'granted')
        if verdict['code'] in ('refunded_with_access', 'access_without_payment'):
            items.append({**row, 'gateway': live, 'verdict': verdict})
    items = _serialise(items)
    logger.info(f"PURCHASES ATTENTION: [{admin_email}] {len(items)} item(s) need attention")
    return jsonify({'live': True, 'items': items, 'scanned': len(unconfirmed) + len(granted)})

