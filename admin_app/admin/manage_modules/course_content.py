import os
import re
import logging
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from flask import (
    flash, jsonify, redirect, render_template, request, url_for, session
)
from werkzeug.utils import secure_filename
from admin.manage_modules.content_db import UserOperation
from extensions import admin_login_required, can_manage
from admin import admin_bp, taxonomy

logger = logging.getLogger(__name__)

user_op = UserOperation()
from config import Config
from admin import shared_files
UPLOAD_FOLDER = Config.UPLOAD_BASE
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}

def _is_allowed_image(filename):
    return os.path.splitext(filename or '')[1].lower() in ALLOWED_IMAGE_EXTENSIONS

SYLLABUS_POSITIONS = ('above', 'below')


def _is_pdf(file_storage):
    if os.path.splitext(file_storage.filename or '')[1].lower() != '.pdf':
        return False
    head = file_storage.stream.read(1024)
    file_storage.stream.seek(0)
    return b'%PDF-' in head


def _clean_position(value):
    value = (value or '').strip().lower()
    return value if value in SYLLABUS_POSITIONS else 'below'


def _safe_segment(value, fallback):
    cleaned = re.sub(r'[^A-Za-z0-9_-]+', '_', str(value or '')).strip('_')
    return cleaned[:60] or fallback


def syllabus_folder(code, section_id):
    return os.path.join('syllabus', _safe_segment(code, 'course'), _safe_segment(section_id, 'item'))


def _store_upload(file_storage, subdir='', default_ext=''):
    original = file_storage.filename or ''
    base, ext = os.path.splitext(original)
    ext = ext.lower()
    if not re.fullmatch(r'\.[A-Za-z0-9]{1,8}', ext):
        ext = default_ext
    safe_base = secure_filename(base) or 'file'
    if safe_base.lower() == ext.lstrip('.'):
        safe_base = 'file'
    filename = f"{safe_base}{ext}"
    unique_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}_{filename}"
    target_dir = os.path.join(UPLOAD_FOLDER, subdir) if subdir else UPLOAD_FOLDER
    os.makedirs(target_dir, exist_ok=True)
    file_storage.save(os.path.join(target_dir, unique_name))
    shared_files.publish(os.path.join(target_dir, unique_name))
    stored = os.path.join('uploads', subdir, unique_name) if subdir else os.path.join('uploads', unique_name)
    return stored.replace('\\', '/')


def _upload_disk_path(stored_url):
    if not stored_url:
        return None
    relative = str(stored_url).replace('\\', '/').lstrip('/')
    if relative.startswith('static/'):
        relative = relative[len('static/'):]
    if relative.startswith('uploads/'):
        relative = relative[len('uploads/'):]
    if not relative:
        return None
    root = os.path.realpath(UPLOAD_FOLDER)
    candidate = os.path.realpath(os.path.join(root, relative))
    if candidate != root and not candidate.startswith(root + os.sep):
        logger.warning(f"UPLOAD PATH REFUSED: {stored_url!r} resolves outside the uploads folder")
        return None
    return candidate


def _prune_empty_dirs(path):
    root = os.path.realpath(UPLOAD_FOLDER)
    folder = os.path.dirname(path or '')
    while folder and folder != root and folder.startswith(root + os.sep):
        try:
            os.rmdir(folder)
        except OSError:
            return
        folder = os.path.dirname(folder)


def _remove_upload(image_url):
    if not image_url:
        return
    try:
        path = _upload_disk_path(image_url)
        if path:
            shared_files.remove(path)
        if path and os.path.isfile(path):
            os.remove(path)
            _prune_empty_dirs(path)
            logger.info(f"UPLOAD CLEANUP: removed {path}")
        else:
            logger.info(f"UPLOAD CLEANUP: nothing to remove for {image_url}")
    except OSError as e:
        logger.warning(f"UPLOAD CLEANUP failed for {image_url}: {e}")

