import logging
import mysql.connector
from config import Config

logger = logging.getLogger(__name__)

class PurchaseOperation:
    def connection(self):
        try:
            from admin.db_pool import get_connection
            return get_connection()
        except mysql.connector.Error as err:
            logger.error(f"Error connecting to database: {err}")
            raise

    def _fetch_all(self, query, params=None):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True, buffered=True)
            cursor.execute(query, params or ())
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Purchase DB fetch failed: {e}", exc_info=True)
            return []
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def get_purchase_courses(self):
        query = """
            SELECT c.code, c.name,
                   COALESCE(p.purchase_count, 0) AS purchase_count,
                   COALESCE(p.buyer_count, 0) AS buyer_count,
                   COALESCE(e.enrollment_count, 0) AS enrollment_count
            FROM courses c
            LEFT JOIN (
                SELECT course_code, COUNT(*) AS purchase_count, COUNT(DISTINCT email) AS buyer_count
                FROM purchase GROUP BY course_code
            ) p ON p.course_code = c.code
            LEFT JOIN (
                SELECT course_code, COUNT(*) AS enrollment_count
                FROM enrollment_payment GROUP BY course_code
            ) e ON e.course_code = c.code
            ORDER BY c.name
        """
        rows = self._fetch_all(query)
        logger.info(f"DB PURCHASES: {len(rows)} course(s) with purchase stats")
        return rows

    def get_buyers_for_course(self, course_code):
        query = """
            SELECT email, MAX(username) AS username, COUNT(*) AS items,
                   SUM(final_price) AS total_paid, MAX(payment_date) AS last_purchase
            FROM purchase
            WHERE course_code = %s
            GROUP BY email
            ORDER BY MAX(payment_date) DESC
        """
        rows = self._fetch_all(query, (course_code,))
        logger.info(f"DB PURCHASES: {len(rows)} buyer(s) for course {course_code!r}")
        return rows

    def get_user_purchases(self, course_code, email):
        query = """
            SELECT id, email, username, phone, course_code, title, subtitle, price,
                   original_price, discount_percent, final_price, payment_id,
                   payment_mode, payment_date, purchase_code, status
            FROM purchase
            WHERE course_code = %s AND email = %s
            ORDER BY payment_date DESC, id DESC
        """
        rows = self._fetch_all(query, (course_code, email))
        logger.info(f"DB PURCHASES: {len(rows)} purchase row(s) for {email!r} in {course_code!r}")
        return rows

    def get_user_enrollment_payments(self, course_code, email):
        query = """
            SELECT id, user_email AS email, user_username AS username, course_code,
                   amount_paid, payment_id, razorpay_payment_id, payment_method,
                   payment_status, completion_date
            FROM enrollment_payment
            WHERE course_code = %s AND user_email = %s
            ORDER BY completion_date DESC, id DESC
        """
        rows = self._fetch_all(query, (course_code, email))
        logger.info(f"DB PURCHASES: {len(rows)} enrollment payment(s) for {email!r} in {course_code!r}")
        return rows

    def find_by_payment_id(self, payment_id):
        purchases = self._fetch_all(
            """
            SELECT id, email, username, phone, course_code, title, subtitle, price,
                   original_price, discount_percent, final_price, payment_id,
                   payment_mode, payment_date, purchase_code, status
            FROM purchase WHERE payment_id = %s
            ORDER BY payment_date DESC
            """,
            (payment_id,)
        )
        enrollments = self._fetch_all(
            """
            SELECT id, user_email AS email, user_username AS username, course_code,
                   amount_paid, payment_id, razorpay_payment_id, payment_method,
                   payment_status, completion_date
            FROM enrollment_payment
            WHERE payment_id = %s OR razorpay_payment_id = %s
            """,
            (payment_id, payment_id)
        )
        logger.info(f"DB PURCHASES: payment_id {payment_id!r} -> {len(purchases)} purchase(s), {len(enrollments)} enrollment(s)")
        return purchases, enrollments

    def get_all_purchase_details(self):
        query = """
            SELECT id, email, username, phone, course_code, title, subtitle, price,
                   original_price, discount_percent, final_price, payment_id,
                   payment_mode, payment_date, purchase_code, status
            FROM purchase
            ORDER BY payment_date DESC
        """
        return self._fetch_all(query)

    def get_purchase_by_email_and_payment_id(self, email, payment_id):
        query = """
            SELECT id, email, username, phone, course_code, title, subtitle, price,
                   original_price, discount_percent, final_price, payment_id,
                   payment_mode, payment_date, purchase_code, status
            FROM purchase
            WHERE email = %s AND payment_id = %s
        """
        return self._fetch_all(query, (email, payment_id))

    def delete_purchase_by_id(self, purchase_id):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(buffered=True)
            cursor.execute("DELETE FROM purchase WHERE id = %s AND status = 'Pending'", (purchase_id,))
            db.commit()
            logger.warning(f"DB PURCHASES: deleted pending purchase id={purchase_id} ({cursor.rowcount} row)")
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting purchase with ID: {purchase_id}: {e}", exc_info=True)
            if db: db.rollback()
            return False
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def _fetch_one(self, query, params=None):
        rows = self._fetch_all(query + " LIMIT 1", params)
        return rows[0] if rows else None


    def get_groups_with_codes(self):
        rows = self._fetch_all("""
            SELECT g.group_name, g.label AS group_label,
                   c.code, c.label AS code_label,
                   COALESCE(p.purchase_count, 0)   AS purchase_count,
                   COALESCE(p.buyer_count, 0)      AS buyer_count,
                   COALESCE(e.enrollment_count, 0) AS enrollment_count
            FROM course_groups g
            JOIN course_group_codes c ON c.group_name = g.group_name
            LEFT JOIN (SELECT course_code, COUNT(*) AS purchase_count, COUNT(DISTINCT email) AS buyer_count
                       FROM purchase GROUP BY course_code) p ON p.course_code = c.code
            LEFT JOIN (SELECT course_code, COUNT(*) AS enrollment_count
                       FROM enrollment_payment GROUP BY course_code) e ON e.course_code = c.code
            ORDER BY g.position, g.group_name, c.position, c.code
        """)
        groups = {}
        for r in rows:
            g = groups.setdefault(r['group_name'], {'group_name': r['group_name'],
                                                    'label': r['group_label'], 'codes': []})
            g['codes'].append({k: r[k] for k in ('code', 'code_label', 'purchase_count',
                                                  'buyer_count', 'enrollment_count')})
        return list(groups.values())

    def search_customers(self, q, course_code=None, limit=25):
        q = (q or '').strip()
        if not q:
            return []
        like = q + '%'
        found = {}

        def bucket(email):
            return found.setdefault(email, {
                'email': email, 'username': None, 'phone': None,
                'purchases': 0, 'enrollments': 0, 'subscriptions': 0,
                'total_paid': 0.0, 'last_activity': None, 'registered': False,
            })

        def touch(row, when):
            if when and (row['last_activity'] is None or when > row['last_activity']):
                row['last_activity'] = when

        sql = """SELECT email, MAX(username) AS username, MAX(phone) AS phone, COUNT(*) AS n,
                        SUM(final_price) AS total, MAX(payment_date) AS last_at
                 FROM purchase
                 WHERE (email LIKE %s OR username LIKE %s OR phone LIKE %s OR payment_id = %s)"""
        params = [like, like, like, q]
        if course_code:
            sql += " AND course_code = %s"
            params.append(course_code)
        sql += " GROUP BY email ORDER BY last_at DESC LIMIT %s"
        params.append(int(limit))
        for r in self._fetch_all(sql, tuple(params)):
            b = bucket(r['email'])
            b['username'] = b['username'] or r['username']
            b['phone'] = b['phone'] or r['phone']
            b['purchases'] += int(r['n'] or 0)
            b['total_paid'] += float(r['total'] or 0)
            touch(b, r['last_at'])

        sql = """SELECT user_email AS email, MAX(user_username) AS username, COUNT(*) AS n,
                        SUM(amount_paid) AS total, MAX(completion_date) AS last_at
                 FROM enrollment_payment
                 WHERE (user_email LIKE %s OR user_username LIKE %s OR payment_id = %s OR razorpay_payment_id = %s)"""
        params = [like, like, q, q]
        if course_code:
            sql += " AND course_code = %s"
            params.append(course_code)
        sql += " GROUP BY user_email ORDER BY last_at DESC LIMIT %s"
        params.append(int(limit))
        for r in self._fetch_all(sql, tuple(params)):
            b = bucket(r['email'])
            b['username'] = b['username'] or r['username']
            b['enrollments'] += int(r['n'] or 0)
            b['total_paid'] += float(r['total'] or 0)
            touch(b, r['last_at'])

        if not course_code:
            for r in self._fetch_all("""
                    SELECT s.email, MAX(a.username) AS username, COUNT(*) AS n,
                           SUM(CASE WHEN s.status = 'active' THEN s.amount_paise ELSE 0 END) / 100 AS total,
                           MAX(s.created_at) AS last_at
                    FROM pcp_subscriptions s
                    LEFT JOIN auth a ON a.email = s.email
                    WHERE (s.email LIKE %s OR a.username LIKE %s OR s.razorpay_payment_id = %s)
                    GROUP BY s.email ORDER BY last_at DESC LIMIT %s""", (like, like, q, int(limit))):
                b = bucket(r['email'])
                b['username'] = b['username'] or r['username']
                b['subscriptions'] += int(r['n'] or 0)
                b['total_paid'] += float(r['total'] or 0)
                touch(b, r['last_at'])

            for r in self._fetch_all("""
                    SELECT email, username, COALESCE(last_active, created_at) AS last_at
                    FROM auth WHERE (email LIKE %s OR username LIKE %s)
                    ORDER BY last_at DESC LIMIT %s""", (like, like, int(limit))):
                b = bucket(r['email'])
                b['username'] = b['username'] or r['username']
                b['registered'] = True
                touch(b, r['last_at'])

        results = sorted(found.values(), key=lambda r: (r['last_activity'] is None, ), reverse=False)
        results.sort(key=lambda r: r['last_activity'] or 0, reverse=True)
        return results[:int(limit)]

    def get_customer_overview(self, email, course_code=None):
        account = self._fetch_one("""
            SELECT username, email, auth_type, is_verified, created_at, last_active
            FROM auth WHERE email = %s""", (email,))

        sql = """SELECT id, email, username, phone, course_code, section_id, section, title, subtitle,
                        price, original_price, discount_percent, final_price, payment_id, payment_mode,
                        payment_date, status, purchase_code
                 FROM purchase WHERE email = %s"""
        params = [email]
        if course_code:
            sql += " AND course_code = %s"
            params.append(course_code)
        purchases = self._fetch_all(sql + " ORDER BY payment_date DESC, id DESC", tuple(params))

        sql = """SELECT id, user_email AS email, user_username AS username, course_code, amount_paid,
                        currency, payment_method, payment_status, payment_id, razorpay_payment_id,
                        completion_date
                 FROM enrollment_payment WHERE user_email = %s"""
        params = [email]
        if course_code:
            sql += " AND course_code = %s"
            params.append(course_code)
        enrollments = self._fetch_all(sql + " ORDER BY completion_date DESC, id DESC", tuple(params))

        subscriptions = self._fetch_all("""
            SELECT id, plan, amount_paise / 100 AS amount, status, starts_at, expires_at, created_at,
                   razorpay_order_id, razorpay_payment_id,
                   (status = 'active' AND expires_at > NOW()) AS is_live
            FROM pcp_subscriptions WHERE email = %s
            ORDER BY created_at DESC, id DESC""", (email,))

        total = sum(float(p.get('final_price') or 0) for p in purchases)
        total += sum(float(e.get('amount_paid') or 0) for e in enrollments)
        total += sum(float(s.get('amount') or 0) for s in subscriptions if s.get('status') == 'active')
        return {
            'account': account,
            'purchases': purchases,
            'enrollment_payments': enrollments,
            'subscriptions': subscriptions,
            'total_paid': round(total, 2),
        }

    def _write(self, query, params=None):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor()
            cursor.execute(query, params or ())
            db.commit()
            return cursor.rowcount
        except Exception as e:
            logger.error(f"Purchase DB write failed: {e}", exc_info=True)
            if db:
                db.rollback()
            return 0
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def search_everything(self, q, limit=30):
        q = (q or '').strip()
        if len(q) < 2:
            return []
        like = '%' + q + '%'
        found = {}

        def bucket(email):
            return found.setdefault(email, {
                'email': email, 'username': None, 'phone': None,
                'paid_items': 0, 'premium': 0, 'pending': 0, 'enrollments': 0,
                'total_paid': 0.0, 'last_activity': None, 'registered': False, 'hit': set(),
            })

        def touch(row, when):
            if when and (row['last_activity'] is None or when > row['last_activity']):
                row['last_activity'] = when

        for r in self._fetch_all("""
                SELECT email, MAX(username) AS username, MAX(phone) AS phone, COUNT(*) AS n,
                       SUM(CASE WHEN status = 'Paid' THEN final_price ELSE 0 END) AS total, MAX(payment_date) AS last_at,
                       MAX(payment_id LIKE %s OR purchase_code LIKE %s) AS by_id
                FROM purchase
                WHERE email LIKE %s OR username LIKE %s OR phone LIKE %s OR payment_id LIKE %s OR purchase_code LIKE %s OR title LIKE %s
                GROUP BY email ORDER BY last_at DESC LIMIT %s""", (like, like, like, like, like, like, like, like, int(limit))):
            b = bucket(r['email']); b['username'] = b['username'] or r['username']; b['phone'] = b['phone'] or r['phone']
            b['paid_items'] += int(r['n'] or 0); b['total_paid'] += float(r['total'] or 0); touch(b, r['last_at'])
            b['hit'].add('payment id' if r['by_id'] else 'paid content')
        for r in self._fetch_all("""
                SELECT s.email, MAX(a.username) AS username, MAX(s.phone) AS phone, COUNT(*) AS n,
                       SUM(CASE WHEN s.status = 'active' THEN s.amount_paise ELSE 0 END) / 100 AS total,
                       MAX(s.created_at) AS last_at, SUM(s.status = 'created') AS pending,
                       MAX(s.razorpay_payment_id LIKE %s OR s.razorpay_order_id LIKE %s) AS by_id
                FROM pcp_subscriptions s LEFT JOIN auth a ON a.email = s.email
                WHERE s.email LIKE %s OR a.username LIKE %s OR s.phone LIKE %s OR s.razorpay_payment_id LIKE %s OR s.razorpay_order_id LIKE %s
                GROUP BY s.email ORDER BY last_at DESC LIMIT %s""", (like, like, like, like, like, like, like, int(limit))):
            b = bucket(r['email']); b['username'] = b['username'] or r['username']; b['phone'] = b['phone'] or r['phone']
            b['premium'] += int(r['n'] or 0); b['pending'] += int(r['pending'] or 0); b['total_paid'] += float(r['total'] or 0); touch(b, r['last_at'])
            b['hit'].add('payment id' if r['by_id'] else 'premium')
        for r in self._fetch_all("""
                SELECT email, MAX(username) AS username, MAX(phone) AS phone, COUNT(*) AS n, MAX(created_at) AS last_at,
                       MAX(razorpay_payment_id LIKE %s OR razorpay_order_id LIKE %s) AS by_id
                FROM content_orders
                WHERE status IN ('created','failed') AND (email LIKE %s OR username LIKE %s OR phone LIKE %s OR razorpay_payment_id LIKE %s OR razorpay_order_id LIKE %s)
                GROUP BY email ORDER BY last_at DESC LIMIT %s""", (like, like, like, like, like, like, like, int(limit))):
            b = bucket(r['email']); b['username'] = b['username'] or r['username']; b['phone'] = b['phone'] or r['phone']
            b['pending'] += int(r['n'] or 0); touch(b, r['last_at'])
            b['hit'].add('order id' if r['by_id'] else 'unconfirmed order')
        for r in self._fetch_all("""
                SELECT user_email AS email, MAX(user_username) AS username, COUNT(*) AS n, MAX(completion_date) AS last_at
                FROM enrollment_payment
                WHERE user_email LIKE %s OR user_username LIKE %s OR payment_id LIKE %s OR razorpay_payment_id LIKE %s
                GROUP BY user_email ORDER BY last_at DESC LIMIT %s""", (like, like, like, like, int(limit))):
            b = bucket(r['email']); b['username'] = b['username'] or r['username']
            b['enrollments'] += int(r['n'] or 0); touch(b, r['last_at']); b['hit'].add('enrollment')
        for r in self._fetch_all("""
                SELECT email, username, COALESCE(last_active, created_at) AS last_at
                FROM auth WHERE email LIKE %s OR username LIKE %s
                ORDER BY last_at DESC LIMIT %s""", (like, like, int(limit))):
            b = bucket(r['email']); b['username'] = b['username'] or r['username']; b['registered'] = True; touch(b, r['last_at'])
        out = []
        for b in found.values():
            b['hit'] = sorted(b['hit'])
            out.append(b)
        out.sort(key=lambda r: r['last_activity'] or 0, reverse=True)
        return out[:int(limit)]

    def get_customer_orders(self, email, course_code=None, limit=60):
        sql = """SELECT id, email, username, phone, course_code, unique_code, razorpay_order_id, razorpay_payment_id,
                        amount_paise / 100 AS amount, list_paise, discount_pct, cart_json, status, gateway_status,
                        payment_method, fulfilled_by, fulfilled_at, created_at
                 FROM content_orders WHERE email = %s"""
        params = [email]
        if course_code:
            sql += " AND course_code = %s"; params.append(course_code)
        sql += " ORDER BY created_at DESC, id DESC LIMIT %s"; params.append(int(limit))
        return self._fetch_all(sql, tuple(params))

    def get_subscription_detail(self, email):
        return self._fetch_all("""
            SELECT id, email, course_code, plan, plan_label, amount_paise / 100 AS amount, status, gateway_status, fulfilled_by,
                   starts_at, expires_at, plan_ends_at, created_at, razorpay_order_id, razorpay_payment_id,
                   (status = 'active' AND expires_at > NOW()) AS is_live
            FROM pcp_subscriptions WHERE email = %s ORDER BY created_at DESC, id DESC""", (email,))

    def content_order_by_order_id(self, order_id):
        return self._fetch_one("SELECT * FROM content_orders WHERE razorpay_order_id = %s", (order_id,))

    def subscription_by_order_id(self, order_id):
        return self._fetch_one("SELECT * FROM pcp_subscriptions WHERE razorpay_order_id = %s", (order_id,))

    def attention_candidates(self, days=30, limit=60):
        orders = self._fetch_all("""
            SELECT 'content' AS kind, id, email, username, course_code, razorpay_order_id, razorpay_payment_id,
                   amount_paise, status, gateway_status, created_at
            FROM content_orders
            WHERE status IN ('created','failed') AND created_at >= (NOW() - INTERVAL %s DAY) AND created_at <= (NOW() - INTERVAL 3 MINUTE)
            ORDER BY created_at DESC LIMIT %s""", (int(days), int(limit)))
        subs = self._fetch_all("""
            SELECT 'premium' AS kind, s.id, s.email, a.username, s.course_code, s.razorpay_order_id, s.razorpay_payment_id,
                   s.amount_paise, s.status, s.gateway_status, s.created_at
            FROM pcp_subscriptions s LEFT JOIN auth a ON a.email = s.email
            WHERE s.status IN ('created','failed') AND s.created_at >= (NOW() - INTERVAL %s DAY) AND s.created_at <= (NOW() - INTERVAL 3 MINUTE)
            ORDER BY s.created_at DESC LIMIT %s""", (int(days), int(limit)))
        granted = self._fetch_all("""
            SELECT 'content' AS kind, id, email, username, course_code, razorpay_order_id, razorpay_payment_id,
                   amount_paise, status, gateway_status, created_at
            FROM content_orders WHERE status = 'paid' AND created_at >= (NOW() - INTERVAL %s DAY)
            ORDER BY created_at DESC LIMIT %s""", (int(days), int(limit)))
        granted += self._fetch_all("""
            SELECT 'premium' AS kind, s.id, s.email, a.username, s.course_code, s.razorpay_order_id, s.razorpay_payment_id,
                   s.amount_paise, s.status, s.gateway_status, s.created_at
            FROM pcp_subscriptions s LEFT JOIN auth a ON a.email = s.email
            WHERE s.status = 'active' AND s.expires_at > NOW() AND s.created_at >= (NOW() - INTERVAL %s DAY)
            ORDER BY s.created_at DESC LIMIT %s""", (int(days), int(limit)))
        return orders + subs, granted

    def grant_content_order(self, order, payment_id, admin_email, method='razorpay'):
        import json, secrets, string
        from datetime import datetime
        try:
            cart = json.loads(order.get('cart_json') or '[]')
        except ValueError:
            cart = []
        if not cart:
            return 0
        discount = float(order.get('discount_pct') or 0)
        now = datetime.now()
        inserted = 0
        for item in cart:
            price = float(item.get('price') or 0)
            final_price = round(price - round(price * discount / 100, 2), 2)
            code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(10))
            section_id = item.get('section_id')
            if section_id and not self._fetch_one("SELECT 1 FROM course_content WHERE section_id = %s", (section_id,)):
                section_id = None
            inserted += self._write("""
                INSERT IGNORE INTO purchase (email, username, phone, title, subtitle, price, original_price, discount_percent,
                                             final_price, payment_date, payment_id, status, purchase_code, course_code, section, section_id, payment_mode)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Paid',%s,%s,%s,%s,%s)
            """, (order['email'], order.get('username') or order['email'], order.get('phone') or '', item.get('title'),
                  item.get('subtitle', ''), price, price, discount, final_price, now, payment_id, code,
                  order['course_code'], item.get('section'), section_id, method))
        self._write("""UPDATE content_orders SET status='paid', gateway_status='captured', razorpay_payment_id=%s,
                       payment_method=%s, fulfilled_by=%s, fulfilled_at=NOW() WHERE id=%s""",
                    (payment_id, method, f'admin:{admin_email}'[:60], order['id']))
        return inserted

    def grant_subscription(self, row, payment_id, admin_email):
        from datetime import datetime, timedelta
        now = datetime.now()
        ends = row.get('plan_ends_at')
        if not ends and row.get('course_code'):
            plan = self._fetch_one("SELECT valid_until, extra_days FROM premium_plans WHERE code = %s AND plan_key = %s",
                                   (row['course_code'], row['plan']))
            if plan and plan.get('valid_until'):
                ends = plan['valid_until'] + timedelta(days=int(plan.get('extra_days') or 0))
        if not ends:
            return None
        current = self._fetch_one("""SELECT expires_at FROM pcp_subscriptions WHERE email = %s AND status = 'active'
                                     AND expires_at > NOW() AND (course_code = %s OR course_code IS NULL)
                                     ORDER BY expires_at DESC""", (row['email'], row.get('course_code')))
        if current and current['expires_at'] > ends:
            ends = current['expires_at']
        self._write("""UPDATE pcp_subscriptions SET status='active', gateway_status='captured', razorpay_payment_id=%s,
                       fulfilled_by=%s, starts_at=%s, expires_at=%s WHERE id=%s AND status IN ('created','failed')""",
                    (payment_id, f'admin:{admin_email}'[:60], now, ends, row['id']))
        return ends

    def revoke_payment(self, payment_id, admin_email):
        n = self._write("UPDATE purchase SET status='Refunded' WHERE payment_id = %s AND status = 'Paid'", (payment_id,))
        n += self._write("""UPDATE content_orders SET status='refunded', gateway_status='refunded', fulfilled_by=%s
                            WHERE razorpay_payment_id = %s AND status = 'paid'""", (f'revoked:{admin_email}'[:60], payment_id))
        n += self._write("""UPDATE pcp_subscriptions SET status='refunded', gateway_status='refunded', fulfilled_by=%s
                            WHERE razorpay_payment_id = %s AND status = 'active'""", (f'revoked:{admin_email}'[:60], payment_id))
        return n

    def access_for_payment(self, payment_id):
        row = self._fetch_one("SELECT COUNT(*) AS n, SUM(status = 'Paid') AS paid FROM purchase WHERE payment_id = %s", (payment_id,))
        if row and int(row['n'] or 0):
            return 'granted' if int(row['paid'] or 0) else 'revoked'
        sub = self._fetch_one("SELECT status, expires_at FROM pcp_subscriptions WHERE razorpay_payment_id = %s ORDER BY id DESC", (payment_id,))
        if sub:
            if sub['status'] == 'active':
                from datetime import datetime
                return 'granted' if (sub['expires_at'] and sub['expires_at'] > datetime.now()) else 'expired'
            return 'revoked' if sub['status'] == 'refunded' else 'not_granted'
        return 'not_granted'

