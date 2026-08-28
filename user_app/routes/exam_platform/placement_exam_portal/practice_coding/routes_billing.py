"""Premium subscription for the practice platform, paid through Razorpay.

Flow: premium page -> phone + billing summary (browser) -> create order
(server) -> Razorpay checkout (browser) -> verify signature (server) ->
subscription activated. The signature check is the authority; nothing the
browser sends is trusted on its own.

The phone step exists because the checkout used to open with no contact
prefilled, so Razorpay filled that field from whatever it had remembered in
the browser and buyers saw a number that was not theirs.
"""
import hashlib
import hmac
import logging
from datetime import datetime, timedelta

from flask import jsonify, redirect, render_template, request, url_for

from config import Config
from extensions import limiter
from . import models
from .auth import csrf_protect, current_user, login_required
from .routes_practice import bp, has_premium

logger = logging.getLogger(__name__)

# Paise. Overridable from the environment without a deploy.
PLANS = {
    "monthly": {"label": "Monthly", "amount": int(getattr(Config, "PCP_MONTHLY_PAISE", 0) or 99900),
                "days": 30},
    "yearly": {"label": "Yearly", "amount": int(getattr(Config, "PCP_YEARLY_PAISE", 0) or 699900),
               "days": 365},
}


def _clean_phone(data):
    """Validates the buyer's contact number.

    Returns (phone, error). The rule matches the course checkout
    (utils_phone.validate_phone_number) so a student sees one standard across
    the site.
    """
    phone = "".join(ch for ch in str(data.get("phone") or "") if ch.isdigit())
    # A pasted +91 / 0 prefix is a formatting habit, not a different number.
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
def premium():
    user = current_user()
    subscription = models.active_subscription(user["email"])
    from . import models_quiz
    return render_template(
        "users/exam_platform/placement_exam_portal/practice_coding/premium.html",
        user=user, plans=PLANS, subscription=subscription,
        quiz_count=models_quiz.premium_quiz_count(),
        razorpay_key=getattr(Config, "RAZORPAY_KEY_ID", "") or "")


@bp.route("/api/subscribe/order", methods=["POST"])
@login_required
@csrf_protect
@limiter.limit("10 per minute")
def subscribe_order(**kwargs):
    user = current_user()
    if has_premium(user["email"]):
        return jsonify({"error": "You already have an active subscription."}), 409

    payload = request.get_json(silent=True) or {}
    plan_key = payload.get("plan")
    plan = PLANS.get(plan_key)
    if not plan:
        return jsonify({"error": "Choose the monthly or yearly plan."}), 400

    phone, phone_error = _clean_phone(payload)
    if phone_error:
        return jsonify({"error": phone_error}), 400

    client = _razorpay_client()
    if not client:
        return jsonify({"error": "Payments are not configured on this server yet."}), 503

    try:
        order = client.order.create({
            "amount": plan["amount"], "currency": "INR", "payment_capture": 1,
            "notes": {"email": user["email"], "product": "practice_coding_premium",
                      "plan": plan_key, "phone": phone},
        })
    except Exception:
        logger.exception("PRACTICE BILLING: order create failed for %s", user["email"])
        return jsonify({"error": "Payment gateway error. Please try again."}), 502

    try:
        models.create_subscription_order(user["email"], plan_key, plan["amount"],
                                         order["id"], phone)
    except Exception:
        # Without this row the verify step cannot match the payment, so stop
        # the buyer here instead of letting them pay against a lost order.
        logger.exception("PRACTICE BILLING: could not record order %s for %s",
                         order["id"], user["email"])
        return jsonify({"error": "Could not start the payment. Please try again."}), 500
    logger.info("PRACTICE BILLING: order %s (%s) for %s", order["id"], plan_key, user["email"])
    return jsonify({
        "order_id": order["id"], "amount": plan["amount"], "currency": "INR",
        "key_id": getattr(Config, "RAZORPAY_KEY_ID", ""),
        "email": user["email"], "username": user["username"], "plan": plan_key,
        # Sent back from the server so the checkout is prefilled with the
        # number that was actually validated and stored, not the raw input.
        "contact": phone,
    })