@admin_bp.route('/manage_course_content', methods=['GET', 'POST'])
@admin_login_required
def manage_course_content():
    admin_email = session.get('admin_email', 'Unknown')
    admin_role = session.get('admin_role', 'default')

    try:
        if request.method == 'POST':
            code = request.form.get('code', '').strip()
            name = request.form.get('name', '').strip()
            stream = request.form.get('stream', '').strip()
            section = request.form.get('section', '').strip()
            title = request.form.get('title', '').strip()
            subtitle = request.form.get('subtitle', '').strip()
            details = clean_details(request.form.get('details', ''))
            label = request.form.get('label', '').strip()
            status = request.form.get('status', '').strip()
            max_tests, limit_error = _parse_test_limit(request.form.get('max_test_descriptions'))

            logger.info(f"ADD CONTENT 1: [{admin_email}] code={code!r} section={section!r} title={title!r} "
                        f"test_limit={max_tests}")
            if limit_error:
                logger.warning(f"ADD CONTENT 1t BLOCKED: [{admin_email}] {limit_error}")
                flash(limit_error, "admin_error")
                return redirect(url_for('admin.manage_course_content'))

            if not all([code, name, stream, section, title, label, status]):
                logger.warning(f"ADD CONTENT 2 BLOCKED: [{admin_email}] missing required fields")
                flash("All fields except Subtitle and Details are required.", "admin_error")
                return redirect(url_for('admin.manage_course_content'))

            if not taxonomy.section_meta(section):
                logger.warning(f"ADD CONTENT 3 BLOCKED: [{admin_email}] unknown section {section!r}")
                flash("That section does not exist. Please refresh the page and try again.", "admin_error")
                return redirect(url_for('admin.manage_course_content'))

            if not taxonomy.is_valid_section(name, section):
                allowed = ', '.join(taxonomy.label_for(s) for s in taxonomy.sections_for_group(name))
                logger.warning(f"ADD CONTENT 3b BLOCKED: [{admin_email}] section {section!r} not allowed under group {name!r}")
                flash(f"'{taxonomy.label_for(section)}' is not available for {name}. "
                      f"Allowed sections: {allowed or 'none'}.", "admin_error")
                return redirect(url_for('admin.manage_course_content'))

            if status == 'active' and not taxonomy.is_available(section):
                logger.warning(f"ADD CONTENT 3c BLOCKED: [{admin_email}] {section!r} has no portal yet")
                flash(f"The {taxonomy.label_for(section)} portal is not built yet, so this content "
                      f"cannot be set active. Save it as inactive until the portal is ready.",
                      "admin_error")
                return redirect(url_for('admin.manage_course_content'))

            if label not in ('Free', 'Paid') or status not in ('active', 'inactive'):
                logger.warning(f"ADD CONTENT 4 BLOCKED: [{admin_email}] bad label/status {label!r}/{status!r}")
                flash("Invalid label or status value.", "admin_error")
                return redirect(url_for('admin.manage_course_content'))

            price = 0.00
            discount = 0.00
            if label == 'Paid':
                try:
                    price = float(request.form.get('price', 0.00))
                    if price <= 0:
                        logger.warning(f"ADD CONTENT 5 BLOCKED: [{admin_email}] non-positive price {price}")
                        flash("Price must be a positive number for Paid content.", "admin_error")
                        return redirect(url_for('admin.manage_course_content'))
                except (ValueError, TypeError):
                    logger.warning(f"ADD CONTENT 5 BLOCKED: [{admin_email}] invalid price format")
                    flash("Invalid price format. Please enter a valid number.", "admin_error")
                    return redirect(url_for('admin.manage_course_content'))

                try:
                    discount = float(request.form.get('discount') or 0)
                except (ValueError, TypeError):
                    logger.warning(f"ADD CONTENT 5b BLOCKED: [{admin_email}] invalid discount format")
                    flash("Discount must be a number between 0 and 100.", "admin_error")
                    return redirect(url_for('admin.manage_course_content'))

                if discount < 0 or discount >= 100:
                    logger.warning(f"ADD CONTENT 5b BLOCKED: [{admin_email}] discount out of range: {discount}")
                    flash("Discount must be between 0 and 99.99 percent.", "admin_error")
                    return redirect(url_for('admin.manage_course_content'))

                payable, saved = effective_price(price, discount)
                logger.info(f"ADD CONTENT 5c: [{admin_email}] price={price} discount={discount}% -> payable={payable} (saves {saved})")

            syllabus_position = _clean_position(request.form.get('syllabus_position'))
            syllabus_label = (request.form.get('syllabus_label') or '').strip()[:120] or None
            syllabus_file = request.files.get('syllabus_file')
            has_syllabus = bool(syllabus_file and syllabus_file.filename)
            if has_syllabus and not _is_pdf(syllabus_file):
                logger.warning(f"ADD CONTENT 6s BLOCKED: [{admin_email}] rejected syllabus {syllabus_file.filename!r}")
                flash("The syllabus must be a PDF file.", "admin_error")
                return redirect(url_for('admin.manage_course_content'))

            image_url = ''
            file = request.files.get('image_file')
            if file and file.filename:
                if not _is_allowed_image(file.filename):
                    logger.warning(f"ADD CONTENT 6 BLOCKED: [{admin_email}] rejected file {file.filename!r}")
                    flash("Image must be a PNG, JPG, GIF or WEBP file.", "admin_error")
                    return redirect(url_for('admin.manage_course_content'))
                image_url = _store_upload(file) or ''
                logger.info(f"ADD CONTENT 7: [{admin_email}] image stored as {image_url!r}")

            if PREMIUM_MARKER in details and label.lower() != 'free':
                details = apply_premium_rule(details, label)
                logger.info(f"ADD CONTENT 8p: [{admin_email}] premium link dropped - {label} content cannot carry one")

            logger.info(f"ADD CONTENT 8: [{admin_email}] inserting content row")
            result = user_op.insert_content(code, name, stream, title, subtitle, price, details, label,
                                            status, image_url, section, None, discount,
                                            None, syllabus_position, syllabus_label, max_tests)

            if result and has_syllabus:
                saved = user_op.get_content_by_id(result)
                stored = _store_upload(syllabus_file, syllabus_folder(code, (saved or {}).get('section_id')), '.pdf')
                if stored and user_op.update_content_syllabus(result, stored):
                    logger.info(f"ADD CONTENT 7s: [{admin_email}] syllabus stored as {stored!r}")
                else:
                    logger.error(f"ADD CONTENT 7s FAILED: [{admin_email}] could not attach the syllabus to {result}")
                    flash("The content was saved but its syllabus could not be stored. Try uploading it again from Edit.",
                          "admin_error")

            if result:
                logger.info(f"ADMIN ACTION by {admin_email}: Inserted new content '{title}' for course '{code}'.")
                flash(f"Content '{title}' was added successfully!", "admin_success")
            else:
                logger.error(f"ADMIN ACTION by {admin_email}: Database error on content insertion for '{title}'.")
                flash("Failed to add content due to a database error. Please try again.", "admin_error")

            return redirect(url_for('admin.manage_course_content'))

        all_courses = user_op.get_all_courses()

        return render_template(
            "admin/manage_modules/course_content.html",
            all_courses=all_courses,
            group_sections={g: taxonomy.section_options(g) for g in taxonomy.groups()},
            admin_role=admin_role
        )

    except Exception as e:
        logger.exception(f"ADMIN ACTION by {admin_email}: Unhandled exception in 'manage_course_content'. Error: {e}")
        flash("A critical server error occurred. Please check the logs.", "admin_error")
        return redirect(url_for('admin.admin_dashboard'))


