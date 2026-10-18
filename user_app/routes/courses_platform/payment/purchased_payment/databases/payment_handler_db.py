import logging
import mysql.connector
from routes.db_pool import get_connection
from mysql.connector import Error
from config import Config


logger = logging.getLogger(__name__)

class UserOperation:
    def connection(self):
        return get_connection()

    def get_user_unique_code(self, email, course_code):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            query = "SELECT unique_code FROM enrollment WHERE email = %s AND code = %s"
            cursor.execute(query, (email, course_code))
            result = cursor.fetchone()
            return result['unique_code'] if result else None
        except Error as e:
            logger.error(f"Error getting unique code for {email}/{course_code}: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if conn:
                try: conn.close()
                except Exception: pass

    def get_all_active_coupons(self, email=None):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            if email:
                query = """
                    SELECT * FROM coupone WHERE status = 1
                      AND (email IS NULL OR email = %s)
                      AND (valid_until IS NULL OR valid_until > NOW())
                      AND (expiry_date IS NULL OR expiry_date > NOW())
                """
                cursor.execute(query, (email,))
            else:
                query = """
                    SELECT * FROM coupone WHERE status = 1
                      AND email IS NULL
                      AND (valid_until IS NULL OR valid_until > NOW())
                      AND (expiry_date IS NULL OR expiry_date > NOW())
                """
                cursor.execute(query)
            return cursor.fetchall()
        except Error as e:
            logger.error(f"Error getting active coupons: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conn:
                try: conn.close()
                except Exception: pass

    def get_coupon_by_code(self, code, email=None):
        conn = None
        cursor = None
        try:
            conn =  self.connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            query = """
                SELECT * FROM coupone WHERE coupon_code = %s AND status = 1
                  AND (email IS NULL OR email = %s)
                  AND (valid_until IS NULL OR valid_until > NOW())
                  AND (expiry_date IS NULL OR expiry_date > NOW())
            """
            cursor.execute(query, (code, email))
            return cursor.fetchall()
        except Error as e:
            logger.error(f"Error getting coupon by code '{code}': {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conn:
                try: conn.close()
                except Exception: pass

    def add_purchase_transactional(self, purchases_data):
        if not purchases_data:
            return False
        payment_id = purchases_data[0].get('payment_id')
        query = """
            INSERT INTO purchase (
                email, username, phone, title, subtitle, price, original_price,
                discount_percent, final_price, payment_date, payment_id, status,
                purchase_code, course_code, section, section_id, payment_mode
            ) VALUES (
                %(email)s, %(username)s, %(phone)s, %(title)s, %(subtitle)s, %(price)s,
                %(original_price)s, %(discount_percent)s, %(final_price)s, %(payment_date)s,
                %(payment_id)s, %(status)s, %(purchase_code)s, %(course_code)s,
                %(section)s, %(section_id)s, %(payment_mode)s
            )
        """
        RETRYABLE = (1213, 1205)
        for attempt in range(1, 4):
            conn = cursor = None
            try:
                conn = self.connection()
                cursor = conn.cursor(buffered=True)
                conn.start_transaction()
                cursor.execute(
                    "SELECT payment_id FROM purchase WHERE payment_id = %s LIMIT 1 FOR UPDATE",
                    (payment_id,)
                )
                if cursor.fetchone():
                    conn.rollback()
                    logger.info(f"Purchase for payment_id {payment_id} already recorded; nothing to add.")
                    return True
                for purchase_data in purchases_data:
                    cursor.execute(query, purchase_data)
                conn.commit()
                return True
            except Error as e:
                if conn:
                    try: conn.rollback()
                    except Error: pass
                errno = getattr(e, 'errno', None)
                if errno == 1062:
                    logger.info(f"Purchase for payment_id {payment_id} was saved by a concurrent request.")
                    return True
                if errno in RETRYABLE and attempt < 3:
                    logger.info(f"Purchase insert for payment_id {payment_id} hit {errno}; retry {attempt}/2")
                    continue
                logger.error(f"Transactional error for payment_id {payment_id}: {e}")
                return False
            finally:
                if cursor: cursor.close()
                if conn: conn.close()
        return False

    def get_all_purchases(self, email):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            query = """
                SELECT p.*, cc.status AS content_status FROM purchase AS p
                LEFT JOIN course_content AS cc ON p.section_id = cc.section_id
                WHERE p.email = %s
                ORDER BY p.payment_date DESC, p.section_id ASC
            """
            cursor.execute(query, (email,))
            return cursor.fetchall()
        except Error as e:
            logger.error(f"Error getting all purchases for {email}: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conn:
                try: conn.close()
                except Exception: pass
    
    def get_purchased_content_titles(self, email, course_code):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            query = """
                SELECT title
                FROM purchase
                WHERE email = %s AND course_code = %s AND status = 'Paid'
            """
            cursor.execute(query, (email, course_code))
            return [row['title'] for row in cursor.fetchall()]
        except Error as e:
            logger.error(f"Error getting purchased content titles for {email}/{course_code}: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conn:
                try: conn.close()
                except Exception: pass

    def get_content_by_code_title_subtitle(self, course_code, title, subtitle):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            query = """
                SELECT * FROM course_content
                WHERE code = %s
                  AND title = %s
                  AND COALESCE(subtitle, '') = COALESCE(%s, '')
                  AND label = 'Paid'
                  AND status = 'active'
                LIMIT 1
            """
            cursor.execute(query, (course_code, title, subtitle))
            return cursor.fetchone()
        except Error as e:
            logger.error(f"Error getting content by code/title/subtitle: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if conn:
                try: conn.close()
                except Exception: pass
            
    def get_premium_courses_by_code(self, course_code):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            query = "SELECT * FROM course_content WHERE code = %s AND price > 0 ORDER BY title ASC"
            cursor.execute(query, (course_code,))
            return cursor.fetchall()
        except Error as e:
            logger.error(f"Error getting premium courses for code {course_code}: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conn:
                try: conn.close()
                except Exception: pass

    def get_course_details(self, course_code):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            query = "SELECT code, name, description FROM courses WHERE code = %s"
            cursor.execute(query, (course_code,))
            return cursor.fetchone()
        except Error as e:
            logger.error(f"Error getting course details for code {course_code}: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if conn:
                try: conn.close()
                except Exception: pass

    def get_free_courses_by_code(self, code):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            query = """
                SELECT * FROM course_content 
                WHERE code = %s AND status = 'active' AND label = 'Free'
                ORDER BY 
                    FIELD(section, 'NOTES', 'PRACTICE BOOK', 'PYQ','MOCK TEST')
            """
            cursor.execute(query, (code,))
            return cursor.fetchall()
        except Error as e:
            logger.error(f"Error getting free courses: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conn:
                try: conn.close()
                except Exception: pass

    def get_practice_sections_for_code(self, code):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(buffered=True)
            query = "SELECT DISTINCT section FROM practice_questions WHERE code = %s"
            cursor.execute(query, (code,))
            sections = [row[0] for row in cursor.fetchall()]
            return sections
        except Error as e:
            logger.error(f"Error getting practice sections: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conn:
                try: conn.close()
                except Exception: pass

    def is_course_purchased_securely(self, email, course_code, title, subtitle):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            query = """
                SELECT status, purchase_code FROM purchase
                WHERE email = %s AND course_code = %s AND title = %s
                  AND COALESCE(subtitle, '') = COALESCE(%s, '') AND status = 'Paid'
            """
            cursor.execute(query, (email, course_code, title, subtitle))
            results = cursor.fetchall()
            return results[0] if results else None
        except Error as e:
            logger.error(f"Error checking secure purchase for {email}: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if conn:
                try: conn.close()
                except Exception: pass

    def content_exists(self, section_id):
        db = cursor = None
        try:
            db = self.connection()
            cursor = db.cursor()
            cursor.execute("SELECT 1 FROM course_content WHERE section_id = %s LIMIT 1", (section_id,))
            return cursor.fetchone() is not None
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def get_purchase_by_payment_id(self, email, payment_id):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            query = "SELECT * FROM purchase WHERE email = %s AND payment_id = %s"
            cursor.execute(query, (email, payment_id))
            return cursor.fetchall()
        except Error as e:
            logger.error(f"Error getting purchase by payment_id {payment_id}: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if conn:
                try: conn.close()
                except Exception: pass