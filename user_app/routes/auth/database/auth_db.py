import mysql.connector
from mysql.connector import Error
from config import Config
from contextlib import contextmanager
import logging
import json

logger = logging.getLogger(__name__)

class AuthOperation:

    @contextmanager
    def connection(self):
        """A pooled connection.

        This layer used to open a brand new connection for every call, so the
        hottest paths in the app - login, signup checks, update_last_active -
        each paid a full connect and teardown while the rest of the app used
        the pool. Closing a pooled connection returns it to the pool, so the
        surrounding code does not change.
        """
        conn = None
        try:
            from routes.db_pool import get_connection
            conn = get_connection()
            yield conn
        except Error as e:
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            if conn:
                try: conn.close()
                except Exception: pass

    def get_user_by_email(self, email):
        try:
            with self.connection() as db:
                cursor = db.cursor(dictionary=True, buffered=True)
                query = "SELECT * FROM auth WHERE email = %s"
                cursor.execute(query, (email,))
                return cursor.fetchone()
        except Exception:
            logger.exception("Error fetching user by email")
            raise

    # ------------------------------------------------- pending signup
    PENDING_FIELDS = ('username', 'email', 'password_hash',
                      'otp_hash', 'otp_expires_at', 'otp_attempts')

    def get_pending_signup(self, token):
        with self.connection() as db:
            cursor = db.cursor(dictionary=True, buffered=True)
            cursor.execute("SELECT * FROM pending_signups WHERE token = %s", (token,))
            return cursor.fetchone()

    def upsert_pending_signup(self, token, **fields):
        """Create or update the row, touching only the fields supplied."""
        data = {k: v for k, v in fields.items() if k in self.PENDING_FIELDS}
        cols = ['token'] + list(data)
        marks = ', '.join(['%s'] * len(cols))
        updates = ', '.join(f"{c} = VALUES({c})" for c in data) or 'token = token'
        with self.connection() as db:
            cursor = db.cursor()
            cursor.execute(
                f"INSERT INTO pending_signups ({', '.join(cols)}) VALUES ({marks}) "
                f"ON DUPLICATE KEY UPDATE {updates}",
                tuple([token] + list(data.values())))
            db.commit()

    def bump_otp_attempts(self, token):
        with self.connection() as db:
            cursor = db.cursor()
            cursor.execute("UPDATE pending_signups SET otp_attempts = otp_attempts + 1 "
                           "WHERE token = %s", (token,))
            db.commit()

    def delete_pending_signup(self, token):
        with self.connection() as db:
            cursor = db.cursor()
            cursor.execute("DELETE FROM pending_signups WHERE token = %s", (token,))
            db.commit()

    # ------------------------------------------------------------ lockout
    # Shared storage so a failed-login counter cannot be reset by throwing
    # away a cookie. Mirrors the admin app's table.
    def is_locked_out(self, identifier):
        with self.connection() as db:
            cursor = db.cursor()
            cursor.execute(
                "SELECT 1 FROM user_login_attempts "
                "WHERE identifier = %s AND locked_until IS NOT NULL AND locked_until > NOW() "
                "LIMIT 1", (identifier,))
            return cursor.fetchone() is not None

    def register_failed_attempt(self, identifier, limit, lockout_seconds):
        with self.connection() as db:
            cursor = db.cursor()
            cursor.execute(
                """
                INSERT INTO user_login_attempts (identifier, attempts, last_attempt_at)
                VALUES (%s, 1, NOW())
                ON DUPLICATE KEY UPDATE
                    attempts = IF(locked_until IS NOT NULL AND locked_until <= NOW(), 1, attempts + 1),
                    last_attempt_at = NOW(),
                    locked_until = IF(locked_until IS NOT NULL AND locked_until <= NOW(), NULL, locked_until)
                """, (identifier,))
            cursor.execute(
                "UPDATE user_login_attempts "
                "SET locked_until = DATE_ADD(NOW(), INTERVAL %s SECOND) "
                "WHERE identifier = %s AND attempts >= %s "
                "  AND (locked_until IS NULL OR locked_until <= NOW())",
                (lockout_seconds, identifier, limit))
            db.commit()

    def clear_attempts(self, identifier):
        with self.connection() as db:
            cursor = db.cursor()
            cursor.execute("DELETE FROM user_login_attempts WHERE identifier = %s", (identifier,))
            db.commit()

    def is_username_taken(self, username):
        try:
            with self.connection() as db:
                cursor = db.cursor()
                query = "SELECT 1 FROM auth WHERE username = %s LIMIT 1"
                cursor.execute(query, (username,))
                return cursor.fetchone() is not None
        except Exception:
            # Reporting "not taken" on a database error let signup continue and
            # create a duplicate username. Fail closed: the caller treats this
            # as taken and asks for another name.
            logger.exception(f"Error checking username {username}")
            raise

    def update_username(self, email, new_username):
        try:
            with self.connection() as db:
                cursor = db.cursor()
                query = "UPDATE auth SET username = %s WHERE email = %s"
                cursor.execute(query, (new_username, email))
                db.commit()
        except Exception:
            logger.exception(f"Error updating username for {email}")
            raise

    def update_user_password(self, email, new_password):
        try:
            with self.connection() as db:
                cursor = db.cursor()
                query = "UPDATE auth SET password = %s WHERE email = %s"
                cursor.execute(query, (new_password, email))
                db.commit()
        except Exception:
            logger.exception("Error updating password")
            raise

    def set_user_password(self, email, hashed_password):
        self.update_user_password(email, hashed_password)

    def insert_user_google(self, username, email, oauth_id):
        try:
            with self.connection() as db:
                cursor = db.cursor(buffered=True)
                query = "INSERT INTO auth (username, email, oauth_id, auth_type, is_verified) VALUES (%s, %s, %s, 'google', TRUE)"
                cursor.execute(query, (username, email, oauth_id))
                db.commit()
        except Exception:
            logger.exception("Error inserting Google user")
            raise

    def user_signup_insert(self, username, password, email, is_verified=False):
        try:
            with self.connection() as db:
                cursor = db.cursor(buffered=True)
                query = "INSERT INTO auth (username, password, email, is_verified, auth_type) VALUES (%s, %s, %s, %s, 'manual')"
                cursor.execute(query, (username, password, email, is_verified))
                db.commit()
        except Exception:
            logger.exception("Error inserting manual signup user")
            raise
    
    def update_auth_type_to_both(self, email, oauth_id):
        try:
            with self.connection() as conn:
                cursor = conn.cursor(buffered=True)
                query = "UPDATE auth SET auth_type = 'both', oauth_id = %s WHERE email = %s"
                cursor.execute(query, (oauth_id, email))
                conn.commit()
                return True
        except Exception:
            logger.exception(f"Error updating auth_type to 'both' for email: {email}")
            return False

    def update_last_active(self, email):
        try:
            with self.connection() as db:
                cursor = db.cursor()
                query = "UPDATE auth SET last_active = NOW() WHERE email = %s"
                cursor.execute(query, (email,))
                db.commit()
        except Exception:
            pass

    def update_cookie_consent(self, email, consent_data):
        try:
            with self.connection() as db:
                cursor = db.cursor()
                consent_json = json.dumps(consent_data)
                query = "UPDATE auth SET cookie_consent = %s WHERE email = %s"
                cursor.execute(query, (consent_json, email))
                db.commit()
        except Exception as e:
            logger.warning(f"DB: Failed to update cookie consent for {email}. Error: {e}")

    def get_cookie_consent(self, email):
        try:
            with self.connection() as db:
                cursor = db.cursor(dictionary=True)
                query = "SELECT cookie_consent FROM auth WHERE email = %s"
                cursor.execute(query, (email,))
                result = cursor.fetchone()
                
                if result and result.get('cookie_consent'):
                    if isinstance(result['cookie_consent'], dict):
                        return result['cookie_consent']
                    if isinstance(result['cookie_consent'], str):
                        return json.loads(result['cookie_consent'])
                    return result['cookie_consent']
                return None
        except Exception as e:
            logger.error(f"DB: Error fetching cookie consent: {e}")
            return None