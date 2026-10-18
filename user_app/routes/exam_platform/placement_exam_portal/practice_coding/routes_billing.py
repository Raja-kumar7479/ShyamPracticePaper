import hashlib
import hmac
import logging
from datetime import datetime, timedelta

from flask import jsonify, redirect, render_template, request, session, url_for

from config import Config
from extensions import limiter
from . import models
from .auth import csrf_protect, current_user, login_required
from .routes_practice import bp, has_premium

logger = logging.getLogger(__name__)

PLANS = {
    "monthly": {"label": "Monthly", "amount": int(getattr(Config, "PCP_MONTHLY_PAISE", 0) or 99900),
                "days": 30},
    "yearly": {"label": "Yearly", "amount": int(getattr(Config, "PCP_YEARLY_PAISE", 0) or 699900),
               "days": 365},
}


def _portal_plans():
    out = []
    for key, plan in PLANS.items():
        rupees = plan["amount"] / 100.0
        ends = datetime.now() + timedelta(days=plan["days"])
        out.append({'key': key, 'label': plan["label"], 'price': rupees, 'payable': rupees,
                    'amount': plan["amount"], 'discount': 0.0, 'saved': 0.0, 'offer_ends_at': None,
                    'valid_until': ends, 'ends_at': ends, 'is_dated': True, 'days': plan["days"], 'extra_days': 0,
                    'available': True, 'featured': key == 'yearly'})
    return out


def _clean_phone(data):
    phone = "".join(ch for ch in str(data.get("phone") or "") if ch.isdigit())
    if len(phone) == 12 and phone.startswith("91"):
        phone = phone[2:]
    elif len(phone) == 11 and phone.startswith("0"):
        phone = phone[1:]
    if len(phone) != 10 or phone[0] == "0":
        return None, "Enter a valid 10-digit phone number starting from 1-9."
    return phone, None


def _razorpay_client():
    key = getattr(Config, "RAZORPAY_KEY_ID", None)
    secret = getattr(Config, "RAZORPAY_KEY_SECRET", None)
    if not key or not secret:
        return None
    try:
        import razorpay
        return razorpay.Client(auth=(key, secret))
    except Exception:
        logger.exception("PRACTICE BILLING: razorpay client init failed")
        return None


@bp.route("/premium")
@bp.route("/premium/<course_code>/<unique_code>")
@login_required
def premium(course_code=None, unique_code=None):
    user = current_user()
    subscription = models.active_subscription(user["email"])
    from . import models_quiz

    course_code = course_code or session.get("pcp_course_code")
    unique_code = unique_code or session.get("pcp_unique_code")
    if course_code and unique_code:
        return redirect(url_for("users.premium_details_page",
                                course_code=course_code, unique_code=unique_code))

    from_course = request.args.get("src") == "course" and course_code and unique_code
    if from_course:
        back_url = url_for("users.view_course_dashboard",
                           course_code=course_code, unique_code=unique_code)
        back_label = "Back to your course"
        next_url = back_url
    else:
        back_url = url_for("practice_coding.home")
        back_label = "Problems"
        next_url = ""
    return render_template(
        "users/exam_platform/placement_exam_portal/practice_coding/premium.html",
        user=user, plans=_portal_plans(), subscription=subscription,
        quiz_count=models_quiz.premium_quiz_count(),
        back_url=back_url, back_label=back_label, next_url=next_url,
        from_course=bool(from_course),
        order_url=url_for("practice_coding.subscribe_order"),
        verify_url=url_for("practice_coding.subscribe_verify"),
        razorpay_key=getattr(Config, "RAZORPAY_KEY_ID", "") or "")


