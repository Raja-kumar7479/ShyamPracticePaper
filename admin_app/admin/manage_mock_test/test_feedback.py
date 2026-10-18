import logging
import re
from flask import render_template, request, flash, redirect, url_for, session, jsonify, current_app
from flask_mail import Message
from admin.manage_mock_test.test_details_db import UserOperation
from extensions import admin_login_required, admin_owner_required, can_manage
from admin import admin_bp
import math

logger = logging.getLogger(__name__)

user_op = UserOperation()

ALLOWED_REPLY_TAGS = re.compile(r'</?(?:p|br|b|strong|i|em|u|ul|ol|li|h[1-6]|span|blockquote)(?:\s[^<>]*)?/?>', re.I)


def _sanitise_reply_html(html):
    cleaned = []
    pos = 0
    for m in re.finditer(r'<[^>]*>', html):
        cleaned.append(html[pos:m.start()])
        if ALLOWED_REPLY_TAGS.fullmatch(m.group(0)):
            tag = re.sub(r'\s(?:on\w+|style|class)\s*=\s*(?:"[^"]*"|\'[^\']*\'|\S+)', '', m.group(0), flags=re.I)
            cleaned.append(tag)
        pos = m.end()
    cleaned.append(html[pos:])
    return ''.join(cleaned)


