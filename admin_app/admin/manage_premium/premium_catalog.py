import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from flask import jsonify, render_template, request, session

from admin import admin_bp
from admin.db_pool import get_connection
from extensions import admin_login_required, can_manage

logger = logging.getLogger(__name__)


def _payable(price, discount):
    price = Decimal(str(price or 0))
    off = Decimal(str(discount or 0))
    if not (0 <= off < 100):
        off = Decimal(0)
    return float((price - price * off / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _stamp(value, fmt='%Y-%m-%dT%H:%M'):
    return value.strftime(fmt) if value is not None and hasattr(value, 'strftime') else value


def _add_months(day, months):
    year, month = divmod(day.month - 1 + months, 12)
    year, month = day.year + year, month + 1
    for last in (31, 30, 29, 28):
        try:
            return day.replace(year=year, month=month, day=min(day.day, last))
        except ValueError:
            continue
    return day


def _span(end, now=None):
    now = now or datetime.now()
    today, last = now.date(), end.date()
    days = (last - today).days
    if days <= 0:
        return days, ''
    months = (last.year - today.year) * 12 + (last.month - today.month)
    if _add_months(today, months) > last:
        months -= 1
    rest = (last - _add_months(today, months)).days
    years, months = divmod(months, 12)
    bits = []
    if years:
        bits.append(f"{years} year{'s' if years > 1 else ''}")
    if months:
        bits.append(f"{months} month{'s' if months > 1 else ''}")
    if rest or not bits:
        bits.append(f"{rest} day{'s' if rest != 1 else ''}")
    return days, ' '.join(bits)


def _plan_key(label):
    return re.sub(r'[^a-z0-9]+', '-', (label or '').lower()).strip('-')[:40] or 'plan'


def _serialise_plan(row):
    now = datetime.now()
    out = {k: (float(v) if isinstance(v, Decimal) else v) for k, v in row.items()}
    live = float(row.get('discount') or 0) > 0 and (row.get('discount_ends_at') is None or row.get('discount_ends_at') > now)
    out['payable'] = _payable(row.get('price'), row.get('discount') if live else 0)
    out['discount_ends_at'] = _stamp(row.get('discount_ends_at'))
    out['valid_until'] = _stamp(row.get('valid_until'))
    ends = row['valid_until'] + timedelta(days=int(row.get('extra_days') or 0)) if row.get('valid_until') else None
    out['ends_at'] = _stamp(ends, '%d %b %Y, %I:%M %p')
    days, span = _span(ends, now) if ends else (0, '')
    out['days'] = max(0, days)
    out['span'] = span
    out['expired'] = bool(ends and ends <= now)
    for k in ('created_at', 'updated_at'):
        out[k] = _stamp(out.get(k), '%d %b %Y, %I:%M %p')
    return out


def _serialise(row):
    if not row:
        return None
    out = {k: (float(v) if isinstance(v, Decimal) else v) for k, v in row.items()}
    for k in ('created_at', 'updated_at'):
        out[k] = _stamp(out.get(k), '%d %b %Y, %I:%M %p')
    return out


class PremiumCatalogDB:
    def _run(self, sql, params=(), one=False, write=False):
        conn = get_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        try:
            cursor.execute(sql, params)
            if write:
                conn.commit()
                return cursor.lastrowid or cursor.rowcount
            result = cursor.fetchone() if one else cursor.fetchall()
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def courses(self):
        return self._run("SELECT code, name FROM courses ORDER BY code")

    def row(self, code):
        return self._run("SELECT * FROM premium_catalog WHERE code = %s", (code,), one=True)

    def rows(self):
        return {r['code']: r for r in self._run("SELECT * FROM premium_catalog")}

    def plans(self, code):
        return self._run("SELECT * FROM premium_plans WHERE code = %s ORDER BY valid_until, id", (code,))

    def all_plans(self):
        out = {}
        for r in self._run("SELECT * FROM premium_plans ORDER BY code, valid_until, id"):
            out.setdefault(r['code'], []).append(r)
        return out

    def plan(self, plan_id):
        return self._run("SELECT * FROM premium_plans WHERE id = %s", (plan_id,), one=True)

    def save_copy(self, code, headline, details):
        self._run("""
            INSERT INTO premium_catalog (code, headline, details) VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE headline = VALUES(headline), details = VALUES(details)
        """, (code, headline, details), write=True)
        return self.row(code)

    def save_plan(self, code, plan_id, data):
        if plan_id:
            self._run("""
                UPDATE premium_plans SET plan_key=%s, label=%s, price=%s, discount=%s, discount_ends_at=%s,
                       valid_until=%s, extra_days=%s
                 WHERE id=%s AND code=%s
            """, (data['plan_key'], data['label'], data['price'], data['discount'], data['discount_ends_at'],
                  data['valid_until'], data['extra_days'], plan_id, code), write=True)
            return plan_id
        return self._run("""
            INSERT INTO premium_plans (code, plan_key, label, price, discount, discount_ends_at, valid_until, extra_days)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (code, data['plan_key'], data['label'], data['price'], data['discount'], data['discount_ends_at'],
              data['valid_until'], data['extra_days']), write=True)

    def delete_plan(self, code, plan_id):
        return self._run("DELETE FROM premium_plans WHERE id = %s AND code = %s", (plan_id, code), write=True)

    def holders(self, code, plan_key):
        now = datetime.now()
        row = self._run("""
            SELECT COALESCE(SUM(status = 'active' AND expires_at > %s), 0) AS active,
                   COALESCE(SUM(status = 'created' AND created_at > %s), 0) AS pending
              FROM pcp_subscriptions WHERE course_code = %s AND plan = %s
        """, (now, now - timedelta(days=7), code, plan_key), one=True) or {}
        return {'active': int(row.get('active') or 0), 'pending': int(row.get('pending') or 0)}

    def used_keys(self, code):
        return {r['plan'] for r in self._run(
            "SELECT DISTINCT plan FROM pcp_subscriptions WHERE course_code = %s", (code,))}


db = PremiumCatalogDB()


@admin_bp.route('/manage-premium')
@admin_login_required
def manage_premium():
    admin_email = session.get('admin_email', 'UnknownAdmin')
    logger.info(f"[{admin_email}] Accessed /manage-premium")
    return render_template('admin/manage_premium/premium_catalog.html', courses=db.courses(),
                           today_label=datetime.now().strftime('%A, %d %b %Y'))


@admin_bp.route('/api/premium-catalog', methods=['GET'])
@admin_login_required
def premium_catalog_list():
    try:
        rows = db.rows()
        plans = db.all_plans()
        now = datetime.now()
        return jsonify({'success': True, 'today': now.strftime('%Y-%m-%d'),
                        'today_label': now.strftime('%A, %d %b %Y'), 'courses': [
            {'code': c['code'], 'name': c['name'], 'row': _serialise(rows.get(c['code'])),
             'plans': [_serialise_plan(p) for p in plans.get(c['code'], [])]}
            for c in db.courses()
        ]})
    except Exception:
        logger.exception("PREMIUM CATALOG: could not list")
        return jsonify({'success': False, 'message': 'Could not load the premium catalog.'}), 500


def _money(value, name, minimum):
    try:
        number = Decimal(str(value if value not in (None, '') else '0'))
    except Exception:
        return None, f"{name} must be a number."
    if number < minimum:
        return None, f"{name} must be at least {minimum}."
    return number.quantize(Decimal('0.01')), None


def _when(raw, name):
    raw = (raw or '').strip()
    if not raw:
        return None, None
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(raw, fmt), None
        except ValueError:
            continue
    return None, f'{name} must be a valid date and time.'


def _known_course(code):
    return any(c['code'] == code for c in db.courses())


def course_has_premium(code):
    code = (code or '').strip().upper()
    if not code:
        return False
    now = datetime.now()
    return any((p.get('valid_until') and p['valid_until'] + timedelta(days=int(p.get('extra_days') or 0)) > now)
               for p in db.plans(code))


PREMIUM_NOT_SET = ('Premium is not set up for this course yet. Open Premium Catalog, add a plan for it, '
                   'and then this can be Premium - otherwise students would see Unlock Premium and land on an empty page.')


@admin_bp.route('/api/premium-catalog/<code>/copy', methods=['POST'])
@admin_login_required
def premium_copy_save(code):
    admin_email = session.get('admin_email', 'UnknownAdmin')
    if not can_manage():
        return jsonify({'success': False, 'message': 'Permission Denied.'}), 403
    code = (code or '').strip().upper()
    if not _known_course(code):
        return jsonify({'success': False, 'message': 'Unknown course.'}), 404

    data = request.get_json(silent=True) or {}
    headline = (data.get('headline') or '').strip()[:160]
    if not headline:
        return jsonify({'success': False, 'message': 'Headline is required.'}), 400
    if not db.plans(code):
        return jsonify({'success': False, 'message': 'Add at least one plan first - page text is only shown when a plan is on sale.'}), 400
    from admin.manage_modules.course_content import clean_details
    details = clean_details(data.get('details') or '') or None
    if not details or not re.sub(r'<[^>]+>|&nbsp;|\s', '', details):
        return jsonify({'success': False, 'message': '"What you get" is required.'}), 400
    try:
        row = db.save_copy(code, headline, details)
    except Exception:
        logger.exception(f"PREMIUM COPY FAILED: [{admin_email}] {code}")
        return jsonify({'success': False, 'message': 'Could not save. The server log has the reason.'}), 500
    logger.info(f"ADMIN ACTION by {admin_email}: premium copy for {code} saved")
    return jsonify({'success': True, 'message': f'Premium page text for {code} saved.', 'row': _serialise(row)})


def _minimum_days(label):
    low = label.lower()
    if 'year' in low:
        return 365
    if 'month' in low:
        return 30
    return 1


@admin_bp.route('/api/premium-catalog/<code>/plans', methods=['POST'])
@admin_login_required
def premium_plan_save(code):
    admin_email = session.get('admin_email', 'UnknownAdmin')
    if not can_manage():
        return jsonify({'success': False, 'message': 'Permission Denied.'}), 403
    code = (code or '').strip().upper()
    if not _known_course(code):
        return jsonify({'success': False, 'message': 'Unknown course.'}), 404

    data = request.get_json(silent=True) or {}
    plan_id = data.get('id')
    label = (data.get('label') or '').strip()[:80]
    if not label:
        return jsonify({'success': False, 'message': 'Plan name is required, for example Monthly or Valid till GATE 2027.'}), 400

    current = None
    if plan_id:
        try:
            current = db.plan(int(plan_id))
        except (TypeError, ValueError):
            current = None
        if not current or current['code'] != code:
            return jsonify({'success': False, 'message': 'That plan no longer exists. Reload the page.'}), 404
    price, err = _money(data.get('price'), 'Amount', 1)
    if err: return jsonify({'success': False, 'message': err}), 400
    discount, err = _money(data.get('discount') or 0, 'Discount', 0)
    if err: return jsonify({'success': False, 'message': err}), 400
    if discount >= 100:
        return jsonify({'success': False, 'message': 'Discount must be below 100%.'}), 400

    discount_ends_at, err = _when(data.get('discount_ends_at'), 'The discount end date')
    if err: return jsonify({'success': False, 'message': err}), 400
    valid_until, err = _when(data.get('valid_until'), 'The valid-until date')
    if err: return jsonify({'success': False, 'message': err}), 400
    if not valid_until:
        return jsonify({'success': False, 'message': 'Valid until is required - the date this plan gives access to.'}), 400

    raw_extra = str(data.get('extra_days') or '0').strip()
    if not raw_extra.isdigit():
        return jsonify({'success': False, 'message': 'Extra days must be a whole number (0 or more).'}), 400
    extra_days = int(raw_extra)

    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    need = _minimum_days(label)
    earliest = today + timedelta(days=need)
    if valid_until < earliest:
        what = 'a yearly plan' if need == 365 else ('a monthly plan' if need == 30 else 'a plan')
        return jsonify({'success': False,
                        'message': f'"{label}" is {what}, so the date must be at least {need} days from today - '
                                   f'on or after {earliest.strftime("%d %b %Y")}. Later is fine, earlier is not.'}), 400
    years = re.findall(r'(20\d{2})', label)
    if years and str(valid_until.year) not in years:
        return jsonify({'success': False,
                        'message': f'The name says {years[0]}, so the valid-until date must fall in {years[0]}.'}), 400

    if discount > 0 and not discount_ends_at:
        return jsonify({'success': False, 'message': 'A discount needs a "Discount valid until" date.'}), 400
    if discount > 0 and discount_ends_at <= now:
        return jsonify({'success': False, 'message': 'The discount end date is already past.'}), 400
    if discount > 0 and discount_ends_at >= valid_until:
        return jsonify({'success': False, 'message': 'The discount must end before the plan itself does.'}), 400
    if discount <= 0:
        discount_ends_at = None

    wanted = _plan_key(label)
    try:
        others = [p for p in db.plans(code) if not current or p['id'] != current['id']]
        if any(p['plan_key'] == wanted or _plan_key(p['label']) == wanted for p in others):
            return jsonify({'success': False, 'message': f'A plan named "{label}" already exists for {code}.'}), 409
        if current:
            key = current['plan_key']
        else:
            taken = {p['plan_key'] for p in others} | db.used_keys(code)
            key, n = wanted, 2
            while key in taken:
                key = f"{wanted[:36]}-{n}"
                n += 1
        held = db.holders(code, key) if current else {'active': 0, 'pending': 0}
        total = held['active'] + held['pending']
        if total and str(data.get('approved_holders')) != str(total):
            return jsonify({'success': False, 'needs_approval': True, 'holders': held,
                            'message': f'{total} student(s) already bought "{current["label"]}" or are paying for it. '
                                       f'Approve the change again - it applies only to new buyers.'}), 409
        payload = {'plan_key': key, 'label': label, 'price': price, 'discount': discount,
                   'discount_ends_at': discount_ends_at, 'valid_until': valid_until, 'extra_days': extra_days}
        saved_id = db.save_plan(code, current['id'] if current else None, payload)
    except Exception:
        logger.exception(f"PREMIUM PLAN FAILED: [{admin_email}] {code} {label!r}")
        return jsonify({'success': False, 'message': 'Could not save the plan.'}), 500

    ends = valid_until + timedelta(days=extra_days)
    days, span = _span(ends, now)
    logger.info(f"ADMIN ACTION by {admin_email}: premium plan {code}/{key} -> {price} (-{discount}%), "
                f"until {valid_until} +{extra_days}d = {days} days from today; "
                f"{held['active']} holder(s) and {held['pending']} checkout(s) keep their own terms")
    message = (f'Plan "{label}" saved. New buyers get {days} days ({span}) of access, '
               f'until {ends.strftime("%d %b %Y")}.')
    if total:
        message += (f' The {total} student(s) who already bought it or are paying keep their own amount '
                    f'and end date.')
    return jsonify({'success': True, 'message': message, 'holders': held,
                    'plans': [_serialise_plan(p) for p in db.plans(code)], 'id': saved_id})


@admin_bp.route('/api/premium-catalog/<code>/plans/<int:plan_id>/holders', methods=['GET'])
@admin_login_required
def premium_plan_holders(code, plan_id):
    code = (code or '').strip().upper()
    plan = db.plan(plan_id)
    if not plan or plan['code'] != code:
        return jsonify({'success': False, 'message': 'That plan no longer exists. Reload the page.'}), 404
    return jsonify({'success': True, 'holders': db.holders(code, plan['plan_key'])})


@admin_bp.route('/api/premium-catalog/<code>/plans/<int:plan_id>', methods=['DELETE'])
@admin_login_required
def premium_plan_delete(code, plan_id):
    admin_email = session.get('admin_email', 'UnknownAdmin')
    if not can_manage():
        return jsonify({'success': False, 'message': 'Permission Denied.'}), 403
    code = (code or '').strip().upper()
    plan = db.plan(plan_id)
    if not plan or plan['code'] != code:
        return jsonify({'success': False, 'message': 'Plan not found.'}), 404
    held = db.holders(code, plan['plan_key'])
    sold = held['active'] + held['pending']
    db.delete_plan(code, plan_id)
    logger.warning(f"ADMIN ACTION by {admin_email}: deleted premium plan {code}/{plan['plan_key']} ({sold} holder(s) keep access)")
    note = f' {sold} student(s) who bought it keep their access until their own end date.' if sold else ''
    return jsonify({'success': True, 'message': f"Plan \"{plan['label']}\" removed - new students no longer see it.{note}",
                    'plans': [_serialise_plan(p) for p in db.plans(code)]})