def start_subscription_order(user, payload):
    from routes.exam_platform.premium_catalog import premium_offer
    course_code = (payload.get("course_code") or session.get("pcp_course_code") or "").strip().upper() or None
    if not course_code:
        return {"error": "Open premium from your course so we know which course to unlock."}, 400
    if not models._one("SELECT 1 FROM enrollment WHERE email = %s AND code = %s LIMIT 1", (user["email"], course_code)):
        logger.warning("PRACTICE BILLING: %s tried to buy premium for %s without enrolment", user["email"], course_code)
        return {"error": "You are not enrolled in this course."}, 403
    current = models.active_subscription(user["email"], course_code)
    if current:
        logger.warning("PRACTICE BILLING: %s tried to buy premium for %s again while it is active until %s",
                       user["email"], course_code, current.get("expires_at"))
        ends = current.get("expires_at")
        return {"error": "You already have premium for this course"
                         + (f" until {ends.strftime('%d %b %Y, %I:%M %p')}" if ends else "")
                         + ". You can buy it again after it ends."}, 409

    offer = premium_offer(course_code)
    plan_key = payload.get("plan")
    plan = offer["by_key"].get(plan_key)
    if not plan:
        return {"error": "Choose one of the plans on this page."}, 400
    if not plan["available"]:
        return {"error": f"The {plan['label']} plan is no longer on sale."}, 403

    phone, phone_error = _clean_phone(payload)
    if phone_error:
        return {"error": phone_error}, 400

    open_order = models._one("""
        SELECT razorpay_order_id FROM pcp_subscriptions
         WHERE email = %s AND course_code = %s AND plan = %s AND amount_paise = %s
           AND status = 'created' AND created_at > %s
         ORDER BY id DESC LIMIT 1
    """, (user["email"], course_code, plan_key, plan["amount"], datetime.now() - timedelta(minutes=30)))
    if open_order:
        logger.info("PRACTICE BILLING: reusing open order %s for %s (%s)",
                    open_order["razorpay_order_id"], user["email"], course_code)
        return {
            "order_id": open_order["razorpay_order_id"], "amount": plan["amount"], "currency": "INR",
            "key_id": getattr(Config, "RAZORPAY_KEY_ID", ""),
            "email": user["email"], "username": user["username"], "plan": plan_key,
            "contact": phone,
        }, 200

    client = _razorpay_client()
    if not client:
        return {"error": "Payments are not configured on this server yet."}, 503

    try:
        order = client.order.create({
            "amount": plan["amount"], "currency": "INR", "payment_capture": 1,
            "notes": {"email": user["email"], "product": "premium",
                      "course": course_code, "plan": plan_key, "phone": phone},
        })
    except Exception:
        logger.exception("PRACTICE BILLING: order create failed for %s", user["email"])
        return {"error": "Payment gateway error. Please try again."}, 502

    try:
        models.create_subscription_order(user["email"], plan_key, plan["amount"],
                                         order["id"], phone, course_code,
                                         int(round(plan["price"] * 100)), plan["discount"], plan["label"], plan_ends_at=plan.get('ends_at'))
    except Exception:
        logger.exception("PRACTICE BILLING: could not record order %s for %s",
                         order["id"], user["email"])
        return {"error": "Could not start the payment. Please try again."}, 500
    logger.info("PRACTICE BILLING: order %s (%s, %s, %s paise) for %s",
                order["id"], course_code, plan_key, plan["amount"], user["email"])
    return {
        "order_id": order["id"], "amount": plan["amount"], "currency": "INR",
        "key_id": getattr(Config, "RAZORPAY_KEY_ID", ""),
        "email": user["email"], "username": user["username"], "plan": plan_key,
        "contact": phone,
    }, 200


@bp.route("/api/subscribe/order", methods=["POST"])
@login_required
@csrf_protect
@limiter.limit("10 per minute")
def subscribe_order(**kwargs):
    body, status = start_subscription_order(current_user(), request.get_json(silent=True) or {})
    return jsonify(body), status


def confirm_subscription_payment(user, data):
    order_id = data.get("razorpay_order_id")
    payment_id = data.get("razorpay_payment_id")
    signature = data.get("razorpay_signature")

    row = models.get_subscription_by_order(order_id or "")
    if not row or row["email"] != user["email"]:
        return {"error": "Unknown payment. Please contact support."}, 404
    if row["status"] == "active":
        return {"success": True, "already": True}, 200

    secret = getattr(Config, "RAZORPAY_KEY_SECRET", None)
    if not (secret and order_id and payment_id and signature):
        return {"error": "Payment could not be verified."}, 400
    expected = hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(),
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        logger.warning("PRACTICE BILLING: BAD SIGNATURE for %s order %s",
                       user["email"], order_id)
        return {"error": "Payment verification failed."}, 400

    starts, expires = _period(user["email"], _row_value(row, "course_code"), row["plan"], _row_value(row, "plan_ends_at"))
    models.activate_subscription(order_id, payment_id, starts, expires)
    logger.info("PRACTICE BILLING: ACTIVATED %s plan for %s from %s until %s",
                row["plan"], user["email"], starts.date(), expires.date())

    emailed = _send_subscription_receipt(user, row, payment_id, starts, expires)

    return {"success": True,
            "receipt_emailed": emailed,
            "redirect": url_for("practice_coding.home", tier="paid")}, 200


