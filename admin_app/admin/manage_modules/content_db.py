import mysql.connector
from mysql.connector import Error
from config import Config
import logging
import uuid
import os
import secrets
from decimal import Decimal

logger = logging.getLogger(__name__)

SECTION_ID_PREFIX = {'paid': '1', 'free': '2'}
SECTION_ID_RANDOM_DIGITS = 11
SECTION_ID_MAX_TRIES = 12

class UserOperation:
    def connection(self):
        from admin.db_pool import get_connection
        return get_connection()


    def get_admin_by_email(self, email):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(buffered=True, dictionary=True)
            query = "SELECT * FROM auth_admin WHERE email = %s"
            cursor.execute(query, (email,))
            return cursor.fetchone()
        except Exception as e:
            logger.exception(f"Error fetching admin by email: {email}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def generate_unique_section_id(self, code, section, label):
        prefix = SECTION_ID_PREFIX.get((label or '').strip().lower(), SECTION_ID_PREFIX['free'])

        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(buffered=True)
            for attempt in range(SECTION_ID_MAX_TRIES):
                candidate = f"{prefix}{secrets.randbelow(10 ** SECTION_ID_RANDOM_DIGITS):0{SECTION_ID_RANDOM_DIGITS}d}"
                cursor.execute("SELECT 1 FROM course_content WHERE section_id = %s LIMIT 1", (candidate,))
                if cursor.fetchone() is None:
                    logger.info(f"SECTION ID: generated {candidate} for label={label!r} (attempt {attempt + 1})")
                    return candidate
                logger.warning(f"SECTION ID: collision on {candidate}; retrying.")
            raise RuntimeError("Could not generate a unique section ID after several attempts.")
        except Error as e:
            logger.exception(f"SECTION ID: database error while generating id: {e}")
            raise
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def insert_content(self, code, name, stream, title, subtitle, price, details, label, status, image_url,
                       section, _unused=None, discount=0,
                       syllabus_url=None, syllabus_position='below', syllabus_label=None,
                       max_test_descriptions=None):
        conn = None
        cursor = None
        try:
            section_id = self.generate_unique_section_id(code, section, label)
            logger.info(f"DB INSERT 1: section_id={section_id} for '{title}' ({label})")

            conn = self.connection()
            cursor = conn.cursor(buffered=True)
            query = """
                INSERT INTO course_content
                (code, name, stream, title, subtitle, price, discount, details, label, status, image_url, section,
                 section_id, syllabus_url, syllabus_position, syllabus_label,
                 max_test_descriptions)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            params = (code, name, stream, title, subtitle, price, discount, details, label, status, image_url, section,
                      section_id, syllabus_url, syllabus_position or 'below', syllabus_label,
                      max_test_descriptions)
            cursor.execute(query, params)
            conn.commit()
            logger.info(f"DB INSERT 2: content '{title}' saved with row id {cursor.lastrowid}, section_id {section_id}.")
            return cursor.lastrowid
        except Exception as e:
            logger.exception(f"Error inserting new content for code {code}. Error: {e}")
            if conn: conn.rollback()
            return None
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def update_content(self, content_id, name, stream, title, subtitle, price, details, label, status,
                       image_url, _unused=None, discount=0,
                       syllabus_url=None, syllabus_position='below', syllabus_label=None,
                       max_test_descriptions=None):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(buffered=True)
            query = """
                UPDATE course_content SET
                name = %s, stream = %s, title = %s, subtitle = %s, price = %s, discount = %s, details = %s,
                label = %s, status = %s, image_url = %s,
                syllabus_url = %s, syllabus_position = %s, syllabus_label = %s,
                max_test_descriptions = %s
                WHERE id = %s
            """
            params = (name, stream, title, subtitle, price, discount, details, label, status, image_url,
                      syllabus_url, syllabus_position or 'below', syllabus_label,
                      max_test_descriptions, content_id)
            cursor.execute(query, params)
            changed = cursor.rowcount
            conn.commit()

            if changed > 0:
                logger.info(f"DB UPDATE: content id={content_id} updated ({changed} row).")
                return True
            cursor.execute("SELECT 1 FROM course_content WHERE id = %s", (content_id,))
            if cursor.fetchone():
                logger.info(f"DB UPDATE: content id={content_id} already held these values; nothing to change.")
                return True
            logger.error(f"DB UPDATE FAILED: content id={content_id} does not exist.")
            return False
        except Exception as e:
            logger.exception(f"DB UPDATE ERROR: content id={content_id} could not be updated. Rolling back. Error: {e}")
            if conn: conn.rollback()
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def get_content_by_id(self, content_id):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            query = """
                SELECT cc.*,
                       (SELECT COUNT(*) FROM test_description td WHERE td.test_id = cc.section_id)
                     + (SELECT COUNT(*) FROM comm_description cd WHERE cd.test_id = cc.section_id) AS description_count
                FROM course_content cc WHERE cc.id = %s
            """
            cursor.execute(query, (content_id,))
            return cursor.fetchone()
        except Exception as e:
            logger.exception(f"Error fetching content with ID {content_id}. Error: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def get_courses_by_code(self, code):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            query = """
                SELECT cc.*, c.name AS course_name,
                       (SELECT COUNT(*) FROM test_description td WHERE td.test_id = cc.section_id)
                     + (SELECT COUNT(*) FROM comm_description cd WHERE cd.test_id = cc.section_id) AS description_count
                FROM course_content AS cc
                LEFT JOIN courses AS c ON cc.code = c.code
                WHERE cc.code = %s
                ORDER BY
                    FIELD(cc.section, 'notes', 'mock_test', 'coding_test',
                                      'communication_test', 'aptitude_test',
                                      'coding_practice', 'question_practice',
                                      'lecture', 'community', 'blog'),
                    FIELD(cc.label, 'Free', 'Paid'),
                    cc.created_at DESC
            """
            cursor.execute(query, (code,))
            rows = cursor.fetchall()
            logger.info(f"DB: fetched {len(rows)} content row(s) for code {code!r}")
            return rows
        except Exception as e:
            logger.exception(f"Error fetching course content for code '{code}'. Error: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def get_all_content(self):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            query = """
                SELECT cc.*, c.name AS course_name,
                       (SELECT COUNT(*) FROM test_description td WHERE td.test_id = cc.section_id)
                     + (SELECT COUNT(*) FROM comm_description cd WHERE cd.test_id = cc.section_id) AS description_count
                FROM course_content AS cc
                LEFT JOIN courses AS c ON cc.code = c.code
                ORDER BY cc.created_at DESC, cc.id DESC
            """
            cursor.execute(query)
            return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error fetching all course content. Error: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def paid_purchase_count(self, section_id):
        if not section_id:
            return 0
        conn = self.connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM purchase WHERE section_id = %s AND status = 'Paid'",
                        (section_id,))
            return cur.fetchone()[0]
        finally:
            cur.close()
            conn.close()

    def delete_content(self, content_id):
        content = self.get_content_by_id(content_id)
        if not content:
            return False

        section_id = content.get('section_id')

        work = self.student_activity_for_section(section_id)
        if work:
            logger.warning("DELETE CONTENT BLOCKED: content %s (section_id=%s) has student work: %s",
                           content_id, section_id, work)
            return 'has_attempts'

        if self.paid_purchase_count(section_id) > 0:
            logger.warning("DELETE CONTENT BLOCKED: content %s (section_id=%s) has paid "
                           "purchases; refusing hard delete", content_id, section_id)
            return 'has_purchases'

        conn = self.connection()
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("SELECT test_key FROM comm_description WHERE test_id = %s", (section_id,))
            keys = [r['test_key'] for r in cur.fetchall()]
            write = conn.cursor()
            for key in keys:
                write.execute("DELETE FROM cp_questions WHERE section_id IN (SELECT s.id FROM cp_sections s "
                              "JOIN cp_tests t ON t.id = s.test_id WHERE t.test_key = %s)", (key,))
                write.execute("DELETE FROM cp_sections WHERE test_id IN (SELECT id FROM cp_tests WHERE test_key = %s)", (key,))
                write.execute("DELETE FROM cp_tests WHERE test_key = %s", (key,))
            write.execute("DELETE FROM comm_description WHERE test_id = %s", (section_id,))
            write.execute("DELETE FROM test_description WHERE test_id = %s", (section_id,))
            write.execute("DELETE FROM course_content WHERE id = %s", (content_id,))
            rows = write.rowcount
            conn.commit()
            write.close()

            from admin.manage_modules.course_content import _remove_upload
            for stored in (content.get('image_url'), content.get('syllabus_url')):
                if stored:
                    _remove_upload(stored)
            logger.info("DELETE CONTENT: removed content %s and %d description(s), no orphans",
                        content_id, len(keys))
            return rows > 0
        except Exception as e:
            conn.rollback()
            logger.exception(f"Error deleting content with ID {content_id}. Error: {e}")
            return False
        finally:
            cur.close()
            conn.close()
            
    def student_activity_for_section(self, section_id):
        counts = {}
        conn = cur = None
        try:
            conn = self.connection()
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT test_key FROM test_description WHERE test_id = %s", (section_id,))
            keys = [r['test_key'] for r in cur.fetchall() if r.get('test_key')]
            if not keys:
                return {}
            marks = ','.join(['%s'] * len(keys))
            for label, table in (('results', 'test_result'),
                                 ('attempts', 'user_test_log'),
                                 ('answers', 'test_attempt_details'),
                                 ('feedback', 'test_feedback')):
                cur.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE test_key IN ({marks})", keys)
                found = cur.fetchone()
                if found and found['n']:
                    counts[label] = int(found['n'])
            return counts
        except Exception as e:
            logger.exception("ACTIVITY CHECK failed for section %s: %s", section_id, e)
            return {'unknown': 1}
        finally:
            if cur: cur.close()
            if conn: conn.close()

    def get_all_courses(self):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            query = "SELECT code, name FROM courses ORDER BY name ASC"
            cursor.execute(query)
            logger.info("Successfully fetched all courses from the database.")
            return cursor.fetchall()
        except Exception as e:
            logger.exception(f"FATAL: Could not fetch courses from database. Error: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
            
    def get_distinct_course_codes(self):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            query = "SELECT code, name FROM courses ORDER BY name ASC"
            cursor.execute(query)
            logger.info("Successfully fetched distinct course codes from the database.")
            return cursor.fetchall()
        except Exception as e:
            logger.exception(f"FATAL: Could not fetch distinct course codes from database. Error: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def get_enum_values(self, table_name, column_name):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True, buffered=True)
            cursor.execute(f"SHOW COLUMNS FROM {table_name} LIKE '{column_name}'")
            result = cursor.fetchone()
            if result and 'Type' in result:
                enum_type = result['Type'].decode('utf-8') if isinstance(result['Type'], bytes) else result['Type']
                if enum_type.startswith("enum("):
                    return enum_type[len("enum("):-1].replace("'", "").split(',')
            return []
        except Exception as e:
            logger.exception(f"Error fetching ENUM values for {table_name}.{column_name}. Error: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if db: db.close()
    
    def update_content_syllabus(self, content_id, syllabus_url):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(buffered=True)
            cursor.execute("UPDATE course_content SET syllabus_url = %s WHERE id = %s", (syllabus_url, content_id))
            changed = cursor.rowcount
            conn.commit()
            if changed > 0:
                logger.info(f"DB SYLLABUS: content id={content_id} now points at {syllabus_url!r}.")
                return True
            cursor.execute("SELECT 1 FROM course_content WHERE id = %s", (content_id,))
            if cursor.fetchone():
                logger.info(f"DB SYLLABUS: content id={content_id} already pointed at this file.")
                return True
            logger.error(f"DB SYLLABUS FAILED: content id={content_id} does not exist.")
            return False
        except Exception as e:
            logger.exception(f"DB SYLLABUS ERROR: could not save the syllabus for content {content_id}: {e}")
            if conn: conn.rollback()
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def update_content_image(self, content_id, image_url):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(buffered=True)
            query = "UPDATE course_content SET image_url = %s WHERE id = %s"
            cursor.execute(query, (image_url, content_id))
            changed = cursor.rowcount
            conn.commit()
            if changed > 0:
                logger.info(f"DB IMAGE: content id={content_id} now points at {image_url!r}.")
                return True
            cursor.execute("SELECT 1 FROM course_content WHERE id = %s", (content_id,))
            if cursor.fetchone():
                logger.info(f"DB IMAGE: content id={content_id} already pointed at this file.")
                return True
            logger.error(f"DB IMAGE FAILED: content id={content_id} does not exist.")
            return False
        except Exception as e:
            logger.exception(f"DB IMAGE ERROR: could not update the image for content {content_id}: {e}")
            if conn: conn.rollback()
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
    
    def purge_abandoned_subscription_orders(self, older_than_hours=24 * 30):
        conn = cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(buffered=True)
            cursor.execute(
                "DELETE FROM pcp_subscriptions WHERE status = 'failed' "
                "AND created_at < (NOW() - INTERVAL %s HOUR)", (int(older_than_hours),))
            removed = cursor.rowcount
            cursor.execute(
                "DELETE FROM content_orders WHERE status = 'failed' "
                "AND created_at < (NOW() - INTERVAL %s HOUR)", (int(older_than_hours),))
            removed += cursor.rowcount
            conn.commit()
            return removed
        except Exception:
            logger.exception("EXPIRY: could not clear abandoned subscription orders")
            if conn: conn.rollback()
            return 0
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def subscriptions_needing_reminder(self, days_before=3):
        conn = cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            cursor.execute(
                "SELECT s.id, s.email, s.course_code, s.plan, s.plan_label, s.expires_at, a.username "
                "FROM pcp_subscriptions s LEFT JOIN auth a ON a.email = s.email "
                "WHERE s.status = 'active' AND s.reminder_sent_at IS NULL "
                "AND s.expires_at > NOW() AND s.expires_at <= (NOW() + INTERVAL %s DAY)",
                (int(days_before),))
            return cursor.fetchall()
        except Exception:
            logger.exception("EXPIRY: could not list subscriptions needing a reminder")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def mark_reminder_sent(self, subscription_id):
        conn = cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(buffered=True)
            cursor.execute("UPDATE pcp_subscriptions SET reminder_sent_at = NOW() WHERE id = %s", (subscription_id,))
            conn.commit()
            return True
        except Exception:
            logger.exception("EXPIRY: could not mark reminder sent for %s", subscription_id)
            if conn: conn.rollback()
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def archive_content(self, content_id):
        conn = cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(buffered=True)
            cursor.execute("UPDATE course_content SET status = 'inactive' WHERE id = %s AND status <> 'inactive'",
                           (content_id,))
            changed = cursor.rowcount
            conn.commit()
            return changed > 0
        except Exception:
            logger.exception("EXPIRY: could not archive content id=%s", content_id)
            if conn: conn.rollback()
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def get_questions_by_code(self, code):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True)
            query = "SELECT * FROM practice_questions WHERE code = %s ORDER BY id DESC"
            cursor.execute(query, (code,))
            return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error fetching practice questions for code '{code}'. Error: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def get_notes_section_ids(self):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True)
            query = "SELECT section_id, title, code FROM course_content WHERE section = 'notes' ORDER BY created_at DESC"
            cursor.execute(query)
            return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error fetching notes section IDs: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def get_code_by_section_id(self, section_id):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True)
            query = "SELECT code FROM course_content WHERE section_id = %s"
            cursor.execute(query, (section_id,))
            result = cursor.fetchone()
            return result['code'] if result else None
        except Exception as e:
            logger.exception(f"Error fetching code for section ID {section_id}: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def insert_note(self, test_id, code, note_type, heading, sub_heading, title, sub_title, file_path, access_label='free'):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor()
            query = """
                INSERT INTO notes_content (test_id, code, type, heading, sub_heading, title, sub_title, file_path, access_label)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (test_id, code, note_type, heading, sub_heading, title, sub_title, file_path,
                                   'paid' if str(access_label).lower() == 'paid' else 'free'))
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.exception(f"Error inserting note: {e}")
            if conn: conn.rollback()
            return None
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
            
    def get_note_by_id(self, note_id):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True)
            query = "SELECT * FROM notes_content WHERE id = %s"
            cursor.execute(query, (note_id,))
            return cursor.fetchone()
        except Exception as e:
            logger.exception(f"Error fetching note by ID {note_id}: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
            
    def get_notes_by_criteria(self, test_id, code, note_type):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True)
            query = "SELECT * FROM notes_content WHERE test_id = %s AND code = %s AND type = %s"
            cursor.execute(query, (test_id, code, note_type))
            return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error fetching notes by criteria: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
            
    def delete_note_by_id(self, note_id):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor()
            query = "DELETE FROM notes_content WHERE id = %s"
            cursor.execute(query, (note_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error deleting note by ID {note_id}: {e}")
            if conn: conn.rollback()
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def get_distinct_headings(self, test_id, code, note_type):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True)
            query = "SELECT DISTINCT heading FROM notes_content WHERE test_id = %s AND code = %s AND type = %s"
            cursor.execute(query, (test_id, code, note_type))
            return [row['heading'] for row in cursor.fetchall()]
        except Exception as e:
            logger.exception(f"Error fetching distinct headings: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
            
    def get_distinct_sub_headings(self, test_id, code, note_type, heading):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True)
            query = "SELECT DISTINCT sub_heading FROM notes_content WHERE test_id = %s AND code = %s AND type = %s AND heading = %s"
            cursor.execute(query, (test_id, code, note_type, heading))
            return [row['sub_heading'] for row in cursor.fetchall()]
        except Exception as e:
            logger.exception(f"Error fetching distinct sub-headings: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def get_course_section_details(self, section_id):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True)
            query = "SELECT label, title FROM course_content WHERE section_id = %s LIMIT 1"
            cursor.execute(query, (section_id,))
            return cursor.fetchone()
        except Exception as e:
            logger.exception(f"Error fetching course section details for section_id {section_id}: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
    
    def get_notes_for_display(self, test_id):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True)
            query = "SELECT * FROM notes_content WHERE test_id = %s ORDER BY heading, sub_heading, title, id"
            cursor.execute(query, (test_id,))
            return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error fetching notes for display by test_id: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def insert_question(self, code, section, title):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor()
            query = "INSERT INTO practice_questions (code, section, title) VALUES (%s, %s, %s)"
            cursor.execute(query, (code, section, title))
            conn.commit()
            logger.info(f"Successfully inserted practice question '{title}' with ID {cursor.lastrowid}.")
            return cursor.lastrowid
        except Exception as e:
            logger.exception(f"Error inserting practice question for code {code}. Error: {e}")
            if conn: conn.rollback()
            return None
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
    
    def get_question_by_id(self, question_id):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True)
            query = "SELECT * FROM practice_questions WHERE id = %s"
            cursor.execute(query, (question_id,))
            return cursor.fetchone()
        except Exception as e:
            logger.exception(f"Error fetching practice question with ID {question_id}. Error: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
    
    def update_question_field(self, question_id, field, value):
        conn = None
        cursor = None
      
        allowed_fields = ['title', 'section']
        if field not in allowed_fields:
            logger.warning(f"Attempt to update a non-allowed field '{field}' for question ID {question_id}.")
            return False
        try:
            conn = self.connection()
            cursor = conn.cursor()
            query = f"UPDATE practice_questions SET {field} = %s WHERE id = %s"
            cursor.execute(query, (value, question_id))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error updating question ID {question_id}. Error: {e}")
            if conn: conn.rollback()
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
    def delete_question(self, question_id):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor()
            query = "DELETE FROM practice_questions WHERE id = %s"
            cursor.execute(query, (question_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error deleting question ID {question_id}. Error: {e}")
            if conn: conn.rollback()
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()