from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO
import time
import hmac
import hashlib
import base64
import os
import logging
import random
import string
from datetime import datetime
from flask import session, flash, redirect, url_for, request

logger = logging.getLogger(__name__)

_download_secret = os.getenv("DOWNLOAD_SECRET_KEY") or os.getenv("SECRET_KEY")
if not _download_secret:
    raise RuntimeError("DOWNLOAD_SECRET_KEY or SECRET_KEY must be set for receipt download tokens.")
DOWNLOAD_SECRET = _download_secret.encode()

PRIMARY = colors.HexColor("#3a0f0f")
PRIMARY_SOFT = colors.HexColor("#fdf3e3")
INK = colors.HexColor("#2a1512")
MUTED = colors.HexColor("#8a7a74")
LINE = colors.HexColor("#e8e2e0")
ZEBRA = colors.HexColor("#fafafa")


def _money(value):
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0
    return "Rs. {:,.2f}".format(amount)


def _resolve_purchase_date(purchase_date, purchases):
    if purchase_date is None and purchases:
        for item in purchases:
            candidate = item.get('payment_date') if hasattr(item, 'get') else None
            if candidate:
                purchase_date = candidate
                break

    if isinstance(purchase_date, str):
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
            try:
                purchase_date = datetime.strptime(purchase_date, fmt)
                break
            except ValueError:
                continue

    if not isinstance(purchase_date, datetime):
        return None
    return purchase_date