@bp.route("/api/subscribe/verify", methods=["POST"])
@login_required
@csrf_protect
@limiter.limit("10 per minute")
def subscribe_verify(**kwargs):
    body, status = confirm_subscription_payment(current_user(), request.get_json(silent=True) or {})
    return jsonify(body), status


def _period(email, course_code, plan_key, plan_ends_at=None):
    from routes.exam_platform.premium_catalog import plan_expiry, premium_offer
    now = datetime.now()
    current = models.active_subscription(email, course_code)
    current_end = current.get("expires_at") if current else None
    if current:
        logger.critical("PREMIUM DOUBLE PAYMENT: %s already had premium for %s until %s when another payment "
                        "was confirmed - refund the second payment from Razorpay", email, course_code, current_end)
    if plan_ends_at and plan_ends_at > now:
        return now, current_end if current_end and current_end > plan_ends_at else plan_ends_at
    plan = (premium_offer(course_code)["by_key"] or {}).get(plan_key)
    if not plan:
        starts = current_end if current_end and current_end > now else now
        return starts, starts + timedelta(days=30)
    return now, plan_expiry(plan, now, current_end)


def _course_label(course_code):
    if not course_code:
        return "Coding Practice"
    row = models._one("SELECT name FROM courses WHERE code = %s LIMIT 1", (course_code,))
    name = (row or {}).get("name")
    return f"{name} ({course_code})" if name and name.upper() != course_code.upper() else course_code


def _row_value(row, key):
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return None


def _subscription_receipt_pdf(user, row, payment_id, starts, expires):
    from routes.courses_platform.payment.purchased_payment.utils.utils_receipt import (
        generate_pdf_receipt)

    plan_label = _row_value(row, "plan_label") or str(row["plan"]).title()
    amount = (row["amount_paise"] or 0) / 100.0
    list_paise = _row_value(row, "list_paise")
    original = (list_paise / 100.0) if list_paise else amount
    discount_pct = float(_row_value(row, "discount_pct") or 0) if list_paise else 0.0
    label = f"{_course_label(_row_value(row, 'course_code'))} Premium - {plan_label}"
    validity = f"{starts.strftime('%d %b %Y')} to {expires.strftime('%d %b %Y')}"
    if discount_pct > 0:
        validity += f" - {discount_pct:g}% discount applied"

    return generate_pdf_receipt(
        username=user.get("username") or user["email"],
        email=user["email"],
        phone=_row_value(row, "phone") or "",
        payment_id=payment_id,
        purchases=[{"title": label, "subtitle": f"Valid {validity}",
                    "price": original, "final_price": amount,
                    "purchase_date": starts}],
        discount=discount_pct,
        original_price=original,
        final_amount=amount,
        payment_mode="Razorpay",
        status="Paid",
        purchase_date=starts)


