import logging

logger = logging.getLogger(__name__)

PREMIUM_ENDPOINT = 'practice_coding.premium'


def has_platform_subscription(email, course_code=None):
    if not email:
        return False
    try:
        from routes.exam_platform.placement_exam_portal.practice_coding.models import active_subscription
        return active_subscription(email, course_code) is not None
    except Exception:
        logger.exception("SUBSCRIPTION: platform subscription check failed")
        return False


def is_test_locked(access_label, subscribed):
    if subscribed:
        return False
    return (access_label or 'inherit') == 'paid'


def premium_url(course_code=None, unique_code=None, section_id=None):
    from flask import session, url_for
    course_code = course_code or session.get('pcp_course_code')
    unique_code = unique_code or session.get('pcp_unique_code')
    if course_code and unique_code:
        kwargs = {'course_code': course_code, 'unique_code': unique_code}
        if section_id:
            kwargs['from'] = section_id
        return url_for('users.premium_details_page', **kwargs)
    return url_for(PREMIUM_ENDPOINT)


def annotate_tests(tests, email, label_key='access_label',
                   course_code=None, unique_code=None, section_id=None):
    subscribed = has_platform_subscription(email, course_code)
    for t in tests:
        t['is_locked'] = is_test_locked(t.get(label_key), subscribed)
        if t['is_locked']:
            t['premium_url'] = premium_url(course_code, unique_code,
                                           t.get('test_id') or section_id)
    return subscribed
