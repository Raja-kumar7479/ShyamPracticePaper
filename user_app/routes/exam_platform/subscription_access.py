import logging

logger = logging.getLogger(__name__)

PREMIUM_ENDPOINT = 'practice_coding.premium'


def has_platform_subscription(email):
    if not email:
        return False
    try:
        from routes.exam_platform.placement_exam_portal.practice_coding.models import active_subscription
        return active_subscription(email) is not None
    except Exception:
        logger.exception("SUBSCRIPTION: platform subscription check failed")
        return False


def is_test_locked(access_label, subscribed):
    if subscribed:
        return False
    return (access_label or 'inherit') == 'paid'


def annotate_tests(tests, email, label_key='access_label'):
    subscribed = has_platform_subscription(email)
    for t in tests:
        t['is_locked'] = is_test_locked(t.get(label_key), subscribed)
    return subscribed