@bp.route("/api/subscribe/verify", methods=["POST"])
@login_required
@csrf_protect
@limiter.limit("10 per minute")
def subscribe_verify(**kwargs):
    user = current_user()
    data = request.get_json(silent=True) or {}
    order_id = data.get("razorpay_order_id")
    payment_id = data.get("razorpay_payment_id")
    signature = data.get("razorpay_signature")

    row = models.get_subscription_by_order(order_id or "")
    if not row or row["email"] != user["email"]:
        return jsonify({"error": "Unknown payment. Please contact support."}), 404
    if row["status"] == "active":
        return jsonify({"success": True, "already": True})

    secret = getattr(Config, "RAZORPAY_KEY_SECRET", None)
    if not (secret and order_id and payment_id and signature):
        return jsonify({"error": "Payment could not be verified."}), 400
    expected = hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(),
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        logger.warning("PRACTICE BILLING: BAD SIGNATURE for %s order %s",
                       user["email"], order_id)
        return jsonify({"error": "Payment verification failed."}), 400

    days = PLANS.get(row["plan"], {}).get("days", 30)
    starts = datetime.now()
    expires = starts + timedelta(days=days)
    models.activate_subscription(order_id, payment_id, starts, expires)
    logger.info("PRACTICE BILLING: ACTIVATED %s plan for %s until %s",
                row["plan"], user["email"], expires.date())

    # A subscription is a purchase, so it gets the same itemised PDF receipt a
    # course purchase does. The email is best-effort: a mail failure must not
    # undo a payment that has already been verified and activated.
    emailed = _send_subscription_receipt(user, row, payment_id, starts, expires)

    return jsonify({"success": True,
                    "receipt_emailed": emailed,
                    "redirect": url_for("practice_coding.home", tier="paid")})


def _row_value(row, key):
    """Reads a column that older subscription rows may not carry at all."""
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return None


def _subscription_receipt_pdf(user, row, payment_id, starts, expires):
    """The same PDF builder the course checkout uses, fed one subscription line."""
    from routes.courses_platform.payment.purchased_payment.utils.utils_receipt import (
        generate_pdf_receipt)

    plan = PLANS.get(row["plan"], {})
    amount = (row["amount_paise"] or 0) / 100.0
    label = f"Coding Practice Premium - {plan.get('label', row['plan'].title())} plan"
    validity = f"{starts.strftime('%d %b %Y')} to {expires.strftime('%d %b %Y')}"

    return generate_pdf_receipt(
        username=user.get("username") or user["email"],
        email=user["email"],
        phone=_row_value(row, "phone") or "",
        payment_id=payment_id,
        purchases=[{"title": label, "subtitle": f"Valid {validity}",
                    "price": amount, "final_price": amount,
                    "purchase_date": starts}],
        discount=0,
        original_price=amount,
        final_amount=amount,
        payment_mode="Razorpay",
        status="Paid",
        purchase_date=starts)


def _send_subscription_receipt(user, row, payment_id, starts, expires):
    from routes.email_service import render_email, send_email

    try:
        pdf = _subscription_receipt_pdf(user, row, payment_id, starts, expires)
        plan = PLANS.get(row["plan"], {})
        amount = (row["amount_paise"] or 0) / 100.0
        body = (
            f"<p>Hi {user.get('username') or 'there'},</p>"
            f"<p>Your <strong>{plan.get('label', row['plan'].title())}</strong> Coding Practice "
            f"Premium subscription is active.</p>"
            f"<p><strong>Amount paid:</strong> &#8377;{amount:.2f}<br>"
            f"<strong>Payment ID:</strong> {payment_id}<br>"
            f"<strong>Active until:</strong> {expires.strftime('%d %b %Y')}</p>"
            f"<p>Your itemised receipt is attached as a PDF, and it is always available "
            f"from your purchases dashboard.</p>")
        html = render_email("Your premium subscription is active", body,
                            preheader="Your receipt is attached")
        sent = send_email("Your Coding Practice Premium receipt", user["email"], html,
                          attachments=[("receipt.pdf", "application/pdf", pdf.getvalue())])
        logger.info("PRACTICE BILLING: receipt email to %s -> %s", user["email"], bool(sent))
        return bool(sent)
    except Exception:
        logger.exception("PRACTICE BILLING: could not send the receipt for %s", user["email"])
        return False


@bp.route("/api/subscribe/webhook", methods=["POST"])
@limiter.limit("60 per minute")
def subscribe_webhook():
    """Server-to-server payment confirmation from Razorpay.

    Covers the buyer whose browser never came back after paying: the money is
    captured but the verify call never arrived, so the subscription would stay
    'created' until support stepped in. Authenticated purely by the webhook
    signature; disabled (404) until RAZORPAY_WEBHOOK_SECRET is configured.
    """
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

    days = PLANS.get(row["plan"], {}).get("days", 30)
    starts = datetime.now()
    expires = starts + timedelta(days=days)
    models.activate_subscription(order_id, payment_id, starts, expires)
    logger.info("PRACTICE BILLING: WEBHOOK ACTIVATED %s plan for %s until %s",
                row["plan"], row["email"], expires.date())

    user = {"email": row["email"], "username": _row_value(row, "username") or row["email"]}
    _send_subscription_receipt(user, row, payment_id, starts, expires)
    return jsonify({"status": "activated"}), 200


@bp.route("/subscription/receipt/<payment_id>")
@login_required
def subscription_receipt(payment_id):
    """Re-download the receipt for a subscription this account paid for."""
    from flask import abort, send_file
    from io import BytesIO

    user = current_user()
    row = models.get_subscription_by_payment(payment_id)
    # Ownership is checked against the signed-in account, so a payment id
    # guessed from somewhere else cannot pull another student's receipt.
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