from html.parser import HTMLParser
from html import escape as _html_escape

_ALLOWED_TAGS = {
    'p', 'br', 'hr', 'div', 'span', 'strong', 'b', 'em', 'i', 'u', 's', 'sub', 'sup',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'blockquote', 'pre', 'code',
    'a', 'img', 'table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th',
}
_VOID_TAGS = {'br', 'hr', 'img'}
_ALLOWED_ATTRS = {
    'a': {'href', 'target', 'rel', 'title', 'class'},
    'img': {'src', 'alt', 'width', 'height', 'class', 'style'},
    'td': {'colspan', 'rowspan', 'class', 'style', 'data-row'},
    'th': {'colspan', 'rowspan', 'class', 'style', 'data-row'},
    'tr': {'class', 'style', 'data-row'},
}
_GLOBAL_ATTRS = {'class', 'style'}
_ALLOWED_STYLES = {
    'color', 'background-color', 'text-align', 'font-size', 'font-weight',
    'font-style', 'text-decoration', 'width', 'height', 'margin', 'padding',
}
_SAFE_LINK_SCHEMES = ('http://', 'https://', 'mailto:', 'tel:', '/', '#')
_SAFE_IMG_SCHEMES = ('http://', 'https://', '/', 'data:image/')


def _clean_style(value):
    kept = []
    for rule in (value or '').split(';'):
        if ':' not in rule:
            continue
        prop, _, val = rule.partition(':')
        prop, val = prop.strip().lower(), val.strip()
        if prop in _ALLOWED_STYLES and 'expression' not in val.lower() and 'javascript:' not in val.lower():
            kept.append(f'{prop}: {val}')
    return '; '.join(kept)