def _wrap_reply_email(body_html):
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#faf7f5;font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:28px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       style="max-width:560px;background:#ffffff;border-radius:14px;overflow:hidden;box-shadow:0 8px 30px rgba(42,21,18,.10);">
<tr><td style="background:#833d17;padding:22px 30px;border-bottom:4px solid #f0ae06;">
<span style="color:#ffffff;font-size:19px;font-weight:700;">ShyamPracticePaper</span></td></tr>
<tr><td style="padding:30px;font-size:15px;line-height:1.7;color:#2a1512;">{body_html}</td></tr>
<tr><td style="padding:18px 30px 26px;border-top:1px solid #eee2da;">
<p style="margin:0;font-size:12px;color:#8a7a74;">This message was sent by the ShyamPracticePaper team in response to your test feedback.</p>
</td></tr></table></td></tr></table></body></html>"""

@admin_bp.route('/manage_feedback')
@admin_login_required
def manage_feedback():
    try:
        admin_email = session.get('admin_email', 'UnknownAdmin')
        logger.info(f"Admin [{admin_email}] accessed feedback management page.")
        return render_template("admin/manage_mock_test/manage_feedback.html")
    except Exception as e:
        logger.exception(f"Admin [{admin_email}] encountered an error while loading feedback page.")
        flash("An error occurred while loading the page.", "danger")
        return redirect(url_for('admin.admin_dashboard'))

def _rating_score(row):
    scale = {'excellent': 5, 'very good': 4, 'good': 4, 'average': 3, 'ok': 3,
             'standard': 3, 'poor': 2, 'bad': 1, 'very poor': 1,
             'tougher then standard': 3, 'tougher than standard': 3,
             'easier then standard': 3, 'easier than standard': 3}
    vals = []
    for key in ('feedback_software', 'feedback_content', 'feedback_speed'):
        v = str(row.get(key) or '').strip().lower()
        if v in scale:
            vals.append(scale[v])
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)


def _serialise_feedback(rows):
    for r in rows:
        for k, v in list(r.items()):
            if hasattr(v, 'strftime'):
                r[k] = v.strftime('%d %b %Y, %I:%M %p')
        r['rating'] = _rating_score(r)
        r['display_name'] = r.get('username') or (r.get('email') or '').split('@')[0]
    return rows


@admin_bp.route('/api/feedback/courses', methods=['GET'])
@admin_login_required
def feedback_courses():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    try:
        rows = user_op.get_feedback_courses()
        logger.info(f"FEEDBACK STEP 1: [{admin_email}] {len(rows)} course(s) with feedback")
        return jsonify(rows)
    except Exception:
        logger.exception(f"FEEDBACK STEP 1 FAILED: [{admin_email}]")
        return jsonify({'error': 'Could not load courses.'}), 500


@admin_bp.route('/api/feedback/contents', methods=['GET'])
@admin_login_required
def feedback_contents():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    course_code = (request.args.get('course_code') or '').strip()
    if not course_code:
        return jsonify({'error': 'Course code is required.'}), 400
    try:
        rows = user_op.get_feedback_contents(course_code)
        for r in rows:
            if hasattr(r.get('last_feedback'), 'strftime'):
                r['last_feedback'] = r['last_feedback'].strftime('%d %b %Y, %I:%M %p')
        logger.info(f"FEEDBACK STEP 1b: [{admin_email}] {len(rows)} content block(s) in {course_code}")
        return jsonify(rows)
    except Exception:
        logger.exception(f"FEEDBACK STEP 1b FAILED: [{admin_email}] course={course_code!r}")
        return jsonify({'error': 'Could not load the course content.'}), 500


@admin_bp.route('/api/feedback/tests', methods=['GET'])
@admin_login_required
def feedback_tests():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    course_code = (request.args.get('course_code') or '').strip()
    section_id = (request.args.get('section_id') or '').strip() or None
    if not course_code:
        return jsonify({'error': 'Course code is required.'}), 400
    try:
        rows = user_op.get_feedback_tests(course_code, section_id)
        for r in rows:
            if hasattr(r.get('last_feedback'), 'strftime'):
                r['last_feedback'] = r['last_feedback'].strftime('%d %b %Y, %I:%M %p')
        logger.info(f"FEEDBACK STEP 2: [{admin_email}] {len(rows)} test(s) in {course_code}")
        return jsonify(rows)
    except Exception:
        logger.exception(f"FEEDBACK STEP 2 FAILED: [{admin_email}] course={course_code!r}")
        return jsonify({'error': 'Could not load tests.'}), 500


@admin_bp.route('/api/feedback/entries', methods=['GET'])
@admin_login_required
def feedback_entries():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    test_key = (request.args.get('test_key') or '').strip()
    if not test_key:
        return jsonify({'error': 'Test key is required.'}), 400
    try:
        rows = _serialise_feedback(user_op.get_feedback_for_test(test_key))
        rated = [r['rating'] for r in rows if r.get('rating') is not None]
        summary = {
            'count': len(rows),
            'average': round(sum(rated) / len(rated), 1) if rated else None,
            'happy': sum(1 for r in rated if r >= 4),
            'unhappy': sum(1 for r in rated if r <= 2),
            'test_title': rows[0].get('subject_title') if rows else None,
        }
        logger.info(f"FEEDBACK STEP 3: [{admin_email}] test={test_key!r} -> {summary}")
        return jsonify({'feedbacks': rows, 'summary': summary})
    except Exception:
        logger.exception(f"FEEDBACK STEP 3 FAILED: [{admin_email}] test={test_key!r}")
        return jsonify({'error': 'Could not load feedback.'}), 500


@admin_bp.route('/api/feedback/reply', methods=['POST'])
@admin_login_required
def feedback_reply():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    data = request.get_json(silent=True) or {}
    to_email = (data.get('email') or '').strip().lower()
    subject = (data.get('subject') or '').strip()
    body_html = data.get('body') or ''

    logger.info(f"FEEDBACK REPLY 1: [{admin_email}] preparing reply to {to_email!r}")

    if not to_email or '@' not in to_email:
        logger.warning(f"FEEDBACK REPLY 2 BLOCKED: [{admin_email}] invalid email {to_email!r}")
        return jsonify({'success': False, 'message': 'A valid student email is required.'}), 400
    if not subject:
        return jsonify({'success': False, 'message': 'Please enter a subject line.'}), 400
    if not re.sub(r'<[^>]*>', '', body_html).strip():
        logger.warning(f"FEEDBACK REPLY 2 BLOCKED: [{admin_email}] empty message body")
        return jsonify({'success': False, 'message': 'The message body cannot be empty.'}), 400

    if not user_op.feedback_email_exists(to_email):
        logger.warning(f"FEEDBACK REPLY 3 BLOCKED: [{admin_email}] {to_email!r} has never submitted feedback")
        return jsonify({'success': False,
                        'message': 'This email has not submitted any feedback, so no reply can be sent to it.'}), 403

    safe_body = _sanitise_reply_html(body_html)
    try:
        from app import mail
        msg = Message(subject=subject, recipients=[to_email])
        msg.html = _wrap_reply_email(safe_body)
        mail.send(msg)
        logger.info(f"FEEDBACK REPLY 4: [{admin_email}] reply sent to {to_email!r} subject={subject!r}")
        return jsonify({'success': True, 'message': f'Thank-you message sent to {to_email}.'})
    except Exception as e:
        logger.exception(f"FEEDBACK REPLY FAILED: [{admin_email}] to {to_email!r}: {e}")
        return jsonify({'success': False,
                        'message': 'Could not send the email. Check the mail settings and try again.'}), 500


@admin_bp.route('/api/feedback/delete/<int:feedback_id>', methods=['DELETE'])
@admin_login_required
def feedback_delete(feedback_id):
    if not can_manage():
        return jsonify({'success': False, 'message': 'Permission Denied.'}), 403
    admin_email = session.get('admin_email', 'UnknownAdmin')
    try:
        user_op.delete_feedback_entry(feedback_id)
        logger.warning(f"FEEDBACK DELETE: [{admin_email}] removed feedback id={feedback_id}")
        return jsonify({'success': True, 'message': 'Feedback entry deleted.'})
    except Exception:
        logger.exception(f"FEEDBACK DELETE FAILED: [{admin_email}] id={feedback_id}")
        return jsonify({'success': False, 'message': 'Could not delete this entry.'}), 500


@admin_bp.route('/get_feedback_data', methods=['GET'])
@admin_login_required
def get_feedback_data():
    try:
        admin_email = session.get('admin_email', 'UnknownAdmin')
        page = request.args.get('page', 1, type=int)
        per_page = 50
        
        logger.info(f"Admin [{admin_email}] fetching feedback data for page {page}.")
        
        feedbacks, total = user_op.get_all_feedback_entries(page, per_page)
        
        total_pages = math.ceil(total / per_page)

        return jsonify({
            'feedbacks': feedbacks,
            'total_pages': total_pages,
            'current_page': page,
            'total_records': total
        })
    except Exception as e:
        logger.exception(f"Admin [{admin_email}] failed to fetch feedback data.")
        return jsonify({'error': 'Failed to fetch data'}), 500

@admin_bp.route('/truncate_feedback', methods=['POST'])
@admin_login_required
def truncate_feedback():
    if not can_manage():
        return jsonify({'success': False, 'message': 'Permission Denied.'}), 403
    admin_email = session.get('admin_email', 'UnknownAdmin')
    logger.info(f"Admin [{admin_email}] initiated feedback truncation.")
    try:
        if user_op.truncate_all_feedback():
            logger.info(f"Admin [{admin_email}] successfully truncated all feedback.")
            return jsonify({'success': True, 'message': 'All feedback data has been deleted.'})
        else:
            logger.warning(f"Admin [{admin_email}] failed to truncate feedback.")
            return jsonify({'success': False, 'message': 'Failed to delete feedback data.'}), 500
    except Exception as e:
        logger.exception(f"Admin [{admin_email}] encountered an exception during feedback truncation.")
        return jsonify({'success': False, 'message': 'An internal server error occurred.'}), 500
