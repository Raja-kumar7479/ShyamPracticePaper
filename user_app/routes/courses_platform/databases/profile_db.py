import os
import mysql.connector
from mysql.connector import Error
from config import Config
import logging

logger = logging.getLogger(__name__)

DELETION_TARGETS = [
    ('comm_proctoring_logs', 'email'),
    ('comm_attempt_details', 'email'),
    ('comm_user_log', 'email'),
    ('test_feedback', 'email'),
    ('test_attempt_details', 'email'),
    ('test_result', 'email'),
    ('user_test_log', 'email'),
    ('purchase', 'email'),
    ('enrollment_payment', 'user_email'),
    ('enrollment', 'email'),
    ('auth', 'email'),
]

MEDIA_TARGETS = [
    ('comm_proctoring_logs', 'email', 'snapshot_path'),
    ('comm_attempt_details', 'email', 'audio_response_path'),
]

class ProfileOperation:
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

    def get_user_details(self, email):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            query = "SELECT * FROM auth WHERE email = %s"
            cursor.execute(query, (email,))
            result = cursor.fetchone()
            return result
        except Exception as e:
            logger.error(f"DB Error getting user details for {email}: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def get_user_by_email(self, email):
        return self.get_user_details(email)

    def is_username_taken(self, username, exclude_email=None):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor()
            query = "SELECT 1 FROM auth WHERE username = %s AND email != %s LIMIT 1"
            cursor.execute(query, (username, exclude_email))
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"DB Error checking username {username}: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def update_username(self, email, new_username):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor()
            query = "UPDATE auth SET username = %s WHERE email = %s"
            cursor.execute(query, (new_username, email))
            db.commit()
            return True
        except Exception as e:
            logger.error(f"DB Error updating username for {email}: {e}")
            if db: db.rollback()
            raise e
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def update_user_password(self, email, hashed_password):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor()
            query = "UPDATE auth SET password = %s WHERE email = %s"
            cursor.execute(query, (hashed_password, email))
            db.commit()
            return True
        except Exception as e:
            logger.error(f"DB Error updating password for {email}: {e}")
            if db: db.rollback()
            raise e
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def set_user_password(self, email, hashed_password):
        return self.update_user_password(email, hashed_password)

    def update_last_active(self, email):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor()
            query = "UPDATE auth SET last_active = NOW() WHERE email = %s"
            cursor.execute(query, (email,))
            db.commit()
        except Exception as e:
            pass
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def get_last_active_time(self, email):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            query = "SELECT last_active FROM auth WHERE email = %s"
            cursor.execute(query, (email,))
            result = cursor.fetchone()
            return result['last_active'] if result else None
        except Exception:
            return None
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
            return result
        except Exception as e:
            logger.error(f"DB Error in get_enrolled_courses for {email}: {e}")
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

    def get_all_purchases(self, email):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            query = """
                SELECT p.*, cc.validity_expires_at FROM purchase AS p
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
            if db: db.close()

    def get_account_footprint(self, email):
        db = None
        cursor = None
        counts = {}
        try:
            db = self.connection()
            cursor = db.cursor()
            for table, column in DELETION_TARGETS:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} = %s", (email,))
                    row = cursor.fetchone()
                    counts[table] = int(row[0]) if row else 0
                except Error:
                    counts[table] = 0
            return counts
        except Error as e:
            logger.error(f"Error building account footprint for {email}: {e}")
            return counts
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def _collect_media_paths(self, cursor, email):
        paths = []
        for table, column, path_column in MEDIA_TARGETS:
            try:
                cursor.execute(f"SELECT {path_column} FROM {table} WHERE {column} = %s", (email,))
                for row in cursor.fetchall():
                    if row and row[0]:
                        paths.append(row[0])
            except Error as e:
                logger.warning(f"Could not read {path_column} from {table} for {email}: {e}")
        return paths

    def delete_account_completely(self, email):
        if not email:
            return False, {}

        db = None
        cursor = None
        deleted = {}
        media_paths = []

        try:
            logger.info(f"DELETE STEP 1: opening database connection for {email}.")
            db = self.connection()
            db.autocommit = False
            cursor = db.cursor(buffered=True)

            if not db.in_transaction:
                db.start_transaction()
            logger.info(f"DELETE STEP 2: transaction open for {email}.")

            media_paths = self._collect_media_paths(cursor, email)
            logger.info(f"DELETE STEP 3: found {len(media_paths)} media file(s) to remove for {email}.")

            for table, column in DELETION_TARGETS:
                try:
                    cursor.execute(f"DELETE FROM {table} WHERE {column} = %s", (email,))
                    deleted[table] = cursor.rowcount
                    logger.info(f"DELETE STEP 4: removed {cursor.rowcount} row(s) from {table} for {email}.")
                except Error as e:
                    if getattr(e, 'errno', None) == 1146:
                        logger.warning(f"DELETE STEP 4: table {table} does not exist; skipping for {email}.")
                        deleted[table] = 0
                        continue
                    logger.error(f"DELETE STEP 4 FAILED on table {table} for {email}: {e}", exc_info=True)
                    raise

            db.commit()
            logger.critical(f"DELETE STEP 5: committed. All data removed for {email}. Rows: {deleted}")
        except Error as e:
            if db:
                try:
                    db.rollback()
                    logger.error(f"DELETE ROLLBACK: transaction rolled back for {email}; nothing was removed.")
                except Error as rb:
                    logger.error(f"DELETE ROLLBACK FAILED for {email}: {rb}", exc_info=True)
            logger.error(f"DELETE FAILED for {email}. Error: {e}", exc_info=True)
            return False, {}
        except Exception as e:
            if db:
                try:
                    db.rollback()
                except Exception:
                    pass
            logger.error(f"DELETE FAILED (unexpected) for {email}. Error: {e}", exc_info=True)
            return False, {}
        finally:
            if cursor: cursor.close()
            if db:
                try: db.close()
                except Exception: pass

        removed_files = 0
        for path in media_paths:
            try:
                full_path = path if os.path.isabs(path) else os.path.join(Config.UPLOAD_BASE, path)
                if os.path.isfile(full_path):
                    os.remove(full_path)
                    removed_files += 1
            except OSError as e:
                logger.warning(f"DELETE STEP 6: could not delete media file {path} for {email}: {e}")
        logger.info(f"DELETE STEP 6: removed {removed_files}/{len(media_paths)} media file(s) for {email}.")

        return True, deleted