class _DescriptionCleaner(HTMLParser):
    _DROP_CONTENT = {'script', 'style', 'iframe', 'object', 'embed', 'noscript', 'template'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self._open = []
        self._muted = 0

    def _attrs(self, tag, attrs):
        allowed = _ALLOWED_ATTRS.get(tag, set()) | _GLOBAL_ATTRS
        parts = []
        for name, value in attrs:
            name = (name or '').lower()
            value = value or ''
            if name.startswith('on') or name not in allowed:
                continue
            if name == 'href' and not value.lower().startswith(_SAFE_LINK_SCHEMES):
                continue
            if name == 'src' and not value.lower().startswith(_SAFE_IMG_SCHEMES):
                continue
            if name == 'style':
                value = _clean_style(value)
                if not value:
                    continue
            parts.append(f'{name}="{_html_escape(value, quote=True)}"')
        if tag == 'a':
            parts.append('rel="noopener noreferrer"') if not any(p.startswith('rel=') for p in parts) else None
        return (' ' + ' '.join(parts)) if parts else ''

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self._DROP_CONTENT:
            self._muted += 1
            return
        if self._muted or tag not in _ALLOWED_TAGS:
            return
        self.out.append(f'<{tag}{self._attrs(tag, attrs)}' + ('>' if tag not in _VOID_TAGS else ' />'))
        if tag not in _VOID_TAGS:
            self._open.append(tag)

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if not self._muted and tag in _ALLOWED_TAGS:
            self.out.append(f'<{tag}{self._attrs(tag, attrs)} />')

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self._DROP_CONTENT:
            self._muted = max(0, self._muted - 1)
            return
        if self._muted or tag in _VOID_TAGS or tag not in _ALLOWED_TAGS or tag not in self._open:
            return
        while self._open:
            open_tag = self._open.pop()
            self.out.append(f'</{open_tag}>')
            if open_tag == tag:
                break

    def handle_data(self, data):
        if self._muted:
            return
        self.out.append(_html_escape(data, quote=False))

    def result(self):
        while self._open:
            self.out.append(f'</{self._open.pop()}>')
        return ''.join(self.out)


PREMIUM_MARKER = '[[PREMIUM]]'


def apply_premium_rule(details, label):
    if (label or '').strip().lower() == 'free':
        return details or ''
    return (details or '').replace(PREMIUM_MARKER, '')


def clean_details(html):
    if not html:
        return ''
    cleaner = _DescriptionCleaner()
    cleaner.feed(html)
    cleaner.close()
    out = cleaner.result().strip()
    return '' if out in ('<p><br /></p>', '<p><br></p>', '<p></p>') else out


def _parse_test_limit(value):
    raw = ('' if value is None else str(value)).strip()
    if not raw:
        return None, None
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        return None, "The test description limit must be a whole number."
    if limit < 1:
        return None, "The test description limit must be at least 1 (leave it blank for no limit)."
    return limit, None


def effective_price(price, discount):
    try:
        price = float(price or 0)
        discount = float(discount or 0)
    except (TypeError, ValueError):
        return float(price or 0), 0.0
    if discount <= 0 or discount >= 100:
        return round(price, 2), 0.0
    saved = round(price * discount / 100.0, 2)
    return round(price - saved, 2), saved

def _serialise_content(rows):
    for row in rows:
        if isinstance(row.get('price'), Decimal):
            row['price'] = float(row['price'])
        if isinstance(row.get('discount'), Decimal):
            row['discount'] = float(row['discount'])
        row['discount'] = float(row.get('discount') or 0)

        final, saved = effective_price(row.get('price'), row['discount'])
        row['final_price'] = final
        row['amount_saved'] = saved

        if row.get('created_at'):
            row['created_at'] = row['created_at'].strftime('%d %b %Y, %I:%M %p')
    return rows

@admin_bp.route('/get_all_content', methods=['GET'])
@admin_login_required
def get_all_content():
    try:
        contents = _serialise_content(user_op.get_all_content())
        return jsonify(contents)
    except Exception as e:
        logger.exception(f"API CALL Failed to fetch all course content. Error: {e}")
        return jsonify({"error": "Could not retrieve content due to a server error."}), 500

@admin_bp.route('/get_content_for_course/<string:course_code>', methods=['GET'])
@admin_login_required
def get_content_for_course(course_code):
    try:
        logger.info(f"FETCH CONTENT: course_code={course_code!r}")
        contents = _serialise_content(user_op.get_courses_by_code(course_code))
        logger.info(f"FETCH CONTENT: returned {len(contents)} row(s) for {course_code!r}")
        return jsonify(contents)
    except Exception as e:
        logger.exception(f"API CALL Failed to fetch content for '{course_code}'. Error: {e}")
        return jsonify({"error": "Could not retrieve content due to a server error."}), 500

@admin_bp.route('/delete_content/<int:content_id>', methods=['POST'])
@admin_login_required
def delete_content(content_id):
    admin_email = session.get('admin_email')

    if not can_manage():
        return jsonify({"success": False, "message": "Permission Denied."}), 403

        
    try:
        result = user_op.delete_content(content_id)
        if result == 'has_attempts':
            return jsonify({
                "success": False,
                "message": "Students have already taken tests under this content, so deleting it "
                           "would erase their attempts and results. Set it to 'inactive' instead: "
                           "it disappears from the store and dashboards, while everyone who already "
                           "used it keeps their history."
            }), 409
        if result == 'has_purchases':
            return jsonify({
                "success": False,
                "message": "This item has been paid for by students, so it cannot be deleted "
                           "— they would lose access to what they bought. Set it to "
                           "'inactive' instead: it disappears from the store and dashboards for "
                           "new users, while everyone who already paid keeps full access."
            }), 409
        if result:
            logger.info(f"ADMIN ACTION by {admin_email}: Successfully deleted content ID {content_id}.")
            return jsonify({"success": True, "message": "Content has been deleted."})
        else:
            return jsonify({"success": False, "message": "Deletion failed. Content not found."}), 404
    except Exception as e:
        logger.exception(f"Server error during deletion of content ID {content_id}. Error: {e}")
        return jsonify({"success": False, "message": "A server error occurred."}), 500

@admin_bp.route('/update_content_field/<int:content_id>', methods=['POST'])
@admin_login_required
def update_content_field(content_id):
    admin_email = session.get('admin_email')

    if not can_manage():
        return jsonify({"success": False, "message": "Permission Denied."}), 403
    
    if not request.is_json:
        return jsonify({"success": False, "message": "Invalid request."}), 400

    data = request.get_json()
    field, value = data.get('field'), data.get('value')
    

    ALLOWED_FIELDS = ['name', 'stream', 'title', 'subtitle', 'price', 'discount', 'details',
                      'label', 'status', 'syllabus_position', 'syllabus_label',
                      'max_test_descriptions']
    if field not in ALLOWED_FIELDS:
        logger.warning(f"UPDATE FIELD BLOCKED: [{admin_email}] tried to edit '{field}' on id={content_id}")
        return jsonify({"success": False, "message": f"The '{field}' field cannot be updated directly."}), 400

    try:
        logger.info(f"UPDATE FIELD 1: [{admin_email}] id={content_id} field={field!r}")

        current_content = user_op.get_content_by_id(content_id)
        if not current_content:
            logger.warning(f"UPDATE FIELD 2 BLOCKED: [{admin_email}] content id={content_id} not found")
            return jsonify({"success": False, "message": "Content not found."}), 404

        content_dict = dict(current_content)

        if field == 'details':
            value = apply_premium_rule(clean_details(value), current_content.get('label'))
        if field == 'max_test_descriptions':
            value, limit_error = _parse_test_limit(value)
            if limit_error:
                return jsonify({"success": False, "message": limit_error}), 400

        NOT_NULL_FIELDS = ('title', 'label', 'status')
        if field in NOT_NULL_FIELDS and not value:
            logger.warning(f"UPDATE FIELD 3 BLOCKED: [{admin_email}] '{field}' cannot be empty")
            return jsonify({"success": False, "message": f"'{field}' cannot be empty."}), 400

        if field == 'label' and value not in ('Free', 'Paid'):
            return jsonify({"success": False, "message": "Label must be Free or Paid."}), 400
        if field == 'status' and value not in ('active', 'inactive'):
            return jsonify({"success": False, "message": "Status must be active or inactive."}), 400

        if field == 'status' and value == 'active' \
                and not taxonomy.is_available(current_content.get('section')):
            label_txt = taxonomy.label_for(current_content.get('section'))
            logger.warning(f"UPDATE FIELD BLOCKED: [{admin_email}] tried to activate "
                           f"portal-less section {current_content.get('section')!r} on id={content_id}")
            return jsonify({"success": False,
                            "message": f"The {label_txt} portal is not built yet, so this content "
                                       f"cannot be set active."}), 400

        content_dict[field] = value if value not in ('', None) else None

        if field == 'label':
            if value == 'Free':
                content_dict['price'] = 0.00
                content_dict['discount'] = 0.00
                logger.info(f"UPDATE FIELD 4: [{admin_email}] id={content_id} switched to Free; price and discount cleared")
            else:
                raw_price = data.get('price')
                try:
                    new_price = float(raw_price) if raw_price not in (None, '') else float(content_dict.get('price') or 0)
                except (TypeError, ValueError):
                    return jsonify({"success": False, "message": "Price must be a valid number."}), 400
                if new_price <= 0:
                    logger.warning(f"UPDATE FIELD 4 BLOCKED: [{admin_email}] id={content_id} Paid with price {new_price}")
                    return jsonify({"success": False,
                                    "message": "Set a price greater than 0 to make this content Paid."}), 400
                content_dict['price'] = new_price
                raw_discount = data.get('discount')
                if raw_discount not in (None, ''):
                    try:
                        new_discount = float(raw_discount)
                    except (TypeError, ValueError):
                        return jsonify({"success": False, "message": "Discount must be a valid number."}), 400
                    if not 0 <= new_discount < 100:
                        return jsonify({"success": False, "message": "Discount must be between 0 and 99.99 percent."}), 400
                    content_dict['discount'] = new_discount

        if field == 'price':
            try:
                content_dict['price'] = float(value) if value else 0.00
            except (TypeError, ValueError):
                logger.warning(f"UPDATE FIELD 4 BLOCKED: [{admin_email}] bad price {value!r}")
                return jsonify({"success": False, "message": "Price must be a valid number."}), 400
            if content_dict['price'] < 0:
                return jsonify({"success": False, "message": "Price cannot be negative."}), 400
            if content_dict['price'] <= 0 and content_dict.get('label') == 'Paid':
                logger.warning(f"UPDATE FIELD 4 BLOCKED: [{admin_email}] id={content_id} zero price on Paid content")
                return jsonify({"success": False,
                                "message": "Paid content needs a price greater than 0. Switch the label to Free instead."}), 400

        if field == 'discount':
            try:
                content_dict['discount'] = float(value) if value else 0.00
            except (TypeError, ValueError):
                logger.warning(f"UPDATE FIELD 4b BLOCKED: [{admin_email}] bad discount {value!r}")
                return jsonify({"success": False, "message": "Discount must be a valid number."}), 400
            if not 0 <= content_dict['discount'] < 100:
                logger.warning(f"UPDATE FIELD 4b BLOCKED: [{admin_email}] discount out of range {value!r}")
                return jsonify({"success": False, "message": "Discount must be between 0 and 99.99 percent."}), 400

        if field == 'syllabus_position':
            content_dict['syllabus_position'] = _clean_position(value)

        if PREMIUM_MARKER in (content_dict.get('details') or '') \
                and (content_dict.get('label') or '').lower() != 'free':
            content_dict['details'] = apply_premium_rule(content_dict['details'], content_dict.get('label'))
            logger.info(f"UPDATE FIELD 5p: [{admin_email}] premium link dropped from id={content_id} - "
                        f"{content_dict.get('label')} content cannot carry one")

        logger.info(f"UPDATE FIELD 6: [{admin_email}] writing id={content_id}")
        success = user_op.update_content(
            content_id, content_dict['name'], content_dict['stream'],
            content_dict['title'], content_dict['subtitle'], content_dict['price'],
            content_dict['details'], content_dict['label'], content_dict['status'],
            content_dict['image_url'],
            None, content_dict.get('discount') or 0,
            content_dict.get('syllabus_url'), content_dict.get('syllabus_position'),
            content_dict.get('syllabus_label'),
            max_test_descriptions=content_dict.get('max_test_descriptions'))

        if not success:
            logger.error(f"UPDATE FIELD FAILED: [{admin_email}] no row updated for id={content_id}")
            return jsonify({"success": False, "message": "Database update failed."}), 500

        updated = user_op.get_content_by_id(content_id)
        logger.info(f"UPDATE FIELD 7: [{admin_email}] '{field}' saved for content id={content_id}")

        updated_value = updated.get(field)
        if isinstance(updated_value, Decimal):
            updated_value = float(updated_value)

        new_price = float(updated['price'] or 0)
        new_discount = float(updated.get('discount') or 0)
        payable, saved = effective_price(new_price, new_discount)

        return jsonify({
            "success": True,
            "message": "Update successful.",
            "updated_field_value": updated_value,
            "new_price": new_price,
            "new_discount": new_discount,
            "new_final_price": payable,
            "new_amount_saved": saved,
        })

    except Exception as e:
        logger.exception(f"Exception while updating content field for ID {content_id}. Error: {e}")
        return jsonify({"success": False, "message": "Server error during update."}), 500

@admin_bp.route('/update_content_image/<int:content_id>', methods=['POST'])
@admin_login_required
def update_content_image(content_id):
    admin_email = session.get('admin_email', 'Unknown')

    if not can_manage():
        logger.warning(f"IMAGE UPDATE BLOCKED: [{admin_email}] attempt on id={content_id}")
        return jsonify({"success": False, "message": "Permission Denied."}), 403

    try:
        content = user_op.get_content_by_id(content_id)
        if not content: return jsonify({"success": False, "message": "Content not found."}), 404

        file = request.files.get('image_file')
        if not file or not file.filename: return jsonify({"success": False, "message": "No file uploaded."}), 400

        if not _is_allowed_image(file.filename):
            logger.warning(f"IMAGE UPDATE BLOCKED: [{admin_email}] rejected file {file.filename!r}")
            return jsonify({"success": False, "message": "Image must be a PNG, JPG, GIF or WEBP file."}), 400

        _remove_upload(content.get('image_url'))

        new_url = _store_upload(file)
        if not new_url:
            return jsonify({"success": False, "message": "Could not store the uploaded file."}), 400
        logger.info(f"IMAGE UPDATE: [{admin_email}] content id={content_id} new file {new_url!r}")

        if user_op.update_content_image(content_id, new_url):
            logger.info(f"ADMIN ACTION by {admin_email}: Updated image for content ID {content_id}.")
            return jsonify({"success": True, "message": "Image updated successfully.", "new_image_url": url_for('static', filename=new_url)})
        return jsonify({"success": False, "message": "Failed to update image link in database."}), 500

    except Exception as e:
        logger.exception(f"ADMIN ACTION by {admin_email}: Exception during image update for content ID {content_id}. Error: {e}")
        return jsonify({"success": False, "message": "Internal server error during image update."}), 500

@admin_bp.route('/delete_content_image/<int:content_id>', methods=['POST'])
@admin_login_required
def delete_content_image(content_id):
    admin_email = session.get('admin_email', 'Unknown')

    if not can_manage():
        logger.warning(f"IMAGE DELETE BLOCKED: [{admin_email}] attempt on id={content_id}")
        return jsonify({"success": False, "message": "Permission Denied."}), 403

    try:
        content = user_op.get_content_by_id(content_id)
        if not content or not content.get('image_url'):
            return jsonify({"success": False, "message": "Content or image not found."}), 404

        _remove_upload(content['image_url'])

        if user_op.update_content_image(content_id, ''):
            logger.info(f"ADMIN ACTION by {admin_email}: Deleted image for content ID {content_id}.")
            return jsonify({"success": True, "message": "Image deleted."})
        return jsonify({"success": False, "message": "Failed to update database after image deletion."}), 500
    except Exception as e:
        logger.exception(f"ADMIN ACTION by {admin_email}: Error deleting image for content ID {content_id}. Error: {e}")
        return jsonify({"success": False, "message": "Internal error during image deletion."}), 500

@admin_bp.route('/update_content/<int:content_id>', methods=['POST'])
@admin_login_required
def update_content(content_id):
    admin_email = session.get('admin_email', 'Unknown')

    if not can_manage():
        logger.warning(f"EDIT CONTENT BLOCKED: [{admin_email}] attempt on id={content_id}")
        return jsonify({"success": False, "message": "Permission Denied."}), 403

    data = request.get_json(silent=True) or {}
    logger.info("EDIT CONTENT 1: [%s] id=%s fields=%s", admin_email, content_id, sorted(data.keys()))
    try:
        current = user_op.get_content_by_id(content_id)
        if not current:
            logger.warning("EDIT CONTENT 2 BLOCKED: [%s] id=%s not found", admin_email, content_id)
            return jsonify({"success": False, "message": "Content not found."}), 404

        title = (data.get('title') or '').strip()
        if not title:
            return jsonify({"success": False, "message": "Title is required."}), 400
        subtitle = (data.get('subtitle') or '').strip()
        stream = (data.get('stream') or '').strip()
        label = (data.get('label') or '').strip()
        status = (data.get('status') or '').strip()
        details = clean_details(data.get('details') or '')

        if label not in ('Free', 'Paid'):
            return jsonify({"success": False, "message": "Label must be Free or Paid."}), 400
        if status not in ('active', 'inactive'):
            return jsonify({"success": False, "message": "Status must be active or inactive."}), 400
        if PREMIUM_MARKER in details and label != 'Free':
            details = apply_premium_rule(details, label)
            logger.info("EDIT CONTENT 2p: [%s] premium link dropped from id=%s - %s content cannot carry one",
                        admin_email, content_id, label)

        if status == 'active' and not taxonomy.is_available(current.get('section')):
            return jsonify({"success": False,
                            "message": f"The {taxonomy.label_for(current.get('section'))} portal is not built "
                                       f"yet, so this content cannot be set active."}), 400

        price, discount = 0.00, 0.00
        if label == 'Paid':
            try:
                price = float(data.get('price') or 0)
            except (TypeError, ValueError):
                return jsonify({"success": False, "message": "Price must be a valid number."}), 400
            if price <= 0:
                return jsonify({"success": False,
                                "message": "Paid content needs a price greater than 0. "
                                           "Switch the label to Free instead."}), 400
            try:
                discount = float(data.get('discount') or 0)
            except (TypeError, ValueError):
                return jsonify({"success": False, "message": "Discount must be a valid number."}), 400
            if not 0 <= discount < 100:
                return jsonify({"success": False, "message": "Discount must be between 0 and 99.99 percent."}), 400

        syllabus_position = _clean_position(data.get('syllabus_position'))
        syllabus_label = (data.get('syllabus_label') or '').strip()[:120] or None
        syllabus_url = current.get('syllabus_url')
        if data.get('remove_syllabus'):
            _remove_upload(syllabus_url)
            syllabus_url = None

        max_tests, limit_error = _parse_test_limit(data.get('max_test_descriptions'))
        if limit_error:
            return jsonify({"success": False, "message": limit_error}), 400
        if max_tests is not None and max_tests < int(current.get('description_count') or 0):
            existing = int(current.get('description_count') or 0)
            return jsonify({"success": False,
                            "message": f"This content already has {existing} test description(s); "
                                       f"the limit cannot be lower than that."}), 400

        logger.info("EDIT CONTENT 3: [%s] id=%s writing label=%s status=%s price=%s discount=%s "
                    "syllabus=%s (%s) test_limit=%s", admin_email, content_id, label, status, price,
                    discount, 'yes' if syllabus_url else 'no', syllabus_position, max_tests)

        ok = user_op.update_content(
            content_id, current.get('name'), stream, title, subtitle, price, details,
            label, status, current.get('image_url'), None, discount,
            syllabus_url, syllabus_position, syllabus_label, max_tests,
        )
        if not ok:
            logger.error("EDIT CONTENT FAILED: [%s] the write did not go through for id=%s",
                         admin_email, content_id)
            return jsonify({"success": False,
                            "message": "The content could not be saved. Please reload the page and try "
                                       "again; if it keeps happening, the server log has the reason."}), 500

        updated = _serialise_content([dict(user_op.get_content_by_id(content_id))])[0]
        logger.info(f"ADMIN ACTION by {admin_email}: Updated content id={content_id} ('{title}').")
        return jsonify({"success": True, "message": "Content updated.", "content": updated})

    except Exception as e:
        logger.exception("EDIT CONTENT ERROR: [%s] id=%s crashed while saving: %s", admin_email, content_id, e)
        return jsonify({"success": False, "message": "Server error during update."}), 500


@admin_bp.route('/upload_editor_image', methods=['POST'])
@admin_login_required
def upload_editor_image():
    admin_email = session.get('admin_email', 'Unknown')

    if not can_manage():
        return jsonify({"success": False, "message": "Permission Denied."}), 403

    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({"success": False, "message": "No file uploaded."}), 400
    if not _is_allowed_image(file.filename):
        return jsonify({"success": False, "message": "Image must be a PNG, JPG, GIF or WEBP file."}), 400

    stored = _store_upload(file)
    if not stored:
        return jsonify({"success": False, "message": "Could not store the uploaded file."}), 400

    logger.info(f"EDITOR IMAGE: [{admin_email}] stored {stored!r}")
    return jsonify({"success": True, "url": url_for('static', filename=stored)})


@admin_bp.route('/update_content_syllabus/<int:content_id>', methods=['POST'])
@admin_login_required
def update_content_syllabus(content_id):
    admin_email = session.get('admin_email', 'Unknown')

    if not can_manage():
        return jsonify({"success": False, "message": "Permission Denied."}), 403

    content = user_op.get_content_by_id(content_id)
    if not content:
        return jsonify({"success": False, "message": "Content not found."}), 404

    file = request.files.get('syllabus_file')
    if not file or not file.filename:
        logger.warning("SYLLABUS 1 BLOCKED: [%s] no file in the request for id=%s", admin_email, content_id)
        return jsonify({"success": False, "message": "No file uploaded."}), 400

    logger.info("SYLLABUS 1: [%s] id=%s receiving %r (%s)", admin_email, content_id, file.filename,
                file.mimetype or 'no mimetype')
    if not _is_pdf(file):
        logger.warning("SYLLABUS 2 BLOCKED: [%s] %r on id=%s is not a PDF (extension or signature)",
                       admin_email, file.filename, content_id)
        return jsonify({"success": False, "message": "The syllabus must be a PDF file."}), 400

    try:
        stored = _store_upload(file, syllabus_folder(content.get('code'), content.get('section_id')), '.pdf')
    except OSError as e:
        logger.exception("SYLLABUS 3 FAILED: [%s] could not write %r for id=%s: %s",
                         admin_email, file.filename, content_id, e)
        return jsonify({"success": False, "message": "The file could not be written to disk."}), 500
    if not stored:
        logger.error("SYLLABUS 3 FAILED: [%s] nothing stored for %r on id=%s",
                     admin_email, file.filename, content_id)
        return jsonify({"success": False, "message": "Could not store the uploaded file."}), 400

    logger.info("SYLLABUS 3: [%s] id=%s stored at %s", admin_email, content_id, stored)
    _remove_upload(content.get('syllabus_url'))
    if not user_op.update_content_syllabus(content_id, stored):
        _remove_upload(stored)
        logger.error("SYLLABUS 4 FAILED: [%s] id=%s could not be linked to %s", admin_email, content_id, stored)
        return jsonify({"success": False,
                        "message": "The file uploaded but could not be linked to this content. "
                                   "The server log has the reason."}), 500

    logger.info(f"SYLLABUS: [{admin_email}] content id={content_id} now has {stored!r}")
    return jsonify({"success": True, "message": "Syllabus uploaded.",
                    "syllabus_url": url_for('static', filename=stored)})
