import mysql.connector
from config import Config
import logging

logger = logging.getLogger(__name__)

class PaperOperation:
    def connection(self):
        try:
            from admin.db_pool import get_connection
            return get_connection()
        except mysql.connector.Error as err:
            logger.error(f"Error connecting to database: {err}")
            raise


    @staticmethod
    def _test_sections():
        from admin import taxonomy
        keys = set(taxonomy.test_sections())
        keys |= {'mock_test', 'coding_test', 'communication_test', 'aptitude_test'}
        return sorted(keys)

    def get_all_paper_codes(self):
        sections = self._test_sections()
        marks = ', '.join(['%s'] * len(sections))
        return self._fetch_all(
            f"SELECT DISTINCT code FROM course_content "
            f"WHERE section IN ({marks}) ORDER BY code ASC", tuple(sections))

    def get_distinct_values(self, column, paper_code, subject=None):
        params = [paper_code]
        query = f"SELECT DISTINCT {column} FROM questions WHERE paper_code = %s"
        if subject:
            query += " AND subject = %s"
            params.append(subject)
        query += f" AND {column} IS NOT NULL AND {column} != '' ORDER BY {column} ASC"
        return self._fetch_all(query, tuple(params))

    def insert_question(self, data):
        query = """
            INSERT INTO questions
            (paper_code, question_id, question_type, subject, topic, question_text,
             option_a, option_b, option_c, option_d, correct_option,
             answer_text, year, paper_set, explanation_link, question_image, option_regions)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            data['paper_code'], data['question_id'], data['question_type'],
            data.get('subject'), data.get('topic'), data.get('question_text'),
            data.get('option_a'), data.get('option_b'), data.get('option_c'), data.get('option_d'),
            data.get('correct_option'), data.get('answer_text'), data.get('year'),
            data.get('paper_set'), data.get('explanation_link'),
            data.get('question_image'), data.get('option_regions')
        )
        return self._execute_query(query, params, fetch_last_id=True)

    def next_question_id(self, paper_code, subject=None):
        rows = self._fetch_all(
            "SELECT COALESCE(MAX(question_id), 0) + 1 AS next_id FROM questions WHERE paper_code = %s",
            (paper_code,))
        return int(rows[0]['next_id']) if rows else 1

    def content_index(self, paper_code):
        return self._fetch_all(
            "SELECT id, question_id, subject, question_type, question_text, option_a, option_b, option_c, option_d "
            "FROM questions WHERE paper_code = %s", (paper_code,))

    def paper_code_exists(self, paper_code):
        sections = self._test_sections()
        marks = ', '.join(['%s'] * len(sections))
        rows = self._fetch_all(
            f"SELECT 1 FROM course_content WHERE code = %s "
            f"AND section IN ({marks}) LIMIT 1",
            (paper_code, *sections)
        )
        return bool(rows)

    def question_id_exists(self, paper_code, question_id):
        rows = self._fetch_all(
            "SELECT id FROM questions WHERE paper_code = %s AND question_id = %s LIMIT 1",
            (paper_code, question_id)
        )
        return bool(rows)

    def insert_questions_bulk(self, rows):
        if not rows:
            return 0
        conn = self.connection()
        conn.autocommit = False
        cursor = conn.cursor()
        try:
            if not conn.in_transaction:
                conn.start_transaction()
            query = """
                INSERT INTO questions
                (paper_code, question_id, question_type, subject, topic, question_text,
                 option_a, option_b, option_c, option_d, correct_option,
                 answer_text, year, paper_set, explanation_link)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            params = [
                (r['paper_code'], r['question_id'], r['question_type'], r.get('subject'), r.get('topic'),
                 r.get('question_text'), r.get('option_a'), r.get('option_b'), r.get('option_c'),
                 r.get('option_d'), r.get('correct_option'), r.get('answer_text'), r.get('year'),
                 r.get('paper_set'), r.get('explanation_link'))
                for r in rows
            ]
            CHUNK = 500
            for i in range(0, len(params), CHUNK):
                cursor.executemany(query, params[i:i + CHUNK])
            conn.commit()
            logger.info(f"DB BULK INSERT: committed {len(params)} practice question(s) in one transaction "
                        f"({(len(params) + CHUNK - 1) // CHUNK} batch(es))")
            return len(params)
        except Exception as e:
            conn.rollback()
            logger.exception(f"DB BULK INSERT FAILED: rolled back {len(rows)} practice row(s): {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    def get_paper_structure(self, paper_code):
        query = """
            SELECT subject,
                   COUNT(*) AS questions,
                   COUNT(DISTINCT NULLIF(topic, '')) AS topics,
                   SUM(CASE WHEN UPPER(question_type) = 'MCQ' THEN 1 ELSE 0 END) AS mcq,
                   SUM(CASE WHEN UPPER(question_type) = 'MSQ' THEN 1 ELSE 0 END) AS msq,
                   SUM(CASE WHEN UPPER(question_type) = 'NAT' THEN 1 ELSE 0 END) AS nat,
                   COUNT(DISTINCT NULLIF(year, '')) AS years
            FROM questions
            WHERE paper_code = %s
            GROUP BY subject
            ORDER BY subject
        """
        rows = self._fetch_all(query, (paper_code,))
        logger.info(f"DB STRUCTURE: paper {paper_code!r} has {len(rows)} subject(s)")
        return rows

    def get_questions_for_export(self, paper_code, subject=None, topic=None):
        query = "SELECT * FROM questions WHERE paper_code = %s"
        params = [paper_code]
        if subject and subject.strip():
            query += " AND subject = %s"
            params.append(subject)
        if topic and topic.strip():
            query += " AND topic = %s"
            params.append(topic)
        query += " ORDER BY subject, topic, question_id"
        rows = self._fetch_all(query, tuple(params))
        logger.info(f"DB EXPORT: fetched {len(rows)} practice question(s) for paper {paper_code!r}")
        return rows

    def search_questions(self, paper_code, subject, topic=None):
        base_query = "SELECT * FROM questions WHERE paper_code = %s AND subject = %s"
        params = [paper_code, subject]
        
        if topic and topic.strip():
            base_query += " AND topic = %s"
            params.append(topic)
            
        base_query += " ORDER BY question_id ASC LIMIT 500"
        return self._fetch_all(base_query, tuple(params))

    UPDATABLE_COLUMNS = (
        'paper_code', 'question_id', 'question_type', 'subject', 'topic', 'question_text',
        'option_a', 'option_b', 'option_c', 'option_d', 'correct_option',
        'answer_text', 'year', 'paper_set', 'explanation_link',
        'question_image', 'option_regions',
    )

    def get_question_by_id(self, db_id):
        rows = self._fetch_all("SELECT * FROM questions WHERE id = %s LIMIT 1", (db_id,))
        return rows[0] if rows else None

    def question_id_taken_by_other(self, paper_code, question_id, db_id):
        rows = self._fetch_all(
            "SELECT id FROM questions WHERE paper_code = %s AND question_id = %s AND id != %s LIMIT 1",
            (paper_code, question_id, db_id)
        )
        return bool(rows)

    def update_question(self, db_id, data):
        fields = [col for col in self.UPDATABLE_COLUMNS if col in data]
        if not fields:
            return 0
        assignments = ', '.join(f"{col} = %s" for col in fields)
        params = tuple(data[col] for col in fields) + (db_id,)
        return self._execute_query(f"UPDATE questions SET {assignments} WHERE id = %s", params)

    def delete_question(self, db_id):
        query = "DELETE FROM questions WHERE id = %s"
        return self._execute_query(query, (db_id,))

    def _fetch_all(self, query, params=None):
        conn = None
        cursor = None
        try:
            conn = self.connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params or ())
            return cursor.fetchall()
        except mysql.connector.Error as err:
            logger.error(f"Error in _fetch_all: {err}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def _execute_query(self, query, params=None, fetch_last_id=False):
        conn = None
        cursor = None
        last_id = None
        try:
            conn = self.connection()
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            if fetch_last_id:
                last_id = cursor.lastrowid
            affected = cursor.rowcount
            conn.commit()
            return last_id if fetch_last_id else affected
        except mysql.connector.Error as err:
            logger.error(f"Database query failed: {err}\nQuery: {query}\nParams: {params}")
            if conn: conn.rollback()
            raise err
        finally:
            if cursor: cursor.close()
            if conn: conn.close()