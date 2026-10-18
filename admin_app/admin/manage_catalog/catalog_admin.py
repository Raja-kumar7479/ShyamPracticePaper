import logging
import re

from flask import jsonify, render_template, request, session

from admin import admin_bp, taxonomy
from admin.manage_catalog.catalog_db import (EDITORS, LEGACY_PORTALS,
                                             LIVE_PORTALS, CatalogDB)
from extensions import admin_login_required, can_manage

PLATFORMS = ('competitive', 'placement')
PLACEMENT_ONLY_PORTALS = ('coding', 'communication', 'tcs', 'coding_practice')

logger = logging.getLogger(__name__)
db = CatalogDB()

KEY_RE = re.compile(r'^[a-z][a-z0-9_]{1,39}$')
GROUP_RE = re.compile(r'^[A-Z0-9][A-Z0-9 +&.-]{0,39}$')
CODE_RE = re.compile(r'^[A-Z0-9]{1,20}$')


def _err(message, status=400):
    return jsonify({'success': False, 'message': message}), status


def _ok(**extra):
    taxonomy.refresh()
    payload = {'success': True}
    payload.update(extra)
    return jsonify(payload)


def _text(value, limit):
    text = (value or '')
    text = text if isinstance(text, str) else str(text)
    text = text.strip()
    if len(text) > limit:
        raise ValueError(f'Value is too long (limit {limit} characters).')
    return text


def _int(value, default, low, high, label):
    try:
        n = int(value) if value not in (None, '') else default
    except (TypeError, ValueError):
        raise ValueError(f'{label} must be a whole number.')
    if n < low or n > high:
        raise ValueError(f'{label} must be between {low} and {high}.')
    return n


def _owner_only():
    return can_manage()


@admin_bp.route('/manage-catalog')
@admin_login_required
def manage_catalog():
    return render_template(
        'admin/manage_catalog/catalog.html',
        groups=db.groups(),
        sections=db.sections(),
        group_sections=db.group_sections(),
        live_portals=LIVE_PORTALS,
        legacy_portals=sorted(LEGACY_PORTALS),
        editors=EDITORS,
        is_owner=_owner_only(),
    )


@admin_bp.route('/api/catalog/groups', methods=['POST'])
@admin_login_required
def api_add_group():
    if not _owner_only():
        return _err('Only an owner can change the catalog.', 403)
    data = request.get_json(silent=True) or {}
    name = (data.get('group_name') or '').strip().upper()
    if not GROUP_RE.match(name):
        return _err('Group name must be uppercase letters, digits, spaces or + & . - (max 40).')
    if db.group_exists(name):
        return _err(f"The group '{name}' already exists.", 409)
    try:
        label = _text(data.get('label'), 80) or name
        position = _int(data.get('position'), 0, 0, 999, 'Position')
    except ValueError as e:
        return _err(str(e))
    platform = (data.get('platform') or 'competitive').strip().lower()
    if platform not in PLATFORMS:
        return _err('Platform must be competitive or placement.')
    try:
        db.add_group(name, label, position, platform)
    except Exception:
        logger.exception('CATALOG: add group failed')
        return _err('Could not add the group.', 500)
    logger.info("CATALOG: [%s] added group %s", session.get('admin_email'), name)
    return _ok(group_name=name)


@admin_bp.route('/api/catalog/groups/<path:name>', methods=['PUT'])
@admin_login_required
def api_update_group(name):
    if not _owner_only():
        return _err('Only an owner can change the catalog.', 403)
    if not db.group_exists(name):
        return _err('Group not found.', 404)
    data = request.get_json(silent=True) or {}
    try:
        label = _text(data.get('label'), 80) or name
        position = _int(data.get('position'), 0, 0, 999, 'Position')
    except ValueError as e:
        return _err(str(e))
    platform = (data.get('platform') or '').strip().lower() or None
    if platform and platform not in PLATFORMS:
        return _err('Platform must be competitive or placement.')
    if platform and platform != 'placement':
        offending = [k for k in (db.group_sections().get(name) or []) if db.section_portal(k) in PLACEMENT_ONLY_PORTALS]
        if offending:
            return _err(f"'{name}' still offers placement-only sections ({', '.join(offending)}). Untick them in Course Catalog first.", 409)
    try:
        db.update_group(name, label, position, data.get('is_active', True), platform)
    except Exception:
        logger.exception('CATALOG: update group failed')
        return _err('Could not update the group.', 500)
    return _ok()


