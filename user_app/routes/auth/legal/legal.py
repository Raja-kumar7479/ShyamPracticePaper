import json
import logging
import os
from flask import abort, jsonify, render_template
from routes import users_bp

logger = logging.getLogger(__name__)

CONTENT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'legal_content.json')

_cache = {'mtime': None, 'data': None}

FALLBACK = {
    'meta': {
        'brand': 'ShyamPracticePaper',
        'support_email': 'support@shyampracticepaper.com',
        'last_updated': ''
    },
    'terms': {
        'title': 'Terms of Use',
        'subtitle': '',
        'intro': 'This document is being updated. Please contact support if you need a copy.',
        'sections': []
    },
    'privacy': {
        'title': 'Privacy Policy',
        'subtitle': '',
        'intro': 'This document is being updated. Please contact support if you need a copy.',
        'sections': []
    }
}


def load_legal_content():
    try:
        mtime = os.path.getmtime(CONTENT_PATH)
    except OSError:
        logger.error(f"Legal content file not found at {CONTENT_PATH}")
        return FALLBACK

    if _cache['data'] is not None and _cache['mtime'] == mtime:
        return _cache['data']

    try:
        with open(CONTENT_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Could not read legal content: {e}")
        return _cache['data'] or FALLBACK

    if not isinstance(data, dict) or 'terms' not in data or 'privacy' not in data:
        logger.error("Legal content JSON is missing the 'terms' or 'privacy' key.")
        return _cache['data'] or FALLBACK

    _cache['mtime'] = mtime
    _cache['data'] = data
    logger.info("Legal content reloaded from JSON.")
    return data


def _render(doc_key):
    content = load_legal_content()
    doc = content.get(doc_key)
    if not doc:
        abort(404)
    return render_template(
        'users/auth/legal.html',
        doc=doc,
        meta=content.get('meta', {}),
        active=doc_key
    )


@users_bp.route('/terms', methods=['GET'])
def terms_of_use():
    return _render('terms')


@users_bp.route('/privacy', methods=['GET'])
def privacy_policy():
    return _render('privacy')


@users_bp.route('/api/legal/<doc_key>', methods=['GET'])
def api_legal(doc_key):
    if doc_key not in ('terms', 'privacy'):
        return jsonify({'error': 'Unknown document.'}), 404
    content = load_legal_content()
    return jsonify({
        'meta': content.get('meta', {}),
        'doc': content.get(doc_key, {})
    })
