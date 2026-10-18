import logging
from functools import wraps

from flask import flash, jsonify, redirect, request, url_for

from routes.exam_platform.subscription_access import has_platform_subscription, premium_url
from routes.exam_platform.competitive_exam_platform.databases.question_handler_db import ContentOperation

logger = logging.getLogger(__name__)
_content_op = ContentOperation()


def _test_owner(test_key):
    return _content_op.fetch_one(
        "SELECT td.test_id, COALESCE(td.access_label, 'inherit') AS access_label, "
        "       cc.code AS course "
        "FROM test_description td LEFT JOIN course_content cc ON cc.section_id = td.test_id "
        "WHERE td.test_key = %s",
        (test_key,),
    )


def test_access_denied(email, section_id, test_key, course_code=None, unique_code=None):
    owner = _test_owner(test_key)
    if not owner:
        return None

    owner_section = owner.get('test_id')
    if section_id and owner_section and str(section_id) != str(owner_section):
        logger.warning("TEST ACCESS: [%s] URL section %s does not own test %s (owner %s); "
                       "using the owner", email, section_id, test_key, owner_section)

    label = _content_op.get_section_label(owner_section)
    if label == 'Paid':
        if _content_op.is_section_purchased(email, owner_section):
            return None
        logger.warning("TEST ACCESS BLOCKED: [%s] paid section %s not purchased (test %s)",
                       email, owner_section, test_key)
        if course_code and unique_code:
            shop = url_for('users.course_shop', course_code=course_code, unique_code=unique_code)
        else:
            shop = url_for('users.index')
        return {'reason': 'purchase',
                'message': 'This is a paid section. Purchase it to open its tests.',
                'redirect_url': shop}

    if owner.get('access_label') == 'paid' and not has_platform_subscription(email, owner.get('course') or course_code):
        logger.warning("TEST ACCESS BLOCKED: [%s] premium test %s without subscription", email, test_key)
        return {'reason': 'subscription',
                'message': 'This is a premium test. Subscribe to unlock all tests.',
                'redirect_url': premium_url(course_code, unique_code, owner_section)}
    return None


def _wants_json():
    return (request.is_json
            or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.path.startswith('/api/')
            or request.path.startswith('/fetch-questions/'))


def test_access_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        from routes.exam_platform.competitive_exam_platform.utils.utils_test_dashboard import get_user_session
        email, _, _ = get_user_session()
        denied = test_access_denied(email, kwargs.get('section_id'), kwargs.get('test_key'),
                                    kwargs.get('course_code'), kwargs.get('unique_code'))
        if not denied:
            return f(*args, **kwargs)
        if request.method == 'POST' or _wants_json():
            return jsonify({'success': False, 'error': denied['message'],
                            'message': denied['message'], 'redirect': denied['redirect_url']}), 403
        flash(denied['message'], 'warning')
        return redirect(denied['redirect_url'])
    return wrapped