@admin_bp.route('/api/catalog/groups/<path:name>', methods=['DELETE'])
@admin_login_required
def api_delete_group(name):
    if not _owner_only():
        return _err('Only an owner can change the catalog.', 403)
    if not db.group_exists(name):
        return _err('Group not found.', 404)
    used = db.group_usage(name)
    if used:
        return _err(f"'{name}' is used by {used} course(s). Move or delete them first.", 409)
    codes = db.group_code_count(name)
    if codes:
        return _err(f"'{name}' still has {codes} code(s). Delete those codes first.", 409)
    try:
        db.delete_group(name)
    except Exception:
        logger.exception('CATALOG: delete group failed')
        return _err('Could not delete the group.', 500)
    logger.info("CATALOG: [%s] deleted group %s", session.get('admin_email'), name)
    return _ok()


@admin_bp.route('/api/catalog/codes', methods=['POST'])
@admin_login_required
def api_add_code():
    if not _owner_only():
        return _err('Only an owner can change the catalog.', 403)
    data = request.get_json(silent=True) or {}
    group_name = (data.get('group_name') or '').strip().upper()
    code = (data.get('code') or '').strip().upper()
    if not db.group_exists(group_name):
        return _err('Choose an existing group.')
    if not CODE_RE.match(code):
        return _err('Code must be 1-20 uppercase letters or digits, e.g. CS or PLA.')
    if db.code_exists(code):
        return _err(f"The code '{code}' already exists. Codes are unique across all groups.", 409)
    try:
        label = _text(data.get('label'), 80) or None
        position = _int(data.get('position'), 0, 0, 999, 'Position')
    except ValueError as e:
        return _err(str(e))
    try:
        db.add_code(group_name, code, label, position)
    except Exception:
        logger.exception('CATALOG: add code failed')
        return _err('Could not add the code.', 500)
    logger.info("CATALOG: [%s] added code %s under %s", session.get('admin_email'), code, group_name)
    return _ok()


@admin_bp.route('/api/catalog/codes/<group_name>/<code>', methods=['DELETE'])
@admin_login_required
def api_delete_code(group_name, code):
    if not _owner_only():
        return _err('Only an owner can change the catalog.', 403)
    if not db.code_pair_exists(group_name, code):
        return _err('Code not found. Refresh the page and try again.', 404)
    used = db.code_usage(code)
    if used:
        return _err(f"Code '{code}' is used by {used} course(s). Delete those courses first.", 409)
    try:
        db.delete_code(group_name, code)
    except Exception:
        logger.exception('CATALOG: delete code failed')
        return _err('Could not delete the code.', 500)
    return _ok()


def _read_section(data, require_key):
    key = (data.get('section_key') or '').strip().lower()
    if require_key and not KEY_RE.match(key):
        raise ValueError('Key must start with a letter and use only lowercase '
                         'letters, digits and underscores, e.g. interview_test.')
    portal = (data.get('portal') or '').strip()
    if portal and portal not in LIVE_PORTALS and portal not in LEGACY_PORTALS:
        raise ValueError('Choose one of the available portals, or leave it as "no portal".')
    editor = (data.get('editor') or '').strip()
    if editor and editor not in EDITORS:
        raise ValueError('Choose one of the available question editors.')
    available = bool(data.get('is_available'))
    if available and not portal:
        raise ValueError('A section with no portal cannot be marked available. '
                         'Pick a portal, or leave it as coming soon.')
    return {
        'key': key,
        'label': _text(data.get('label'), 80),
        'help_text': _text(data.get('help_text'), 255) or None,
        'portal': portal,
        'editor': editor,
        'available': available,
        'position': _int(data.get('position'), 0, 0, 999, 'Position'),
    }


