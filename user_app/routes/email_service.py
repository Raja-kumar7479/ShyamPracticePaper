import logging
from flask import current_app
from flask_mail import Mail, Message

logger = logging.getLogger(__name__)
mail = Mail()

BRAND_PRIMARY = "#3a0f0f"
BRAND_DARK = "#2a1512"
BRAND_HEADING = "#992c25"


def _brand():
    try:
        return current_app.config.get("BRAND_NAME", "ShyamPracticePaper")
    except Exception:
        return "ShyamPracticePaper"


def code_block(value):
    return (
        f'<div style="margin:22px 0;text-align:center;">'
        f'<span style="display:inline-block;background:#fdf3e3;border:1px dashed #db9504;'
        f'border-radius:10px;padding:14px 28px;font-size:28px;letter-spacing:8px;'
        f'font-weight:700;color:{BRAND_DARK};font-family:\'Courier New\',monospace;">{value}</span>'
        f'</div>'
    )


def info_rows(rows):
    cells = ""
    for label, val in rows:
        cells += (
            f'<tr>'
            f'<td style="padding:8px 0;color:#6b6b6b;font-size:14px;">{label}</td>'
            f'<td style="padding:8px 0;color:{BRAND_DARK};font-size:14px;font-weight:600;text-align:right;">{val}</td>'
            f'</tr>'
        )
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="margin:18px 0;border-top:1px solid #e8e2e0;">{cells}</table>'
    )


def render_email(heading, body_html, cta_text=None, cta_url=None, preheader=""):
    brand = _brand()
    button = ""
    if cta_text and cta_url:
        button = (
            f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:8px 0 6px;">'
            f'<tr><td align="center" bgcolor="#db9504" style="border-radius:8px;">'
            f'<a href="{cta_url}" style="display:inline-block;padding:13px 34px;font-size:15px;'
            f'font-weight:700;color:#5c1a15;text-decoration:none;">{cta_text}</a>'
            f'</td></tr></table>'
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#fafafa;font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
<span style="display:none;max-height:0;overflow:hidden;opacity:0;">{preheader}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fafafa;padding:28px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 8px 30px rgba(2,6,23,.08);">
<tr><td style="background:{BRAND_PRIMARY};padding:26px 32px;border-bottom:4px solid #db9504;">
<span style="color:#ffffff;font-size:20px;font-weight:700;letter-spacing:.3px;">{brand}</span>
</td></tr>
<tr><td style="padding:34px 32px 12px;">
<h1 style="margin:0 0 14px;font-size:22px;line-height:1.3;color:{BRAND_HEADING};">{heading}</h1>
<div style="font-size:15px;line-height:1.65;color:#444444;">{body_html}</div>
{button}
</td></tr>
<tr><td style="padding:22px 32px 30px;border-top:1px solid #e8e2e0;">
<p style="margin:0;font-size:12px;line-height:1.6;color:#8a7a74;">You are receiving this email because an action was taken on your {brand} account. If this wasn't you, please ignore this message.</p>
<p style="margin:10px 0 0;font-size:12px;color:#cbd5e1;">&copy; {brand}. All rights reserved.</p>
</td></tr>
</table>
</td></tr>
</table>
</body></html>"""


def send_enrollment_email(email, username, course_name, unique_code, dashboard_url, paid=False, amount=None):
    rows = [("Course", course_name)]
    if paid and amount is not None:
        rows.append(("Amount paid", f"₹{amount}"))
    rows.append(("Access", "Paid" if paid else "Free enrollment"))
    body = (
        f"<p>Hi {username},</p>"
        f"<p>You're successfully enrolled in <strong>{course_name}</strong>. "
        f"Your course dashboard is ready whenever you want to start learning.</p>"
        f"{info_rows(rows)}"
    )
    html = render_email("You're enrolled \U0001F680", body,
                        cta_text="Open your course", cta_url=dashboard_url,
                        preheader=f"You're enrolled in {course_name}")
    return send_email(f"Enrolled: {course_name}", email, html)


def send_email(subject, recipients, html, attachments=None):
    try:
        if isinstance(recipients, str):
            recipients = [recipients]
        msg = Message(subject=subject, recipients=recipients)
        msg.html = html
        if attachments:
            for name, content_type, data in attachments:
                msg.attach(name, content_type, data)
        mail.send(msg)
        logger.info("Email sent to %s (subject=%s)", recipients, subject)
        return True
    except Exception as e:
        logger.error("Email send failed to %s: %s", recipients, e)
        return False