def generate_pdf_receipt(username, email, phone, payment_id, purchases, discount,
                         original_price, final_amount, payment_mode, status,
                         purchase_date=None):
    issued_on = _resolve_purchase_date(purchase_date, purchases)
    date_long = issued_on.strftime('%d %b %Y, %H:%M') if issued_on else time.strftime('%d %b %Y, %H:%M')
    date_short = issued_on.strftime('%d %b %Y') if issued_on else time.strftime('%d %b %Y')

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=42, leftMargin=42, topMargin=40, bottomMargin=44)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Muted', fontSize=9, textColor=MUTED))
    styles.add(ParagraphStyle(name='Section', fontSize=11, leading=14, spaceBefore=6, spaceAfter=8,
                              textColor=PRIMARY, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name='Cell', fontSize=10, leading=13, textColor=INK))
    styles.add(ParagraphStyle(name='Amount', fontSize=10, leading=13, textColor=INK,
                              alignment=2, fontName='Helvetica-Bold'))
    is_paid = str(status).lower() == 'paid'
    badge_bg = colors.HexColor("#dcfce7") if is_paid else colors.HexColor("#fef3c7")
    badge_fg = colors.HexColor("#15803d") if is_paid else colors.HexColor("#b45309")

    elements = []

    brand = Paragraph('<font size=17 color="#ffffff"><b>ShyamPracticePaper</b></font>'
                      '<br/><font size=9 color="#db9504">Learning &amp; Assessment Platform</font>', styles['Normal'])
    meta = Paragraph(f'<para align=right><font size=15 color="#ffffff"><b>RECEIPT</b></font>'
                     f'<br/><font size=8 color="#db9504">Payment ID: {payment_id}<br/>Purchased: {date_long}</font></para>', styles['Normal'])
    header = Table([[brand, meta]], colWidths=[300, 210])
    header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), PRIMARY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 20),
        ('RIGHTPADDING', (0, 0), (-1, -1), 20),
        ('TOPPADDING', (0, 0), (-1, -1), 18),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 18),
        ('ROUNDEDCORNERS', [8, 8, 8, 8]),
    ]))
    elements.append(header)
    elements.append(Spacer(1, 20))

    badge = Table([[Paragraph(f'<font color="#{badge_fg.hexval()[2:]}"><b>{str(status).upper()}</b></font>', styles['Cell'])]],
                  colWidths=[70])
    badge.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), badge_bg),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('ROUNDEDCORNERS', [10, 10, 10, 10]),
    ]))

    elements.append(Paragraph("BILLED TO", styles['Section']))
    details = [
        [Paragraph("Name", styles['Muted']), Paragraph(username or '-', styles['Cell']),
         Paragraph("Method", styles['Muted']), Paragraph((payment_mode or 'N/A').title(), styles['Cell'])],
        [Paragraph("Email", styles['Muted']), Paragraph(email or '-', styles['Cell']),
         Paragraph("Status", styles['Muted']), badge],
        [Paragraph("Phone", styles['Muted']), Paragraph(str(phone or '-'), styles['Cell']),
         Paragraph("Purchased on", styles['Muted']), Paragraph(date_long, styles['Cell'])],
    ]
    details_table = Table(details, colWidths=[55, 200, 95, 130])
    details_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), ZEBRA),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 14), ('RIGHTPADDING', (0, 0), (-1, -1), 14),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, LINE),
        ('ROUNDEDCORNERS', [8, 8, 8, 8]),
    ]))
    elements.append(details_table)
    elements.append(Spacer(1, 22))

    elements.append(Paragraph("ITEMS", styles['Section']))
    data = [[Paragraph('<font color="#ffffff"><b>Course</b></font>', styles['Cell']),
             Paragraph('<font color="#ffffff"><b>Item</b></font>', styles['Cell']),
             Paragraph('<font color="#ffffff"><b>Amount</b></font>', styles['Cell'])]]
    for item in purchases:
        title = item.get("title", "")
        subtitle = item.get("subtitle", "")
        label = title if not subtitle else f"{title}<br/><font size=8 color='#992c25'>{subtitle}</font>"
        data.append([Paragraph(item.get("course_code", ""), styles['Cell']),
                     Paragraph(label, styles['Cell']),
                     Paragraph(f"<para align=right>{_money(item.get('price'))}</para>", styles['Cell'])])
    items_style = [
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 9), ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
        ('LEFTPADDING', (0, 0), (-1, -1), 12), ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('LINEBELOW', (0, 1), (-1, -1), 0.5, LINE),
        ('ROUNDEDCORNERS', [8, 8, 8, 8]),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            items_style.append(('BACKGROUND', (0, i), (-1, i), ZEBRA))
    items_table = Table(data, colWidths=[90, 280, 110])
    items_table.setStyle(TableStyle(items_style))
    elements.append(items_table)
    elements.append(Spacer(1, 20))

    discount_amount = round(original_price * discount / 100, 2)
    summary = [
        [Paragraph("Subtotal", styles['Muted']), Paragraph(f"<para align=right>{_money(original_price)}</para>", styles['Cell'])],
        [Paragraph(f"Discount ({discount}%)", styles['Muted']), Paragraph(f"<para align=right>- {_money(discount_amount)}</para>", styles['Cell'])],
        [Paragraph('<font color="#ffffff"><b>Total Paid</b></font>', styles['Cell']),
         Paragraph(f'<para align=right><font color="#ffffff"><b>{_money(final_amount)}</b></font></para>', styles['Cell'])],
    ]
    summary_table = Table(summary, colWidths=[290, 190], hAlign='RIGHT')
    summary_table.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 14), ('RIGHTPADDING', (0, 0), (-1, -1), 14),
        ('BACKGROUND', (0, -1), (-1, -1), PRIMARY),
        ('BACKGROUND', (0, 0), (-1, -2), PRIMARY_SOFT),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, LINE),
        ('ROUNDEDCORNERS', [8, 8, 8, 8]),
        ('FONTSIZE', (0, -1), (-1, -1), 12),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 30))

    footer = (
        '<para align=center spaceb=4><font size=9 color="#992c25">'
        'Thank you for your purchase! Questions about this receipt? '
        'Contact support@shyampracticepaper.com<br/>'
        f'&#169; {time.strftime("%Y")} ShyamPracticePaper &#8226; This is a computer-generated receipt.'
        '</font></para>'
    )
    elements.append(Paragraph(footer, styles['Normal']))

    def watermark(canvas_obj, doc_obj):
        if is_paid:
            canvas_obj.saveState()
            canvas_obj.translate(A4[0] / 2, A4[1] / 2)
            canvas_obj.rotate(38)
            canvas_obj.setFillColor(colors.Color(0.31, 0.275, 0.898, alpha=0.07))
            canvas_obj.setFont("Helvetica-Bold", 130)
            canvas_obj.drawCentredString(0, -30, "PAID")
            canvas_obj.restoreState()

    doc.build(elements, onFirstPage=watermark, onLaterPages=watermark)
    buffer.seek(0)
    return buffer

def generate_download_token(payment_id, expires_in=600):
    expiry = int(time.time()) + expires_in
    message = f"{payment_id}:{expiry}".encode()
    signature = hmac.new(DOWNLOAD_SECRET, message, hashlib.sha256).hexdigest()
    token = base64.urlsafe_b64encode(f"{expiry}:{signature}".encode()).decode()
    return token

def verify_download_token(payment_id, token):
    try:
        decoded = base64.urlsafe_b64decode(token).decode()
        expiry_str, received_sig = decoded.split(":")
        expiry = int(expiry_str)
        if time.time() > expiry:
            return False
        message = f"{payment_id}:{expiry}".encode()
        expected_sig = hmac.new(DOWNLOAD_SECRET, message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, received_sig)
    except Exception:
        return False
