import mysql.connector
from mysql.connector import Error
from config import Config
from contextlib import contextmanager
import logging
import datetime

logger = logging.getLogger(__name__)

class UserOperation:
    @contextmanager
    def connection(self):
        conn = None
        try:
            from routes.db_pool import get_connection
            conn = get_connection()
            yield conn
        except Error as e:
            logger.error(f"DATABASE CONNECTION ERROR: {e}")
            raise
        finally:
            if conn:
                try: conn.close()
                except Exception: pass

    @contextmanager
    def cursor(self, conn, buffered=False, dictionary=True):
        cursor = None
        try:
            cursor = conn.cursor(buffered=buffered, dictionary=dictionary)
            yield cursor
        finally:
            if cursor:
                cursor.close()

    def fetch_one(self, query, params=()):
        try:
            with self.connection() as conn:
                with self.cursor(conn, buffered=True) as cursor:
                    logger.info(f"DB EXECUTE (fetch_one): {query} | Params: {params}")
                    
                    cursor.execute(query, params)
                    result = cursor.fetchone()
                    
                    if result:
                        logger.info("DB RESULT: Found 1 record.")
                    else:
                        logger.warning(f"DB RESULT: Found 0 records for query: {query} with params: {params}")
                        
                    return result
        except Error as e:
            logger.error(f"DB ERROR in fetch_one: {e} | Query: {query}")
            return None

    def fetch_all(self, query, params=()):
        try:
            with self.connection() as conn:
                with self.cursor(conn, buffered=True) as cursor:
                    logger.info(f"DB EXECUTE (fetch_all): {query} | Params: {params}")
                    
                    cursor.execute(query, params)
                    result = cursor.fetchall()
                    
                    count = len(result) if result else 0
                    if count > 0:
                        logger.info(f"DB RESULT: Fetched {count} rows.")
                    else:
                        logger.warning(f"DB RESULT: Fetched 0 rows. Check if data exists for params: {params}")
                        
                    return result
        except Error as e:
            logger.error(f"DB ERROR in fetch_all: {e} | Query: {query}")
            return []

    def execute_query(self, query, params=()):
        try:
            with self.connection() as conn:
                with self.cursor(conn, dictionary=False) as cursor:
                    logger.info(f"DB EXECUTE (write): {query} | Params: {params}")
                    cursor.execute(query, params)
                    conn.commit()
                    logger.info("DB COMMIT: Successful.")
                    return True
        except Error as e:
            logger.error(f"DB ERROR in execute_query: {e} | Query: {query}")
            return False

    def report_question_issue(self, question_id, problem_description, user_email):
        try:
            select_query = "SELECT report_count, report_problem FROM questions WHERE question_id = %s"
            question_report = self.fetch_one(select_query, (question_id,))

            if not question_report:
                logger.warning(f"Report Issue Failed: Question ID {question_id} not found.")
                return False

            current_count = question_report.get('report_count', 0)
            existing_problems = question_report.get('report_problem') if question_report.get('report_problem') else ""
            
            new_count = current_count + 1
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_problem_entry = f"Report from '{user_email}' at {timestamp}:\n{problem_description}\n{'-'*20}\n"
            updated_problems = new_problem_entry + existing_problems

            update_query = "UPDATE questions SET report_count = %s, report_problem = %s WHERE question_id = %s"
            return self.execute_query(update_query, (new_count, updated_problems, question_id))
        except Exception as e:
            logger.exception(f"Unexpected error reporting issue for QID {question_id}: {e}")
            return False

    def get_user_unique_code(self, email, course_code):
        try:
            query = "SELECT unique_code FROM enrollment WHERE email = %s AND code = %s"
            result = self.fetch_one(query, (email, course_code))
            return result['unique_code'] if result else None
        except Exception:
            logger.exception(f"Error getting unique code for user '{email}' and course '{course_code}'")
            return None

    def get_unique_code(self, email, course_code):
        return self.get_user_unique_code(email, course_code)

    def get_guest_access_code(self, course_code):
        try:
            query = "SELECT unique_code FROM guest_codes WHERE code = %s"
            result = self.fetch_one(query, (course_code,))
            if result:
                return result['unique_code']
            return None
        except Exception as e:
            if "doesn't exist" in str(e):
                logger.warning(f"Guest table missing. Cannot fetch code for {course_code}")
                return None
            logger.exception(f"Error getting guest access code for course '{course_code}'")
            return None

    def get_question_by_id(self, question_id):
        try:
            query = "SELECT * FROM questions WHERE question_id = %s"
            return self.fetch_one(query, (question_id,))
        except Exception:
            logger.exception(f"Error getting question by id '{question_id}'")
            return None
    
   

    def get_subjects_by_course(self, course_code):
        try:
            logger.info(f"Fetching subjects for course: {course_code} using 'paper_code'")
            query = "SELECT DISTINCT subject FROM questions WHERE paper_code = %s"
            return self.fetch_all(query, (course_code,))
        except Exception:
            logger.warning(f"Column 'paper_code' failed. Retrying with 'code' column for course: {course_code}")
            try:
                query = "SELECT DISTINCT subject FROM questions WHERE code = %s"
                return self.fetch_all(query, (course_code,))
            except Exception:
                logger.exception(f"FATAL: Could not fetch subjects for {course_code}. Check table schema.")
                return []

    def get_topics_by_subject(self, course_code, subject):
        try:
            logger.info(f"Fetching topics for {subject} in {course_code} using 'paper_code'")
            query = "SELECT DISTINCT topic FROM questions WHERE subject = %s AND paper_code = %s"
            return self.fetch_all(query, (subject, course_code))
        except Exception:
            logger.warning(f"Column 'paper_code' failed. Retrying with 'code' column.")
            query = "SELECT DISTINCT topic FROM questions WHERE subject = %s AND code = %s"
            return self.fetch_all(query, (subject, course_code))

    def get_question_count_topic(self, course_code, subject, topic):
        try:
            query = "SELECT COUNT(*) as total FROM questions WHERE subject = %s AND topic = %s AND paper_code = %s"
            return self.fetch_one(query, (subject, topic, course_code))
        except Exception:
            query = "SELECT COUNT(*) as total FROM questions WHERE subject = %s AND topic = %s AND code = %s"
            return self.fetch_one(query, (subject, topic, course_code))

    def get_questions_topic(self, course_code, subject, topic, limit, offset):
        try:
            logger.info(f"Fetching questions for Topic: {topic}, Subject: {subject}, Course: {course_code}")
            query = "SELECT * FROM questions WHERE subject = %s AND topic = %s AND paper_code = %s LIMIT %s OFFSET %s"
            return self.fetch_all(query, (subject, topic, course_code, limit, offset))
        except Exception:
            logger.warning("Fallback to 'code' column for fetching topic questions.")
            query = "SELECT * FROM questions WHERE subject = %s AND topic = %s AND code = %s LIMIT %s OFFSET %s"
            return self.fetch_all(query, (subject, topic, course_code, limit, offset))

    def get_question_count_subject(self, course_code, subject):
        try:
            query = "SELECT COUNT(*) as total FROM questions WHERE subject = %s AND paper_code = %s"
            return self.fetch_one(query, (subject, course_code))
        except Exception:
            query = "SELECT COUNT(*) as total FROM questions WHERE subject = %s AND code = %s"
            return self.fetch_one(query, (subject, course_code))

    def get_questions_subject(self, course_code, subject, limit, offset):
        try:
            logger.info(f"Fetching questions for Subject: {subject}, Course: {course_code}")
            query = "SELECT * FROM questions WHERE subject = %s AND paper_code = %s LIMIT %s OFFSET %s"
            return self.fetch_all(query, (subject, course_code, limit, offset))
        except Exception:
            logger.warning("Fallback to 'code' column for fetching subject questions.")
            query = "SELECT * FROM questions WHERE subject = %s AND code = %s LIMIT %s OFFSET %s"
            return self.fetch_all(query, (subject, course_code, limit, offset))

    def get_years_by_course(self, course_code):
        try:
            query = "SELECT DISTINCT year FROM questions WHERE paper_code = %s ORDER BY year DESC"
            return self.fetch_all(query, (course_code,))
        except Exception:
            query = "SELECT DISTINCT year FROM questions WHERE code = %s ORDER BY year DESC"
            return self.fetch_all(query, (course_code,))

    def get_question_count_year(self, course_code, year):
        try:
            query = "SELECT COUNT(*) as total FROM questions WHERE year = %s AND paper_code = %s"
            return self.fetch_one(query, (year, course_code))
        except Exception:
            query = "SELECT COUNT(*) as total FROM questions WHERE year = %s AND code = %s"
            return self.fetch_one(query, (year, course_code))

    def get_questions_year(self, course_code, year, limit, offset):
        try:
            logger.info(f"Fetching questions for Year: {year}, Course: {course_code}")
            query = "SELECT * FROM questions WHERE year = %s AND paper_code = %s LIMIT %s OFFSET %s"
            return self.fetch_all(query, (year, course_code, limit, offset))
        except Exception:
            logger.warning("Fallback to 'code' column for fetching year questions.")
            query = "SELECT * FROM questions WHERE year = %s AND code = %s LIMIT %s OFFSET %s"
            return self.fetch_all(query, (year, course_code, limit, offset))