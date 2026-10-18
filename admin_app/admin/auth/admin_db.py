import mysql.connector
from mysql.connector import Error
from config import Config
import logging
from contextlib import contextmanager


logger = logging.getLogger(__name__)


class UserOperation:

    def connection(self):
        from admin.db_pool import get_connection
        return get_connection()

    @contextmanager
    def db_cursor(self):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(buffered=True)
            yield db, cursor
        except Error as e:
            logging.error(f"MySQL error: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
            if db and db.is_connected():
                db.close()
                logging.info("Database connection closed.")

    def get_admin_by_email(self, email):
        try:
            with self.db_cursor() as (db, cursor):
                cursor.execute("SELECT id, username, email, password, role FROM auth_admin WHERE email = %s", (email,))
                result = cursor.fetchone()
                logging.info(f"Fetched admin for email: {email}")
                return result
        except Exception as e:
            logging.error(f"Error fetching admin by email: {e}")
            return None

    def get_admin_auth_state(self, email):
        with self.db_cursor() as (db, cursor):
            cursor.execute("SELECT password FROM auth_admin WHERE email = %s", (email,))
            row = cursor.fetchone()
            if not row:
                return False, None
            return True, row[0]

    def set_admin_password(self, email, hashed_password):
        if not hashed_password:
            logging.error(f"Refusing to store an empty password hash for admin: {email}")
            return False
        try:
            with self.db_cursor() as (db, cursor):
                cursor.execute("UPDATE auth_admin SET password = %s WHERE email = %s", (hashed_password, email))
                db.commit()
                updated = cursor.rowcount > 0
                if updated:
                    logging.info(f"Password updated for admin: {email}")
                else:
                    logging.error(f"No admin row updated when setting password for: {email}")
                return updated
        except Exception as e:
            logging.error(f"Error updating password for admin: {e}")
            return False

    def is_locked_out(self, identifier):
        with self.db_cursor() as (db, cursor):
            cursor.execute(
                "SELECT locked_until FROM admin_login_attempts "
                "WHERE identifier = %s AND locked_until IS NOT NULL AND locked_until > NOW() LIMIT 1",
                (identifier,)
            )
            return cursor.fetchone() is not None

    def register_failed_attempt(self, identifier, limit, lockout_seconds):
        with self.db_cursor() as (db, cursor):
            cursor.execute(
                """
                INSERT INTO admin_login_attempts (identifier, attempts, last_attempt_at)
                VALUES (%s, 1, NOW())
                ON DUPLICATE KEY UPDATE
                    attempts = IF(locked_until IS NOT NULL AND locked_until <= NOW(), 1, attempts + 1),
                    last_attempt_at = NOW(),
                    locked_until = IF(locked_until IS NOT NULL AND locked_until <= NOW(), NULL, locked_until)
                """,
                (identifier,)
            )
            cursor.execute(
                "UPDATE admin_login_attempts SET locked_until = DATE_ADD(NOW(), INTERVAL %s SECOND) "
                "WHERE identifier = %s AND attempts >= %s AND (locked_until IS NULL OR locked_until <= NOW())",
                (lockout_seconds, identifier, limit)
            )
            db.commit()

    def clear_attempts(self, identifier):
        with self.db_cursor() as (db, cursor):
            cursor.execute("DELETE FROM admin_login_attempts WHERE identifier = %s", (identifier,))
            db.commit()

    def register_reset_request(self, identifier, limit, window_seconds, lockout_seconds):
        with self.db_cursor() as (db, cursor):
            cursor.execute(
                """
                INSERT INTO admin_login_attempts (identifier, attempts, last_attempt_at)
                VALUES (%s, 1, NOW())
                ON DUPLICATE KEY UPDATE
                    attempts = IF(
                        (locked_until IS NOT NULL AND locked_until <= NOW())
                        OR last_attempt_at < DATE_SUB(NOW(), INTERVAL %s SECOND),
                        1, attempts + 1),
                    last_attempt_at = NOW(),
                    locked_until = IF(attempts = 1, NULL, locked_until)
                """,
                (identifier, window_seconds)
            )
            cursor.execute(
                "UPDATE admin_login_attempts SET locked_until = DATE_ADD(NOW(), INTERVAL %s SECOND) "
                "WHERE identifier = %s AND attempts >= %s AND (locked_until IS NULL OR locked_until <= NOW())",
                (lockout_seconds, identifier, limit)
            )
            db.commit()