def _send_subscription_receipt(user, row, payment_id, starts, expires):
    from routes.email_service import render_email, send_email

    try:
        pdf = _subscription_receipt_pdf(user, row, payment_id, starts, expires)
        plan_label = _row_value(row, "plan_label") or str(row["plan"]).title()
        amount = (row["amount_paise"] or 0) / 100.0
        course = _course_label(_row_value(row, "course_code"))
        list_paise = _row_value(row, "list_paise")
        original = (list_paise / 100.0) if list_paise else amount
        discount_pct = float(_row_value(row, "discount_pct") or 0) if list_paise else 0.0
        price_lines = (
            f"<strong>Price:</strong> &#8377;{original:.2f}<br>"
            f"<strong>Discount:</strong> {discount_pct:g}% (&#8377;{original - amount:.2f})<br>"
            if discount_pct > 0 else "")
        body = (
            f"<p>Hi {user.get('username') or 'there'},</p>"
            f"<p>Your <strong>{plan_label}</strong> premium subscription for "
            f"<strong>{course}</strong> is active. Every premium test, note and practice set in {course} is now open.</p>"
            f"<p>{price_lines}<strong>Amount paid:</strong> &#8377;{amount:.2f}<br>"
            f"<strong>Payment ID:</strong> {payment_id}<br>"
            f"<strong>Active until:</strong> {expires.strftime('%d %b %Y')}</p>"
            f"<p>Your itemised receipt is attached as a PDF, and it is always available "
            f"from your purchases dashboard.</p>")
        html = render_email("Your premium subscription is active", body,
                            preheader="Your receipt is attached")
        sent = send_email(f"Your {course} Premium receipt", user["email"], html,
                          attachments=[("receipt.pdf", "application/pdf", pdf.getvalue())])
        logger.info("PRACTICE BILLING: receipt email to %s -> %s", user["email"], bool(sent))
        return bool(sent)
    except Exception:
        logger.exception("PRACTICE BILLING: could not send the receipt for %s", user["email"])
        return False


@bp.route("/api/subscribe/webhook", methods=["POST"])
@limiter.limit("1200 per minute")
def subscribe_webhook():
    secret = getattr(Config, "RAZORPAY_WEBHOOK_SECRET", None)
    if not secret:
        return jsonify({"error": "not found"}), 404

    body = request.get_data()
    signature = request.headers.get("X-Razorpay-Signature", "")
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        logger.warning("PRACTICE BILLING: webhook BAD SIGNATURE from %s", request.remote_addr)
        return jsonify({"error": "invalid signature"}), 400

    event = request.get_json(silent=True) or {}
    if event.get("event") not in ("payment.captured", "order.paid"):
        return jsonify({"status": "ignored"}), 200

    payment = (((event.get("payload") or {}).get("payment") or {}).get("entity") or {})
    order_id = payment.get("order_id")
    payment_id = payment.get("id")
    if not order_id or not payment_id:
        return jsonify({"status": "ignored"}), 200

    row = models.get_subscription_by_order(order_id)
    if not row:
        return jsonify({"status": "ignored"}), 200
    if row["status"] == "active":
        return jsonify({"status": "already_active"}), 200

    if payment.get("amount") is not None and int(payment["amount"]) != int(row["amount_paise"] or 0):
        logger.critical("PRACTICE BILLING: webhook AMOUNT MISMATCH order %s paid=%s expected=%s",
                        order_id, payment.get("amount"), row["amount_paise"])
        return jsonify({"error": "amount mismatch"}), 400

    starts, expires = _period(row["email"], _row_value(row, "course_code"), row["plan"], _row_value(row, "plan_ends_at"))
    models.activate_subscription(order_id, payment_id, starts, expires, fulfilled_by='webhook')
    logger.info("PRACTICE BILLING: WEBHOOK ACTIVATED %s plan for %s from %s until %s",
                row["plan"], row["email"], starts.date(), expires.date())

    user = {"email": row["email"], "username": _row_value(row, "username") or row["email"]}
    _send_subscription_receipt(user, row, payment_id, starts, expires)
    return jsonify({"status": "activated"}), 200


def subscription_receipt_file(user, payment_id):
    from flask import abort, send_file
    from io import BytesIO

    row = models.get_subscription_by_payment(payment_id)
    if not row or row["email"] != user["email"] or row["status"] != "active":
        logger.warning("PRACTICE BILLING: receipt denied for %s payment %s",
                       user["email"], payment_id)
        abort(404)

    pdf = _subscription_receipt_pdf(user, row, payment_id,
                                    row["starts_at"] or datetime.now(),
                                    row["expires_at"] or datetime.now())
    return send_file(BytesIO(pdf.getvalue()), mimetype="application/pdf",
                     as_attachment=True,
                     download_name=f"premium-receipt-{payment_id}.pdf")


@bp.route("/subscription/receipt/<payment_id>")
@login_required
def subscription_receipt(payment_id):
    return subscription_receipt_file(current_user(), payment_id)
