import datetime
import logging
import mysql.connector
from config import Config
from db_pool import get_connection

logger = logging.getLogger(__name__)

class UserOperation:
    def connection(self):
        return get_connection()

    def fetch_one(self, query, params=None):
        db = self.connection()
        cursor = db.cursor(dictionary=True, buffered=True)
        try:
            cursor.execute(query, params or ())
            return cursor.fetchone()
        finally:
            cursor.close()
            db.close()

    def fetch_all(self, query, params=None):
        db = self.connection()
        cursor = db.cursor(dictionary=True, buffered=True)
        try:
            cursor.execute(query, params or ())
            return cursor.fetchall()
        finally:
            cursor.close()
            db.close()

    def execute_query(self, query, params=None):
        db = self.connection()
        cursor = db.cursor(buffered=True)
        try:
            cursor.execute(query, params or ())
            db.commit()
        finally:
            cursor.close()
            db.close()

    def get_user_unique_code(self, email, course_code):
        try:
            query = "SELECT unique_code FROM enrollment WHERE email = %s AND code = %s"
            result = self.fetch_one(query, (email, course_code))
            return result['unique_code'] if result else None
        except Exception as e:
            logger.exception("Error fetching user unique code")
            return None

    def get_user_by_email(self, email):
        try:
            query = "SELECT username FROM auth WHERE email = %s"
            return self.fetch_one(query, (email,))
        except Exception as e:
            logger.exception("Error fetching user by email")
            return None

    def validate_test_credentials(self, test_key, submitted_key):
        try:
            query = "SELECT id FROM test_description WHERE test_key = %s AND test_key = %s"
            result = self.fetch_one(query, (test_key, submitted_key))
            return result is not None
        except Exception as e:
            logger.exception(f"Error validating credentials for test_key {test_key}")
            return False

    def check_test_already_taken(self, email, test_key):
        try:
            query = "SELECT id FROM user_test_log WHERE email = %s AND test_key = %s AND status = 'completed'"
            result = self.fetch_one(query, (email, test_key))
            return result is not None
        except Exception as e:
            logger.exception(f"Error checking if test {test_key} was taken by {email}")
            return False

    def get_test_status_for_user(self, email, test_key):
        try:
            query = ("SELECT status, start_time, attempt_number, last_heartbeat FROM user_test_log "
                     "WHERE email = %s AND test_key = %s ORDER BY (status = 'completed') DESC, attempt_number DESC LIMIT 1")
            result = self.fetch_one(query, (email, test_key))
            return result if result else {'status': 'not_started', 'start_time': None, 'attempt_number': 0, 'last_heartbeat': None}
        except Exception as e:
            logger.exception(f"Error fetching test status for user {email}, test_key {test_key}")
            return {'status': 'not_started', 'start_time': None, 'attempt_number': 0, 'last_heartbeat': None}

    def get_last_attempt_number(self, email, test_key):
        try:
            query = "SELECT MAX(attempt_number) AS last_attempt FROM user_test_log WHERE email = %s AND test_key = %s"
            result = self.fetch_one(query, (email, test_key))
            return result['last_attempt'] if result and result['last_attempt'] is not None else 0
        except Exception as e:
            logger.exception(f"Error fetching last attempt number for user {email}, test_key {test_key}")
            return 0

    def store_user_test_start(self, email, test_key, username, is_checkbox_checked=False, ready_to_begin=False):
        try:
            test_info = self.get_test_details(test_key)
            if not test_info:
                raise Exception("Test details not found for storing log.")

            finished = self.fetch_one(
                "SELECT id FROM user_test_log WHERE email = %s AND test_key = %s AND status = 'completed' LIMIT 1",
                (email, test_key)
            )
            if finished:
                logger.warning(f"Start refused for {email} on {test_key}: the test is already submitted.")
                return None

            existing_unperformed_test = self.fetch_one(
                "SELECT id, attempt_number FROM user_test_log WHERE email = %s AND test_key = %s AND status = 'unperformed' ORDER BY attempt_number DESC LIMIT 1",
                (email, test_key)
            )
            
            if existing_unperformed_test:
                attempt_number = existing_unperformed_test['attempt_number']
                query = """
                    UPDATE user_test_log SET start_time = NOW(), is_checkbox_checked = %s, ready_to_begin = %s, accepted_at = NOW(), updated_at = CURRENT_TIMESTAMP
                    WHERE email = %s AND test_key = %s AND status = 'unperformed' AND id = %s
                """
                self.execute_query(query, (int(is_checkbox_checked), int(ready_to_begin), email, test_key, existing_unperformed_test['id']))
                return attempt_number
            else:
                last_attempt = self.get_last_attempt_number(email, test_key)
                new_attempt_number = last_attempt + 1
                query = """
                    INSERT INTO user_test_log (email, test_id, test_key, username, start_time, status, attempt_number, is_checkbox_checked, ready_to_begin, accepted_at)
                    VALUES (%s, %s, %s, %s, NOW(), 'unperformed', %s, %s, %s, NOW())
                """
                try:
                    self.execute_query(query, (email, test_info['test_id'], test_key, username, new_attempt_number, int(is_checkbox_checked), int(ready_to_begin)))
                except mysql.connector.Error as err:
                    if getattr(err, 'errno', None) != 1062:
                        raise
                    twin = self.fetch_one(
                        "SELECT attempt_number FROM user_test_log WHERE email = %s AND test_key = %s "
                        "AND attempt_number = %s", (email, test_key, new_attempt_number))
                    logger.info(f"Concurrent start for {email} on {test_key}: reusing attempt {new_attempt_number}")
                    return twin['attempt_number'] if twin else new_attempt_number
                return new_attempt_number
        except Exception as e:
            logger.exception(f"Error storing/updating test log for user {email}, test_key {test_key}")
            return None

    def set_test_status_in_progress(self, email, test_key, attempt_number):
        try:
            query = """
                UPDATE user_test_log SET status = 'in_progress', start_time = NOW(), last_heartbeat = NOW(), updated_at = CURRENT_TIMESTAMP
                WHERE email = %s AND test_key = %s AND attempt_number = %s AND status = 'unperformed'
            """
            self.execute_query(query, (email, test_key, attempt_number))
            logger.info(f"Set test {test_key} to 'in_progress' for user {email}, attempt {attempt_number}")
        except Exception as e:
            logger.exception(f"Failed to set test status to 'in_progress' for {email}, {test_key}")

    def update_test_heartbeat(self, email, test_key, attempt_number):
        try:
            query = """
                UPDATE user_test_log SET last_heartbeat = NOW()
                WHERE email = %s AND test_key = %s AND attempt_number = %s AND status = 'in_progress'
            """
            self.execute_query(query, (email, test_key, attempt_number))
        except Exception as e:
            logger.exception(f"Failed to update heartbeat for {email}, {test_key}")

    def complete_user_test(self, email, test_key, device_info, attempt_number=1):
        try:
            query = """
                UPDATE user_test_log SET status = 'completed', end_time = NOW(), device_info = %s
                WHERE email = %s AND test_key = %s AND status = 'in_progress' AND attempt_number = %s
            """
            self.execute_query(query, (device_info, email, test_key, attempt_number))
        except Exception as e:
            logger.exception(f"Failed to update test completion for {email}, test {test_key}")

    def get_test_details(self, test_key):
        try:
            query = """
                SELECT test_id, test_key, subject_title, subject_subtitle,
                       total_questions, total_marks, total_duration_minutes, show_calculator
                FROM test_description
                WHERE test_key = %s
            """
            return self.fetch_one(query, (test_key,))
        except Exception as e:
            logger.exception(f"Error fetching test details for test_key: {test_key}")
            return None

    def get_all_test_questions(self, test_key):
        try:
            query = """
                SELECT id, test_id, test_key, section_id, section_name, question_number, question_type,
                       question_text, question_image, option_regions,
                       option_a, option_b, option_c, option_d,
                       correct_option, correct_marks, negative_marks, question_level, answer_text, answer_link
                FROM test_questions
                WHERE test_key = %s
                ORDER BY section_id, question_number
            """
            return self.fetch_all(query, (test_key,))
        except Exception as e:
            logger.exception(f"Error fetching all questions for test_key: {test_key}")
            return []

    def set_question_flag(self, email, test_key, question_id, flagged, note, attempt_number=1):
        try:
            row = self.fetch_one(
                """SELECT id FROM test_attempt_details
                   WHERE email=%s AND test_key=%s AND question_id=%s AND attempt_number=%s""",
                (email, test_key, question_id, attempt_number))
            if row:
                self.execute_query(
                    """UPDATE test_attempt_details SET is_flagged=%s, flag_note=%s
                       WHERE id=%s""", (flagged, note or None, row['id']))
            else:
                test_id_row = self.fetch_one(
                    "SELECT test_id FROM test_questions WHERE id=%s LIMIT 1", (question_id,))
                self.execute_query(
                    """INSERT INTO test_attempt_details
                       (email, test_id, test_key, question_id, status_of_attempt,
                        is_flagged, flag_note, attempt_number)
                       VALUES (%s, %s, %s, %s, 'not_answered', %s, %s, %s)""",
                    (email, (test_id_row or {}).get('test_id'), test_key, question_id,
                     flagged, note or None, attempt_number))
            return True
        except Exception:
            logger.exception(f"Failed setting flag for {email}, {test_key}, q={question_id}")
            return False

    def get_course_info_by_test_id(self, test_id):
        try:
            query = "SELECT code, stream, name FROM course_content WHERE section_id = %s"
            result = self.fetch_one(query, (test_id,))
            return result if result else None
        except Exception as e:
            logger.exception(f"Error fetching course info for test_id: {test_id}")
            return None

    def get_test_sections(self, test_key):
        try:
            query = """
                SELECT section_id, section_name,
                       SUM(CASE WHEN correct_marks = 1 THEN 1 ELSE 0 END) AS one_mark_questions,
                       SUM(CASE WHEN correct_marks = 2 THEN 1 ELSE 0 END) AS two_mark_questions,
                       SUM(correct_marks) AS section_total_marks
                FROM test_questions WHERE test_key = %s GROUP BY section_id, section_name ORDER BY section_id
            """
            return self.fetch_all(query, (test_key,))
        except Exception as e:
            logger.exception(f"Error fetching sections for test_key: {test_key}")
            return []

    def terminate_user_test_log(self, email, test_key, attempt_number):
        try:
            query = """
                UPDATE user_test_log SET status = 'unperformed', end_time = NOW() 
                WHERE email = %s AND test_key = %s AND status = 'in_progress' AND attempt_number = %s
            """
            self.execute_query(query, (email, test_key, attempt_number))
            logger.info(f"Terminated (reset to unperformed) test log for {email}, {test_key}, attempt {attempt_number}")
        except Exception as e:
            logger.exception(f"Failed to terminate test log for {email}, {test_key}")

    def get_completed_tests_for_user(self, email, section_id):
        try:
            query = """
                SELECT 
                    tr.test_id, 
                    td.test_key, 
                    td.subject_title, 
                    td.subject_subtitle,
                    tr.submission_timestamp, 
                    tr.net_score, 
                    tr.percentage
                FROM test_result tr
                JOIN test_description td ON tr.test_key = td.test_key
                WHERE tr.email = %s AND td.test_id = %s
                ORDER BY tr.submission_timestamp DESC
            """
            return self.fetch_all(query, (email, section_id))
        except Exception as e:
            logger.exception(f"Error fetching completed tests for user {email} and section {section_id}")
            return []

    def get_course_code_from_test_id(self, test_id):
        try:
            query = "SELECT code,stream,name  FROM course_content WHERE section_id = %s"
            result = self.fetch_one(query, (test_id,))
            return result['code'] if result else None
        except Exception as e:
            logger.exception(f"Error fetching course code for test_id: {test_id}")
            return None

    def update_email_for_guest_data(self, guest_email, actual_email, actual_username):
        try:
            query_log = "UPDATE user_test_log SET email = %s, username = %s WHERE email = %s"
            self.execute_query(query_log, (actual_email, actual_username, guest_email))
            logger.info(f"USER_DB: Updated email in user_test_log from {guest_email} to {actual_email}")
        except Exception as e:
            logger.exception(f"Failed to update email in user_test_log for guest {guest_email}")

    def remove_user_data(self, email):
        try:
            db_connection = self.connection()
            cursor = db_connection.cursor(buffered=True)
            db_connection.start_transaction()
            cursor.execute("DELETE FROM user_test_log WHERE email = %s", (email,))
            cursor.execute("DELETE FROM test_attempt_details WHERE email = %s", (email,))
            cursor.execute("DELETE FROM test_result WHERE email = %s", (email,))
            cursor.execute("DELETE FROM test_feedback WHERE email = %s", (email,))
            db_connection.commit()
            logger.info(f"USER_DB: Removed all data for user {email}")
        except Exception as e:
            db_connection.rollback()
            logger.exception(f"Failed to remove user data for {email}")
        finally:
            if db_connection:
                db_connection.close()

    def remove_guest_data(self, guest_email):
        try:
            db_connection = self.connection()
            cursor = db_connection.cursor(buffered=True)
            db_connection.start_transaction()
            cursor.execute("DELETE FROM user_test_log WHERE email = %s", (guest_email,))
            cursor.execute("DELETE FROM test_attempt_details WHERE email = %s", (guest_email,))
            cursor.execute("DELETE FROM test_result WHERE email = %s", (guest_email,))
            cursor.execute("DELETE FROM test_feedback WHERE email = %s", (guest_email,))
            db_connection.commit()
            logger.info(f"USER_DB: Removed all data for guest user {guest_email}")
        except Exception as e:
            db_connection.rollback()
            logger.exception(f"Failed to remove guest data for {guest_email}")
        finally:
            if db_connection:
                db_connection.close()
    
    def remove_expired_guest_data(self):
        try:
            db = self.connection()
            cursor = db.cursor()
            
            cutoff_time = datetime.now() - datetime.timedelta(hours=3)
            
            query = "SELECT email FROM user_test_log WHERE email LIKE 'guest_%' AND start_time < %s"
            cursor.execute(query, (cutoff_time,))
            guest_emails_to_delete = [row[0] for row in cursor.fetchall()]
            
            if guest_emails_to_delete:
                for email in guest_emails_to_delete:
                    self.remove_guest_data(email)
                logger.info(f"Removed {len(guest_emails_to_delete)} expired guest records.")
            else:
                logger.info("No expired guest records found for removal.")
            
        except Exception as e:
            logger.exception("An error occurred during expired guest data cleanup.")
        finally:
            if 'cursor' in locals() and cursor:
                try: cursor.close()
                except Exception: pass
            if 'db' in locals() and db:
                try: db.close()
                except Exception: pass

