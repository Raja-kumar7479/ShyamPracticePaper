import logging
import mysql.connector
from mysql.connector import Error
from config import Config
from db_pool import get_connection

logger = logging.getLogger(__name__)

class ContentOperation:
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

    def get_note_access_level(self, file_path):
        query = """
            SELECT cc.label
            FROM notes_content nc
            JOIN course_content cc ON nc.test_id = cc.section_id
            WHERE nc.file_path = %s
            LIMIT 1
        """
        result = self.fetch_one(query, (file_path,))
        return result['label'] if result else 'Paid'

    def get_note_course_and_label(self, file_path):
        query = """
            SELECT cc.code, cc.label, cc.section_id,
                   COALESCE(nc.access_label, 'free') AS access_label
            FROM notes_content nc
            JOIN course_content cc ON nc.test_id = cc.section_id
            WHERE nc.file_path = %s
            LIMIT 1
        """
        return self.fetch_one(query, (file_path,))

    def get_user_unique_code(self, email, course_code):
        query = "SELECT unique_code FROM enrollment WHERE email = %s AND code = %s"
        result = self.fetch_one(query, (email, course_code))
        return result['unique_code'] if result else None

    def get_course_section_details(self, section_id):
        query = "SELECT label, title FROM course_content WHERE section_id = %s LIMIT 1"
        return self.fetch_one(query, (section_id,))

    def get_mock_tests_paid(self, section_id, course_code, user_email):
        query = """
            SELECT
                c.name AS course_name, c.stream, c.label, c.code,
                td_desc.test_id, td_desc.test_key,
                td_desc.subject_title, td_desc.subject_subtitle,
                td_desc.total_questions, td_desc.total_marks,
                td_desc.total_duration_minutes,
                COALESCE(td_desc.access_label, 'inherit') AS access_label,
                td_desc.created_at, td_desc.updated_at,
                COALESCE(utl.status, 'not_started') AS user_test_status,
                utl.attempt_number
            FROM course_content c
            JOIN test_description td_desc ON c.section_id = td_desc.test_id
            LEFT JOIN user_test_log utl ON utl.id = (
                SELECT latest.id FROM user_test_log latest
                WHERE latest.test_key = td_desc.test_key AND latest.email = %s
                ORDER BY (latest.status = 'completed') DESC, latest.attempt_number DESC LIMIT 1)
            WHERE c.section_id = %s AND c.code = %s AND c.label = 'Paid'
            ORDER BY td_desc.id
        """
        return self.fetch_all(query, (user_email, section_id, course_code))

    def get_mock_tests_free(self, section_id, course_code, user_email):
        query = """
            SELECT
                c.name AS course_name, c.stream, c.label, c.code,
                td_desc.test_id, td_desc.test_key,
                td_desc.subject_title, td_desc.subject_subtitle,
                td_desc.total_questions, td_desc.total_marks,
                td_desc.total_duration_minutes,
                COALESCE(td_desc.access_label, 'inherit') AS access_label,
                td_desc.created_at, td_desc.updated_at,
                COALESCE(utl.status, 'not_started') AS user_test_status,
                utl.attempt_number
            FROM course_content c
            JOIN test_description td_desc ON c.section_id = td_desc.test_id
            LEFT JOIN user_test_log utl ON utl.id = (
                SELECT latest.id FROM user_test_log latest
                WHERE latest.test_key = td_desc.test_key AND latest.email = %s
                ORDER BY (latest.status = 'completed') DESC, latest.attempt_number DESC LIMIT 1)
            WHERE c.section_id = %s AND c.code = %s AND c.label = 'Free'
            ORDER BY td_desc.id
        """
        return self.fetch_all(query, (user_email, section_id, course_code))

    def get_random_free_mock_tests(self, section_id, course_code, limit=6):
        query = """
            SELECT
                c.name AS course_name, c.stream, c.label, c.code,
                td_desc.test_id, td_desc.test_key,
                td_desc.subject_title, td_desc.subject_subtitle,
                td_desc.total_questions, td_desc.total_marks,
                td_desc.total_duration_minutes,
                td_desc.created_at, td_desc.updated_at,
                'not_started' AS user_test_status,
                0 AS attempt_number
            FROM course_content c
            JOIN test_description td_desc ON c.section_id = td_desc.test_id
            WHERE c.section_id = %s AND c.code = %s AND c.label = 'Free'
            ORDER BY RAND()
            LIMIT %s
        """
        return self.fetch_all(query, (section_id, course_code, limit))

    def get_course_info_from_section(self, section_id):
        query = "SELECT name, stream FROM course_content WHERE section_id = %s"
        return self.fetch_one(query, (section_id,))

    def get_notes_for_display(self, test_id):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT * FROM notes_content
                WHERE test_id = %s
                ORDER BY type, heading, sub_heading, title, sub_title
            """
            cursor.execute(query, (test_id,))
            return cursor.fetchall()
        except Error as e:
            logger.error(f"Error fetching notes for display for test_id={test_id}: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conn:
                try: conn.close()
                except Exception: pass

    def get_random_free_notes(self, section_id, limit=5):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT * FROM notes_content
                WHERE test_id = %s
                ORDER BY RAND()
                LIMIT %s
            """
            cursor.execute(query, (section_id, limit))
            return cursor.fetchall()
        except Error as e:
            logger.error(f"Error fetching random free notes for test_id={section_id}: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conn:
                try: conn.close()
                except Exception: pass

    def get_section_label(self, section_id):
        query = "SELECT label FROM course_content WHERE section_id = %s"
        result = self.fetch_one(query, (section_id,))
        return result['label'] if result else None

    def is_section_purchased(self, email, section_id):
        query = """
            SELECT 1 FROM purchase p
            JOIN course_content cc ON cc.section_id = %s
            WHERE p.email = %s AND p.status = 'Paid'
              AND (p.section_id = cc.section_id OR (p.course_code = cc.code AND p.title = cc.title))
            LIMIT 1
        """
        return self.fetch_one(query, (section_id, email)) is not None

    def get_locked_paid_mock_sections(self, course_code, email):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT cc.section_id, cc.title, cc.subtitle, cc.price, cc.discount,
                       cc.image_url, cc.details,
                       (SELECT COUNT(*) FROM test_description td
                         WHERE td.test_id = cc.section_id) AS test_count
                FROM course_content cc
                WHERE cc.code = %s
                  AND cc.section = 'mock_test'
                  AND cc.label = 'Paid'
                  AND cc.status = 'active'
                  AND NOT EXISTS (
                        SELECT 1 FROM purchase p
                         WHERE p.email = %s
                           AND p.status = 'Paid'
                           AND (p.section_id = cc.section_id
                                OR (p.course_code = cc.code AND p.title = cc.title))
                  )
                ORDER BY cc.created_at DESC
            """
            cursor.execute(query, (course_code, email))
            rows = cursor.fetchall()
            logger.info(f"CONTENT_DB: {len(rows)} locked paid mock section(s) for {course_code}")
            return rows
        except mysql.connector.Error as e:
            logger.exception(f"CONTENT_DB: failed fetching locked paid mock sections for {course_code}")
            return []
        finally:
            if cursor: cursor.close()
            if conn:
                try: conn.close()
                except Exception: pass

    def get_test_access_label(self, test_key):
        query = "SELECT COALESCE(access_label, 'inherit') AS access_label FROM test_description WHERE test_key = %s"
        row = self.fetch_one(query, (test_key,))
        return row['access_label'] if row else 'inherit'
