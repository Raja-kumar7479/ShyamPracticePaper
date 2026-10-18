import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from routes.db_pool import get_connection

logger = logging.getLogger(__name__)

RENEW_WINDOW_DAYS = 7
YEAR_RE = re.compile(r'(20\d{2})')


def _rows(course_code):
    if not course_code:
        return []
    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM premium_plans WHERE code = %s ORDER BY valid_until, id", (course_code,))
        return cursor.fetchall()
    except Exception:
        logger.exception("PREMIUM PLANS: could not read plans for %s", course_code)
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def catalog_row(course_code):
    if not course_code:
        return None
    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM premium_catalog WHERE code = %s LIMIT 1", (course_code,))
        return cursor.fetchone()
    except Exception:
        logger.exception("PREMIUM CATALOG: could not read the row for %s", course_code)
        return None
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def plan_end(plan):
    return plan['valid_until'] + timedelta(days=int(plan.get('extra_days') or 0))


def plan_days(plan, start=None):
    now = start or datetime.now()
    return max(0, (plan_end(plan) - now).days)


def _shape(row, now):
    price = Decimal(str(row.get('price') or 0))
    off = Decimal(str(row.get('discount') or 0))
    if not (0 <= off < 100):
        off = Decimal(0)
    ends = row.get('discount_ends_at')
    live = off > 0 and (ends is None or ends > now)
    if not live:
        off = Decimal(0)
    payable = (price - price * off / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    valid_until = row.get('valid_until')
    end = plan_end(row)
    available = end > now
    return {
        'key': row.get('plan_key'),
        'label': row.get('label') or row.get('plan_key'),
        'price': float(price),
        'discount': float(off),
        'payable': float(payable),
        'amount': int(payable * 100),
        'saved': float(price - payable),
        'offer_ends_at': ends if live else None,
        'valid_until': valid_until,
        'ends_at': end,
        'extra_days': int(row.get('extra_days') or 0),
        'days': plan_days(row, now),
        'is_dated': True,
        'available': available,
    }


def premium_offer(course_code, now=None):
    now = now or datetime.now()
    rows = _rows(course_code)
    plans = [_shape(r, now) for r in rows]
    sellable = [p for p in plans if p['available']]
    if sellable:
        longest = max(sellable, key=lambda p: p['days'])
        for p in plans:
            p['featured'] = p is longest and len(sellable) > 1
    row = catalog_row(course_code) or {}
    return {
        'plans': plans,
        'sellable': sellable,
        'by_key': {p['key']: p for p in plans},
        'details': row.get('details') or '',
        'headline': (row.get('headline') or '').strip(),
        'offer_active': any(p['discount'] > 0 for p in sellable),
        'custom': bool(row),
        'available': bool(sellable),
        'course_code': course_code,
        'cheapest': min(sellable, key=lambda p: p['payable']) if sellable else (plans[0] if plans else None),
    }


def plan_expiry(plan, start, current_expiry=None):
    end = plan.get('ends_at') or plan_end(plan)
    if current_expiry and current_expiry > end:
        return current_expiry
    return end


def label_year_matches(label, when):
    if not when:
        return True
    found = YEAR_RE.findall(label or '')
    if not found:
        return True
    return str(when.year) in found


def renewal_state(sub, now=None):
    now = now or datetime.now()
    ends = sub.get('expires_at') if sub else None
    if not ends:
        return {'days_left': None, 'renewable': False, 'ending_soon': False}
    left = max(0, (ends - now).days)
    return {'days_left': left, 'renewable': False,
            'ending_soon': (ends - now).total_seconds() <= RENEW_WINDOW_DAYS * 86400}


def dashboard_premium(course_code, email):
    from routes.exam_platform.placement_exam_portal.practice_coding.models import active_subscription
    sub = active_subscription(email, course_code) if email else None
    if sub:
        return {'state': 'active', 'expires_at': sub.get('expires_at'),
                'plan': sub.get('plan_label') or sub.get('plan'), **renewal_state(sub)}
    offer = premium_offer(course_code)
    if not offer['available']:
        return None
    return {'state': 'offer', 'headline': offer['headline'], 'cheapest': offer['cheapest'],
            'offer_ends_at': (offer['cheapest'] or {}).get('offer_ends_at'), 'offer_active': offer['offer_active']}
