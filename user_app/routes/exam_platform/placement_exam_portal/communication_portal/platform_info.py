import json
import logging
import os
from flask import abort, render_template
from routes import users_bp

logger = logging.getLogger(__name__)

INFO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'platform_info.json')

_cache = {'mtime': None, 'data': None}


def _load_info():
    try:
        mtime = os.path.getmtime(INFO_PATH)
        if _cache['data'] is None or _cache['mtime'] != mtime:
            with open(INFO_PATH, encoding='utf-8') as f:
                _cache['data'] = json.load(f)
            _cache['mtime'] = mtime
            logger.info("SAPM INFO: platform_info.json loaded")
        return _cache['data']
    except Exception:
        logger.exception("SAPM INFO: failed to load platform_info.json")
        return None


@users_bp.route('/sapm/about')
@users_bp.route('/sapm/about/<section>')
def sapm_about(section='about'):
    data = _load_info()
    if not data:
        abort(500)
    sections = data.get('sections', {})
    if section not in sections:
        logger.warning(f"SAPM INFO: unknown section {section!r} requested")
        abort(404)
    logger.info(f"SAPM INFO: serving section {section!r}")
    return render_template(
        'users/exam_platform/placement_exam_portal/communication_portal/platform_info.html',
        platform=data.get('platform', {}),
        sections=sections,
        active=section,
        content=sections[section]
    )
