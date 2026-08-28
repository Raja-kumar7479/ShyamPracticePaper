import mysql.connector
from mysql.connector import Error
from config import Config
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class UserOperation:
    def connection(self):
        try:
            conn = mysql.connector.connect(
                host=Config.DATABASE_HOST,
                user=Config.DATABASE_USER,
                password=Config.DATABASE_PASSWORD,
                database=Config.DATABASE_NAME
            )
            return conn
        except Error as e:
            logger.critical(f"DATABASE CONNECTION ERROR: {e}")
            raise e

    def get_guest_access_code(self, course_code):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            query = "SELECT guest_access_code FROM courses WHERE code = %s"
            cursor.execute(query, (course_code,))
            result = cursor.fetchone()
            logger.info(f"DB: Fetched guest code for {course_code}")
            return result['guest_access_code'] if result else None
        except Exception as e:
            logger.error(f"DB Error in get_guest_access_code: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def get_enrolled_courses(self, email):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            query = """
                SELECT
                    e.code, e.unique_code,
                    COALESCE(ep.payment_status, 'FREE') AS payment_status,
                    ep.amount_paid
                FROM enrollment e
                LEFT JOIN enrollment_payment ep ON e.payment_id = ep.payment_id
                WHERE e.email = %s
                AND (ep.payment_status IN ('Paid', 'FREE') OR ep.payment_status IS NULL)
            """
            cursor.execute(query, (email,))
            result = cursor.fetchall()
            logger.info(f"DB: Fetched {len(result)} enrolled courses for {email}")
            return result
        except Exception as e:
            logger.error(f"DB Error in get_enrolled_courses for {email}: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def get_course_price(self, course_code):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            query = "SELECT price_inr FROM courses WHERE code = %s"
            cursor.execute(query, (course_code,))
            result = cursor.fetchone()
            price = float(result['price_inr']) if result and result['price_inr'] is not None else 0.00
            return price
        except Exception as e:
            logger.error(f"DB Error in get_course_price: {e}")
            return 0.00
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def enroll_user(self, email, course_code, course_name, unique_code, payment_id=None):
        db = None
        cursor = None
        enrollment_id = None
        try:
            db = self.connection()
            cursor = db.cursor()
            query = "INSERT INTO enrollment (email, code, name, unique_code, payment_id) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(query, (email, course_code, course_name, unique_code, payment_id))
            enrollment_id = cursor.lastrowid
            db.commit()
            logger.info(f"DB: User {email} enrolled in {course_code} with enrollment_id {enrollment_id}")
            return enrollment_id
        except Exception as e:
            logger.error(f"DB Error enrolling user {email}: {e}")
            if db: db.rollback()
            return None
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def get_user_unique_code(self, email, course_code):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            query = """
                SELECT unique_code 
                FROM enrollment 
                WHERE email = %s AND code = %s 
            """
            cursor.execute(query, (email, course_code))
            result = cursor.fetchone()
            return result['unique_code'] if result else None
        except Exception as e:
            logger.error(f"DB Error fetching unique code for {email}: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def get_course_groups(self):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            cursor.execute("SELECT DISTINCT name FROM courses ORDER BY name")
            result = cursor.fetchall()
            return result
        except Exception as e:
            logger.error(f"DB Error fetching course groups: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def get_courses_by_group(self, group_name):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            query = "SELECT code, name, description FROM courses WHERE name = %s"
            cursor.execute(query, (group_name,))
            result = cursor.fetchall()
            return result
        except Exception as e:
            logger.error(f"DB Error fetching courses for group {group_name}: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def get_course_details(self, course_code):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            query = "SELECT code, name, description FROM courses WHERE code = %s"
            cursor.execute(query, (course_code,))
            result = cursor.fetchone()
            return result
        except Exception as e:
            logger.error(f"DB Error fetching details for {course_code}: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def get_practice_sections_for_code(self, code):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor()
            query = "SELECT DISTINCT section FROM practice_questions WHERE code = %s"
            cursor.execute(query, (code,))
            result = [row[0] for row in cursor.fetchall()]
            logger.info(f"DB: Fetched practice sections for {code}")
            return result
        except Exception as e:
            logger.error(f"DB Error fetching practice sections for {code}: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def get_free_courses_by_code(self, code):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            query = """
                SELECT * FROM course_content 
                WHERE code = %s AND status = 'active' AND label = 'Free'
                ORDER BY FIELD(section, 'NOTES', 'PRACTICE BOOK', 'PYQ','MOCK TEST')
            """
            cursor.execute(query, (code,))
            result = cursor.fetchall()
            logger.info(f"DB: Fetched free content for {code}")
            return result
        except Exception as e:
            logger.error(f"DB Error fetching free content for {code}: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def get_paid_courses_by_code(self, code):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            query = """
                SELECT * FROM course_content 
                WHERE code = %s AND status = 'active' AND label = 'Paid'
                ORDER BY FIELD(section, 'NOTES', 'PRACTICE BOOK', 'PYQ','MOCK TEST')
            """
            cursor.execute(query, (code,))
            result = cursor.fetchall()
            logger.info(f"DB: Fetched paid content for {code}")
            return result
        except Exception as e:
            logger.error(f"DB Error fetching paid content for {code}: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def get_purchased_content_titles(self, email, course_code):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor()
            query = "SELECT DISTINCT title FROM purchase WHERE email = %s AND course_code = %s AND status = 'Paid'"
            cursor.execute(query, (email, course_code))
            result = [row[0] for row in cursor.fetchall()]
            logger.info(f"DB: Fetched purchased content titles for {email} in {course_code}")
            return result
        except Exception as e:
            logger.error(f"DB Error fetching purchases for {email}: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def get_enrollment_count(self, email):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM enrollment e
                LEFT JOIN enrollment_payment ep ON e.payment_id = ep.payment_id
                WHERE e.email = %s 
                AND (ep.payment_status IN ('Paid', 'FREE') OR ep.payment_status IS NULL)
            """, (email,))
            r = cursor.fetchone()
            return r['count'] if r else 0
        except Exception as e: 
            logger.error(f"DB Error getting enrollment count for {email}: {e}")
            return 0
        finally: 
            if cursor: cursor.close()
            if db: db.close()

    def get_recently_enrolled_course(self, email):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            query = """SELECT e.code, e.name, e.unique_code, c.description, ep.amount_paid
                       FROM enrollment e 
                       JOIN courses c ON e.code = c.code 
                       LEFT JOIN enrollment_payment ep ON e.payment_id = ep.payment_id
                       WHERE e.email = %s 
                       AND (ep.payment_status IN ('Paid', 'FREE') OR ep.payment_status IS NULL)
                       ORDER BY e.enrollment_date DESC LIMIT 1"""
            cursor.execute(query, (email,))
            result = cursor.fetchone()
            return result
        except Exception as e: 
            logger.error(f"DB Error getting recently enrolled course for {email}: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def log_enrollment_payment(self, enrollment_id, email, username, course_code, amount_paid, payment_id, razorpay_order_id, payment_method, payment_status):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor()
            query = """
                INSERT INTO enrollment_payment 
                (enrollment_id, user_email, user_username, course_code, amount_paid, payment_id, razorpay_order_id, payment_method, payment_status) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (enrollment_id, email, username, course_code, amount_paid, payment_id, razorpay_order_id, payment_method, payment_status))
            db.commit()
            logger.info(f"DB: Enrollment payment logged for user {email} (ID: {payment_id})")
            return True
        except Exception as e:
            logger.critical(f"DB Error logging enrollment payment for {email} (payment_id={payment_id}): {e}")
            if db: db.rollback()
            return False
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def update_enrollment_payment_status(self, payment_id, status, razorpay_payment_id=None, method=None):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor()
            now = datetime.now()
            
            update_ep_query = """
                UPDATE enrollment_payment 
                SET payment_status = %s, payment_method = %s, completion_date = %s, razorpay_payment_id = %s
                WHERE payment_id = %s
            """
            
            cursor.execute(update_ep_query, (status, method, now, razorpay_payment_id, payment_id))
            
            select_ep_query = "SELECT enrollment_id FROM enrollment_payment WHERE payment_id = %s"
            cursor.execute(select_ep_query, (payment_id,))
            result = cursor.fetchone()
            enrollment_id = result[0] if result else None
            
            if enrollment_id and status in ('Paid', 'FREE'):
                final_payment_id = razorpay_payment_id if status == 'Paid' and razorpay_payment_id else payment_id
                update_e_query = "UPDATE enrollment SET payment_id = %s WHERE id = %s"
                cursor.execute(update_e_query, (final_payment_id, enrollment_id))

            db.commit()
            logger.info(f"DB: Enrollment payment status updated for {payment_id} to {status}. RZP ID: {razorpay_payment_id}")
        except Exception as e:
            logger.error(f"DB Error updating enrollment payment status for {payment_id}: {e}")
            if db: db.rollback()
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def update_enrollment_unique_code(self, temp_payment_id, unique_code):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor()
            
            select_ep_query = "SELECT enrollment_id FROM enrollment_payment WHERE payment_id = %s"
            cursor.execute(select_ep_query, (temp_payment_id,))
            result = cursor.fetchone()
            enrollment_id = result[0] if result else None

            if enrollment_id:
                update_e_query = "UPDATE enrollment SET unique_code = %s WHERE id = %s"
                cursor.execute(update_e_query, (unique_code, enrollment_id))
                db.commit()
                logger.info(f"DB: Final unique code set for enrollment ID {enrollment_id} using temp ID {temp_payment_id}.")
            else:
                logger.warning(f"DB: Failed to find enrollment_id for temp payment ID {temp_payment_id} to set unique code.")
        except Exception as e:
            logger.error(f"DB Error updating final unique code for {temp_payment_id}: {e}")
            if db: db.rollback()
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def get_enrollment_details_by_payment_id(self, payment_id):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            query = """
                SELECT 
                    ep.user_email, ep.user_username, ep.course_code, ep.amount_paid, ep.payment_id,
                    e.name AS course_name, e.unique_code, ep.payment_status
                FROM enrollment_payment ep
                JOIN enrollment e ON ep.enrollment_id = e.id
                WHERE ep.razorpay_payment_id = %s OR ep.payment_id = %s
            """
            cursor.execute(query, (payment_id, payment_id))
            result = cursor.fetchone()
            logger.info(f"DB: Fetched enrollment details by payment_id {payment_id}")
            return result
        except Exception as e:
            logger.error(f"DB Error getting enrollment details by payment_id {payment_id}: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def is_course_purchased_securely(self, email, course_code, title, subtitle):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            query = """
                SELECT 1 FROM purchase
                WHERE email = %s AND course_code = %s AND title = %s
                  AND COALESCE(subtitle, '') = COALESCE(%s, '') AND status = 'Paid'
            """
            cursor.execute(query, (email, course_code, title, subtitle))
            is_purchased = cursor.fetchone() is not None
            return is_purchased
        except Exception as e:
            logger.error(f"DB Error checking purchase status for {email}: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if db: db.close()