@admin_bp.route('/api/catalog/sections', methods=['POST'])
@admin_login_required
def api_add_section():
    if not _owner_only():
        return _err('Only an owner can change the catalog.', 403)
    data = request.get_json(silent=True) or {}
    try:
        s = _read_section(data, require_key=True)
    except ValueError as e:
        return _err(str(e))
    if not s['label']:
        return _err('Label is required - it is what admins pick in the dropdown.')
    if db.section_exists(s['key']):
        return _err(f"The section '{s['key']}' already exists.", 409)
    try:
        db.add_section(s['key'], s['label'], s['help_text'], s['portal'],
                       s['editor'], s['available'], s['position'])
        for group_name in (data.get('groups') or []):
            if db.group_exists(group_name):
                db.link_section(group_name, s['key'], s['position'])
    except Exception:
        logger.exception('CATALOG: add section failed')
        return _err('Could not add the section.', 500)
    logger.info("CATALOG: [%s] added section %s", session.get('admin_email'), s['key'])
    return _ok(section_key=s['key'])


@admin_bp.route('/api/catalog/sections/<key>', methods=['PUT'])
@admin_login_required
def api_update_section(key):
    if not _owner_only():
        return _err('Only an owner can change the catalog.', 403)
    if not db.section_exists(key):
        return _err('Section not found.', 404)
    data = request.get_json(silent=True) or {}
    try:
        s = _read_section(data, require_key=False)
    except ValueError as e:
        return _err(str(e))
    if not s['label']:
        return _err('Label is required.')
    try:
        db.update_section(key, s['label'], s['help_text'], s['portal'],
                          s['editor'], s['available'], s['position'])
    except Exception:
        logger.exception('CATALOG: update section failed')
        return _err('Could not update the section.', 500)
    logger.info("CATALOG: [%s] updated section %s", session.get('admin_email'), key)
    return _ok()


@admin_bp.route('/api/catalog/sections/<key>', methods=['DELETE'])
@admin_login_required
def api_delete_section(key):
    if not _owner_only():
        return _err('Only an owner can change the catalog.', 403)
    if not db.section_exists(key):
        return _err('Section not found.', 404)
    used = db.section_usage(key)
    if used:
        return _err(f"'{key}' is used by {used} content item(s). "
                    f"Delete or move that content first.", 409)
    try:
        db.delete_section(key)
    except Exception:
        logger.exception('CATALOG: delete section failed')
        return _err('Could not delete the section.', 500)
    logger.info("CATALOG: [%s] deleted section %s", session.get('admin_email'), key)
    return _ok()


@admin_bp.route('/api/catalog/group-sections', methods=['POST'])
@admin_login_required
def api_toggle_group_section():
    if not _owner_only():
        return _err('Only an owner can change the catalog.', 403)
    data = request.get_json(silent=True) or {}
    group_name = (data.get('group_name') or '').strip()
    section_key = (data.get('section_key') or '').strip()
    enabled = bool(data.get('enabled'))

    if not db.group_exists(group_name):
        return _err('Group not found.', 404)
    if not db.section_exists(section_key):
        return _err('Section not found.', 404)

    if enabled and db.section_portal(section_key) in PLACEMENT_ONLY_PORTALS and db.group_platform(group_name) != 'placement':
        return _err(f"'{section_key}' belongs to the Placement Exam Portal only. Competitive groups like {group_name} "
                    f"(GATE, JEE, NEET) never get coding, communication or TCS content.", 409)
    try:
        if enabled:
            db.link_section(group_name, section_key)
        else:
            used = db.link_usage(group_name, section_key)
            if used:
                return _err(f"{used} content item(s) under {group_name} use this section. "
                            f"Move them first.", 409)
            db.unlink_section(group_name, section_key)
    except Exception:
        logger.exception('CATALOG: toggle group section failed')
        return _err('Could not save that change.', 500)
    return _ok()
