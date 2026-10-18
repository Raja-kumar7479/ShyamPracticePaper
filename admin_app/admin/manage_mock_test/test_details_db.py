import mysql.connector
from config import Config
import logging

logger = logging.getLogger(__name__)

COMM_ID_OFFSET = 1000000

class UserOperation:
    def connection(self):
        try:
            from admin.db_pool import get_connection
            return get_connection()
        except mysql.connector.Error as err:
            logger.error(f"Error connecting to database: {err}")
            raise

    @staticmethod
    def _mirror_sections():
        from admin import taxonomy
        keys = [key for key, meta in taxonomy.catalog()['sections'].items()
                if meta['editor'] and meta['editor'] != 'competitive']
        return set(keys) | {'communication_test', 'coding_test', 'aptitude_test'}

    def section_for_test_id(self, test_id):
        row = self._fetch_one("""
            SELECT cc.section
            FROM course_content cc
            WHERE cc.section_id = %s LIMIT 1
        """, (test_id,))
        return (row or {}).get('section') or ''

    def _is_placement_test_id(self, test_id):
        return self.section_for_test_id(test_id) in self._mirror_sections()

    def _tables_for_test_id(self, test_id):
        if self._is_placement_test_id(test_id):
            return 'comm_description', 'comm_questions'
        return 'test_description', 'test_questions'

    def _tables_for_description_id(self, description_id):
        if int(description_id) >= COMM_ID_OFFSET:
            return 'comm_description', 'comm_questions'
        return 'test_description', 'test_questions'

    def _question_table_for_id(self, question_id):
        return 'comm_questions' if int(question_id) >= COMM_ID_OFFSET else 'test_questions'

    def get_content_for_tests(self):
        from admin import taxonomy
        sections = set(taxonomy.test_sections()) | {'mock_test'} | self._mirror_sections()
        placeholders = ', '.join(['%s'] * len(sections))
        query = f"""
            SELECT cc.section_id AS test_id, cc.title, cc.subtitle, cc.code, cc.label,
                   cc.section, cc.max_test_descriptions, c.name AS course_name, c.subgroup AS course_subgroup,
                   (SELECT COUNT(*) FROM test_description td WHERE td.test_id = cc.section_id)
                 + (SELECT COUNT(*) FROM comm_description cd WHERE cd.test_id = cc.section_id) AS description_count,
                   (SELECT COALESCE(SUM(td.total_questions), 0) FROM test_description td WHERE td.test_id = cc.section_id)
                 + (SELECT COALESCE(SUM(cd.total_questions), 0) FROM comm_description cd WHERE cd.test_id = cc.section_id) AS declared_questions
            FROM course_content cc
            LEFT JOIN courses c ON c.code = cc.code
            WHERE cc.section IN ({placeholders})
            ORDER BY cc.code, cc.title
        """
        rows = self._fetch_all(query, tuple(sections))
        logger.info(f"DB: fetched {len(rows)} mock-test item(s) with description counts")
        return rows

    def get_test_descriptions_by_test_id(self, test_id):
        desc_table, _ = self._tables_for_test_id(test_id)
        query = f"SELECT * FROM {desc_table} WHERE test_id = %s"
        rows = self._fetch_all(query, (test_id,))
        section = self.section_for_test_id(test_id)
        for row in rows:
            row['section'] = section
            row['student_activity'] = self.student_activity_for_description(row['id'])
        return rows

    def tcs_exam_summary(self, test_key):
        row = self._fetch_one("""
            SELECT e.id, e.is_published, e.coding_test_id,
                   (SELECT COUNT(*) FROM test_questions q WHERE q.test_key = e.aptitude_test_key) AS aptitude_questions,
                   (SELECT COUNT(*) FROM cp_questions q JOIN cp_sections s ON s.id = q.section_id WHERE s.test_id = e.coding_test_id) AS coding_questions,
                   (SELECT COUNT(*) FROM tcs_attempts a WHERE a.tcs_exam_id = e.id) AS attempts
            FROM tcs_exams e WHERE e.aptitude_test_key = %s ORDER BY e.id DESC LIMIT 1
        """, (test_key,))
        if not row:
            return {'exam_id': None, 'published': False, 'aptitude_questions': 0, 'coding_questions': 0, 'attempts': 0}
        return {'exam_id': row['id'], 'published': bool(row['is_published']), 'aptitude_questions': int(row['aptitude_questions'] or 0),
                'coding_questions': int(row['coding_questions'] or 0), 'attempts': int(row['attempts'] or 0)}

    def sync_tcs_exam(self, old_key, desc):
        self._execute_query("""
            UPDATE tcs_exams SET aptitude_test_key = %s, title = %s, subtitle = %s WHERE aptitude_test_key = %s
        """, (desc['test_key'], desc.get('subject_title') or 'TCS exam', desc.get('subject_subtitle') or None, old_key))
        self._execute_query("""
            UPDATE cp_tests SET test_key = %s, title = %s WHERE test_key = %s
        """, (desc['test_key'] + '_code', f"{desc.get('subject_title') or 'TCS exam'} - Coding", old_key + '_code'))

    def get_test_description_by_id(self, description_id):
        desc_table, _ = self._tables_for_description_id(description_id)
        query = f"SELECT * FROM {desc_table} WHERE id = %s"
        return self._fetch_one(query, (description_id,))

    def platform_for_test_id(self, test_id):
        row = self._fetch_one("""
            SELECT COALESCE(g.platform, 'competitive') AS platform
            FROM course_content cc
            LEFT JOIN course_groups g ON g.group_name = cc.name
            WHERE cc.section_id = %s LIMIT 1
        """, (test_id,))
        return (row or {}).get('platform') or 'competitive'

    def content_label_for_test_id(self, test_id):
        row = self._fetch_one("SELECT label FROM course_content WHERE section_id = %s", (test_id,))
        return row['label'] if row else None

    def get_code_for_test_id(self, test_id):
        query = "SELECT code FROM course_content WHERE section_id = %s LIMIT 1"
        row = self._fetch_one(query, (test_id,))
        code = row['code'] if row else None
        logger.info(f"DB STEP: resolved course code {code!r} for test_id={test_id!r}")
        return code

    def description_usage(self, test_id):
        row = self._fetch_one("""
            SELECT cc.max_test_descriptions AS cap,
                   (SELECT COUNT(*) FROM test_description td WHERE td.test_id = cc.section_id)
                 + (SELECT COUNT(*) FROM comm_description cd WHERE cd.test_id = cc.section_id) AS used
            FROM course_content cc WHERE cc.section_id = %s
        """, (test_id,))
        if not row:
            return {'count': 0, 'limit': None}
        cap = row.get('cap')
        return {'count': int(row.get('used') or 0), 'limit': int(cap) if cap else None}

    def rekey_test_description(self, description_id, new_test_key):
        desc_table, q_table = self._tables_for_description_id(description_id)
        conn = self.connection()
        conn.autocommit = False
        cursor = conn.cursor(dictionary=True, buffered=True)
        try:
            if not conn.in_transaction:
                conn.start_transaction()
            cursor.execute(f"SELECT test_key FROM {desc_table} WHERE id = %s FOR UPDATE", (description_id,))
            row = cursor.fetchone()
            if not row:
                conn.rollback()
                return None
            old_key = row['test_key']
            cursor.execute(f"UPDATE {desc_table} SET test_key = %s, updated_at = NOW() WHERE id = %s",
                           (new_test_key, description_id))
            cursor.execute(f"UPDATE {q_table} SET test_key = %s WHERE test_description_id = %s",
                           (new_test_key, description_id))
            if desc_table == 'test_description':
                cursor.execute("UPDATE cp_tests SET test_key = %s WHERE test_key = %s", (new_test_key, old_key))
            conn.commit()
            logger.info(f"DB REKEY: description {description_id} {old_key} -> {new_test_key}")
            return old_key
        except Exception as e:
            conn.rollback()
            logger.exception(f"DB REKEY FAILED for description {description_id}: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    def test_key_exists(self, test_key):
        if self._fetch_one("SELECT id FROM test_description WHERE test_key = %s LIMIT 1", (test_key,)) is not None:
            return True
        return self._fetch_one("SELECT id FROM comm_description WHERE test_key = %s LIMIT 1", (test_key,)) is not None

    def insert_test_description(self, data):
        logger.info(f"DB STEP 1: inserting test description for test_id={data.get('test_id')!r}")

        code = data.get('code') or self.get_code_for_test_id(data['test_id'])
        if not code:
            logger.error(f"DB STEP 2 FAILED: no course_content row for section_id={data['test_id']!r}")
            raise ValueError("This Test ID does not belong to any course. Please pick a valid test.")

        desc_table, _ = self._tables_for_test_id(data['test_id'])
        query = f"""
            INSERT INTO {desc_table}
            (test_id, code, test_key, subject_title, subject_subtitle,
             total_questions, total_marks, total_duration_minutes, show_calculator, access_label)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            data['test_id'], code, data['test_key'], data['subject_title'],
            data.get('subject_subtitle') or '', data['total_questions'],
            data['total_marks'], data['total_duration_minutes'],
            1 if data.get('show_calculator', 1) else 0,
            data.get('access_label') if data.get('access_label') in ('free', 'paid') else 'inherit'
        )
        logger.info(f"DB STEP 3: executing insert into {desc_table} with code={code!r} test_key={data['test_key']!r}")
        self._execute_query(query, params)
        logger.info(f"DB STEP 4: test description saved for test_id={data['test_id']!r}, code={code!r}")

    def update_test_description_field(self, id, field, value):
        allowed_fields = [
            'test_key', 'subject_title', 'subject_subtitle', 'total_questions',
            'total_marks', 'total_duration_minutes', 'show_calculator', 'access_label'
        ]
        if field not in allowed_fields:
            raise ValueError(f"Invalid field for update: {field}")
        desc_table, _ = self._tables_for_description_id(id)
        query = f"UPDATE {desc_table} SET {field} = %s, updated_at = NOW() WHERE id = %s"
        self._execute_query(query, (value, id))

    def student_activity_for_description(self, description_id):
        desc_table, _ = self._tables_for_description_id(description_id)
        if desc_table != 'test_description':
            return {}
        row = self._fetch_one("SELECT test_key FROM test_description WHERE id = %s", (description_id,))
        if not row or not row.get('test_key'):
            return {}
        key = row['test_key']
        counts = {}
        for label, table in (('results', 'test_result'),
                             ('attempts', 'user_test_log'),
                             ('answers', 'test_attempt_details'),
                             ('feedback', 'test_feedback')):
            try:
                found = self._fetch_one(f"SELECT COUNT(*) AS n FROM {table} WHERE test_key = %s", (key,))
                if found and found['n']:
                    counts[label] = int(found['n'])
            except Exception:
                logger.exception("ACTIVITY CHECK: could not count %s for %s", table, key)
        return counts

    def delete_test_description(self, description_id):
        desc_table, q_table = self._tables_for_description_id(description_id)
        self._execute_query(f"DELETE FROM {q_table} WHERE test_description_id = %s", (description_id,))
        self._execute_query(f"DELETE FROM {desc_table} WHERE id = %s", (description_id,))

    def get_questions_for_description_section(self, description_id, section_id):
        _, q_table = self._tables_for_description_id(description_id)
        query = f"SELECT * FROM {q_table} WHERE test_description_id = %s AND section_id = %s ORDER BY question_number"
        return self._fetch_all(query, (description_id, section_id))

    def get_flagged_questions_for_description(self, description_id):
        _, q_table = self._tables_for_description_id(description_id)
        if q_table != 'test_questions':
            return []
        query = """
            SELECT q.id, q.section_id, q.section_name, q.question_number, q.question_text,
                   COUNT(*) AS flag_count,
                   GROUP_CONCAT(DISTINCT a.email ORDER BY a.email SEPARATOR ', ') AS flagged_by,
                   GROUP_CONCAT(DISTINCT NULLIF(a.flag_note, '') SEPARATOR ' | ') AS notes
            FROM test_attempt_details a
            JOIN test_questions q ON q.id = a.question_id
            WHERE q.test_description_id = %s AND a.is_flagged = 1
            GROUP BY q.id, q.section_id, q.section_name, q.question_number, q.question_text
            ORDER BY flag_count DESC, q.question_number
        """
        rows = self._fetch_all(query, (description_id,))
        logger.info(f"DB FLAGS: {len(rows)} flagged question(s) for description {description_id}")
        return rows

    def get_question_count_for_description(self, description_id):
        _, q_table = self._tables_for_description_id(description_id)
        query = f"SELECT COUNT(*) as count FROM {q_table} WHERE test_description_id = %s"
        result = self._fetch_one(query, (description_id,))
        return result['count'] if result else 0

    def question_texts_for_description(self, description_id):
        _, q_table = self._tables_for_description_id(description_id)
        return self._fetch_all(f"""
            SELECT id, section_id, section_name, question_number, question_type, question_text,
                   option_a, option_b, option_c, option_d
            FROM {q_table} WHERE test_description_id = %s
        """, (description_id,))

    def get_all_questions_for_description(self, description_id):
        _, q_table = self._tables_for_description_id(description_id)
        query = f"""
            SELECT * FROM {q_table}
            WHERE test_description_id = %s
            ORDER BY section_id, question_number, id
        """
        rows = self._fetch_all(query, (description_id,))
        logger.info(f"DB EXPORT: fetched {len(rows)} question(s) for description {description_id}")
        return rows

    def get_marks_sum_for_description(self, description_id):
        _, q_table = self._tables_for_description_id(description_id)
        query = f"SELECT COALESCE(SUM(correct_marks), 0) AS total FROM {q_table} WHERE test_description_id = %s"
        result = self._fetch_one(query, (description_id,))
        return float(result['total']) if result else 0.0

    def get_test_structure(self, description_id):
        _, q_table = self._tables_for_description_id(description_id)
        query = f"""
            SELECT section_id, section_name,
                   COUNT(*) AS questions,
                   SUM(CASE WHEN UPPER(question_type) = 'MCQ' THEN 1 ELSE 0 END) AS mcq,
                   SUM(CASE WHEN UPPER(question_type) = 'MSQ' THEN 1 ELSE 0 END) AS msq,
                   SUM(CASE WHEN UPPER(question_type) = 'NAT' THEN 1 ELSE 0 END) AS nat,
                   COALESCE(SUM(correct_marks), 0) AS marks
            FROM {q_table}
            WHERE test_description_id = %s
            GROUP BY section_id, section_name
            ORDER BY MIN(question_number)
        """
        rows = self._fetch_all(query, (description_id,))
        logger.info(f"DB STRUCTURE: description_id={description_id} has {len(rows)} section(s)")
        return rows

    def get_max_question_number_in_section(self, description_id, section_id):
        _, q_table = self._tables_for_description_id(description_id)
        query = f"SELECT MAX(question_number) as max_num FROM {q_table} WHERE test_description_id = %s AND section_id = %s"
        result = self._fetch_one(query, (description_id, section_id))
        return result['max_num'] if result and result['max_num'] is not None else 0

    def insert_test_question(self, data):
      _, q_table = self._tables_for_description_id(data['test_description_id'])
      query = f"""
        INSERT INTO {q_table}
        (test_id, test_key, test_description_id, section_id, section_name, question_number, question_type, question_text,
         question_image, option_regions,
         option_a, option_b, option_c, option_d, correct_option, correct_marks,
         negative_marks, question_level, answer_text, answer_link, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
      """
      params = (
        data['test_id'], data['test_key'], data['test_description_id'], data['section_id'], data['section_name'], data['question_number'],
        data['question_type'], data['question_text'],
        data.get('question_image'), data.get('option_regions'),
        data.get('option_a'),
        data.get('option_b'), data.get('option_c'), data.get('option_d'),
        data['correct_option'], data['correct_marks'], data['negative_marks'],
        data['question_level'], data.get('answer_text'), data.get('answer_link')
      )
      self._execute_query(query, params)

    def insert_test_questions_bulk(self, rows):
        if not rows:
            return 0
        _, q_table = self._tables_for_description_id(rows[0]['test_description_id'])
        conn = self.connection()
        conn.autocommit = False
        cursor = conn.cursor()
        try:
            if not conn.in_transaction:
                conn.start_transaction()
            query = f"""
                INSERT INTO {q_table}
                (test_id, test_key, test_description_id, section_id, section_name, question_number, question_type, question_text,
                 option_a, option_b, option_c, option_d, correct_option, correct_marks,
                 negative_marks, question_level, answer_text, answer_link, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            """
            params = [
                (r['test_id'], r['test_key'], r['test_description_id'], r['section_id'], r['section_name'],
                 r['question_number'], r['question_type'], r['question_text'], r.get('option_a'),
                 r.get('option_b'), r.get('option_c'), r.get('option_d'), r['correct_option'],
                 r['correct_marks'], r['negative_marks'], r['question_level'],
                 r.get('answer_text'), r.get('answer_link'))
                for r in rows
            ]
            CHUNK = 500
            for i in range(0, len(params), CHUNK):
                cursor.executemany(query, params[i:i + CHUNK])
            conn.commit()
            logger.info(f"DB BULK INSERT: committed {len(params)} question(s) in one transaction "
                        f"({(len(params) + CHUNK - 1) // CHUNK} batch(es))")
            return len(params)
        except Exception as e:
            conn.rollback()
            logger.exception(f"DB BULK INSERT FAILED: rolled back {len(rows)} row(s): {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    def update_test_question_field(self, id, field, value):
        allowed_fields = [
            'section_id', 'section_name', 'question_type', 'question_text', 'option_a',
            'option_b', 'option_c', 'option_d', 'correct_option', 'correct_marks',
            'negative_marks', 'question_level', 'answer_text', 'answer_link'
        ]
        if field not in allowed_fields:
            raise ValueError(f"Invalid field for update: {field}")
        q_table = self._question_table_for_id(id)
        query = f"UPDATE {q_table} SET {field} = %s, updated_at = NOW() WHERE id = %s"
        self._execute_query(query, (value, id))

    def update_test_question_fields(self, id, fields):
        allowed = {'section_id', 'section_name', 'question_type', 'question_text', 'option_a',
                   'option_b', 'option_c', 'option_d', 'correct_option', 'correct_marks',
                   'negative_marks', 'question_level', 'answer_text', 'answer_link'}
        unknown = [f for f in fields if f not in allowed]
        if unknown:
            raise ValueError(f"Invalid field for update: {', '.join(unknown)}")
        if not fields:
            return
        q_table = self._question_table_for_id(id)
        sets = ', '.join(f"{f} = %s" for f in fields)
        self._execute_query(f"UPDATE {q_table} SET {sets}, updated_at = NOW() WHERE id = %s",
                            (*fields.values(), id))

    def get_comm_sections(self, test_key):
        return self._fetch_all("""
            SELECT s.*, (SELECT COUNT(*) FROM comm_questions q
                         WHERE q.test_key = s.test_key AND q.section_name = s.section_name) AS question_count
            FROM comm_sections s WHERE s.test_key = %s
            ORDER BY s.section_order, s.id
        """, (test_key,))

    def add_comm_section(self, data):
        self._execute_query("""
            INSERT INTO comm_sections
            (test_key, section_id, section_name, section_title, section_instruction,
             section_duration_seconds, section_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (data['test_key'], data['section_id'], data['section_name'], data['section_title'],
              data.get('section_instruction') or '', data['section_duration_seconds'], data['section_order']))

    def delete_comm_section(self, section_pk):
        row = self._fetch_one("SELECT test_key, section_name FROM comm_sections WHERE id = %s", (section_pk,))
        if not row:
            return 0
        self._execute_query("DELETE FROM comm_questions WHERE test_key = %s AND section_name = %s",
                            (row['test_key'], row['section_name']))
        self._execute_query("DELETE FROM comm_sections WHERE id = %s", (section_pk,))
        return 1

    def get_comm_max_question_number(self, test_key, section_name):
        row = self._fetch_one(
            "SELECT MAX(question_number) AS m FROM comm_questions WHERE test_key = %s AND section_name = %s",
            (test_key, section_name))
        return row['m'] if row and row['m'] is not None else 0

    def insert_comm_question(self, data):
        self._execute_query("""
            INSERT INTO comm_questions
            (test_id, test_key, test_description_id, section_id, section_name, question_number,
             question_type, instruction_text, question_text, media_url, options_title,
             option_a, option_b, option_c, option_d, correct_option,
             recording_time_seconds, thinking_time_seconds, word_limit,
             correct_marks, negative_marks, question_level, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
        """, (data['test_id'], data['test_key'], data['test_description_id'], data['section_id'],
              data['section_name'], data['question_number'], data['question_type'],
              data.get('instruction_text'), data['question_text'], data.get('media_url'),
              data.get('options_title'), data.get('option_a'), data.get('option_b'),
              data.get('option_c'), data.get('option_d'), data.get('correct_option'),
              data.get('recording_time_seconds') or 0, data.get('thinking_time_seconds') or 0,
              data.get('word_limit') or 0, data.get('correct_marks') or 0,
              data.get('negative_marks') or 0, data.get('question_level') or 'Medium'))

    def insert_comm_questions_bulk(self, rows):
        conn = self.connection()
        cursor = conn.cursor()
        try:
            cursor.executemany("""
                INSERT INTO comm_questions
                (test_id, test_key, test_description_id, section_id, section_name, question_number,
                 question_type, instruction_text, question_text, media_url, options_title,
                 option_a, option_b, option_c, option_d, correct_option,
                 recording_time_seconds, thinking_time_seconds, word_limit,
                 correct_marks, negative_marks, question_level, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
            """, [(d['test_id'], d['test_key'], d['test_description_id'], d['section_id'], d['section_name'],
                   d['question_number'], d['question_type'], d.get('instruction_text'), d['question_text'],
                   d.get('media_url'), d.get('options_title'), d.get('option_a'), d.get('option_b'),
                   d.get('option_c'), d.get('option_d'), d.get('correct_option'),
                   d.get('recording_time_seconds') or 0, d.get('thinking_time_seconds') or 0,
                   d.get('word_limit') or 0, d.get('correct_marks') or 0, d.get('negative_marks') or 0,
                   d.get('question_level') or 'Medium') for d in rows])
            conn.commit()
            return len(rows)
        except mysql.connector.Error:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def get_question(self, qid):
        q_table = self._question_table_for_id(qid)
        return self._fetch_one(f"SELECT * FROM {q_table} WHERE id = %s", (qid,))

    def question_exists(self, qid):
        q_table = self._question_table_for_id(qid)
        return self._fetch_one(f"SELECT id FROM {q_table} WHERE id = %s LIMIT 1", (qid,)) is not None

    def update_image_question(self, qid, data):
        q_table = self._question_table_for_id(qid)
        query = f"""
            UPDATE {q_table}
            SET question_image = %s, option_regions = %s, question_type = %s,
                question_level = %s, correct_option = %s, correct_marks = %s,
                negative_marks = %s, updated_at = NOW()
            WHERE id = %s
        """
        self._execute_query(query, (
            data['question_image'], data['option_regions'], data['question_type'],
            data['question_level'], data['correct_option'], data['correct_marks'],
            data['negative_marks'], qid
        ))

    def delete_test_question(self, id):
        q_table = self._question_table_for_id(id)
        self._execute_query(f"DELETE FROM {q_table} WHERE id = %s", (id,))

    def questions_in_description(self, description_id, ids):
        _, q_table = self._tables_for_description_id(description_id)
        marks = ', '.join(['%s'] * len(ids))
        return self._fetch_all(
            f"SELECT id, section_id, section_name, question_number FROM {q_table} "
            f"WHERE test_description_id = %s AND id IN ({marks})", (description_id, *ids))

    def answers_for_questions(self, description_id, ids):
        _, q_table = self._tables_for_description_id(description_id)
        table = 'test_attempt_details' if q_table == 'test_questions' else 'comm_attempt_details'
        marks = ', '.join(['%s'] * len(ids))
        row = self._fetch_one(
            f"SELECT COUNT(*) AS answers, COUNT(DISTINCT email) AS students FROM {table} "
            f"WHERE question_id IN ({marks})", tuple(ids)) or {}
        return {'answers': int(row.get('answers') or 0), 'students': int(row.get('students') or 0)}

    def delete_questions(self, description_id, ids):
        _, q_table = self._tables_for_description_id(description_id)
        marks = ', '.join(['%s'] * len(ids))
        conn = self.connection()
        cursor = conn.cursor()
        try:
            cursor.execute(f"DELETE FROM {q_table} WHERE test_description_id = %s AND id IN ({marks})",
                           (description_id, *ids))
            deleted = cursor.rowcount
            conn.commit()
            return deleted
        except mysql.connector.Error:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    OFFSET = 1000000

    def _renumber(self, cursor, q_table, where, params):
        cursor.execute(f"UPDATE {q_table} SET question_number = question_number + %s WHERE {where}",
                       (self.OFFSET, *params))
        cursor.execute(f"""
            UPDATE {q_table} q
            JOIN (SELECT id, ROW_NUMBER() OVER (ORDER BY question_number, id) AS rn
                    FROM {q_table} WHERE {where}) x ON x.id = q.id
               SET q.question_number = x.rn
        """, params)

    def _transaction(self, work):
        conn = self.connection()
        cursor = conn.cursor(dictionary=True)
        try:
            conn.start_transaction()
            result = work(cursor)
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def renumber_section(self, description_id, section_id):
        _, q_table = self._tables_for_description_id(description_id)
        self._transaction(lambda cur: self._renumber(
            cur, q_table, "test_description_id = %s AND section_id = %s", (description_id, section_id)))

    def renumber_comm_section(self, test_key, section_name):
        self._transaction(lambda cur: self._renumber(
            cur, 'comm_questions', "test_key = %s AND section_name = %s", (test_key, section_name)))

    def update_marks(self, description_id, ids, correct_marks, negative_marks):
        _, q_table = self._tables_for_description_id(description_id)
        marks = ', '.join(['%s'] * len(ids))
        sets, params = [], []
        if correct_marks is not None:
            sets.append('correct_marks = %s'); params.append(correct_marks)
        if negative_marks is not None:
            sets.append('negative_marks = %s'); params.append(negative_marks)
        if not sets:
            return 0

        def work(cur):
            cur.execute(f"UPDATE {q_table} SET {', '.join(sets)}, updated_at = NOW() "
                        f"WHERE test_description_id = %s AND id IN ({marks})", (*params, description_id, *ids))
            return cur.rowcount
        return self._transaction(work)

    def move_questions(self, description_id, ids, target_id, target_name, sources):
        _, q_table = self._tables_for_description_id(description_id)
        marks = ', '.join(['%s'] * len(ids))

        def work(cur):
            cur.execute(f"SELECT COALESCE(MAX(question_number), 0) AS m FROM {q_table} "
                        f"WHERE test_description_id = %s AND section_id = %s", (description_id, target_id))
            start = int(cur.fetchone()['m'])
            cur.execute(f"SELECT id FROM {q_table} WHERE test_description_id = %s AND id IN ({marks}) "
                        f"ORDER BY section_id, question_number, id", (description_id, *ids))
            ordered = [r['id'] for r in cur.fetchall()]
            for n, qid in enumerate(ordered, 1):
                cur.execute(f"UPDATE {q_table} SET section_id = %s, section_name = %s, question_number = %s, "
                            f"updated_at = NOW() WHERE id = %s", (target_id, target_name, start + self.OFFSET + n, qid))
            for sid in set(sources) | {target_id}:
                self._renumber(cur, q_table, "test_description_id = %s AND section_id = %s", (description_id, sid))
            return len(ordered)
        return self._transaction(work)

    def move_comm_questions(self, test_key, ids, target):
        marks = ', '.join(['%s'] * len(ids))

        def work(cur):
            cur.execute("SELECT DISTINCT section_name FROM comm_questions WHERE test_key = %s AND id IN (" + marks + ")",
                        (test_key, *ids))
            sources = [r['section_name'] for r in cur.fetchall()]
            cur.execute("SELECT COALESCE(MAX(question_number), 0) AS m FROM comm_questions WHERE test_key = %s AND section_name = %s",
                        (test_key, target['section_name']))
            start = int(cur.fetchone()['m'])
            cur.execute("SELECT id FROM comm_questions WHERE test_key = %s AND id IN (" + marks + ") ORDER BY section_name, question_number, id",
                        (test_key, *ids))
            ordered = [r['id'] for r in cur.fetchall()]
            for n, qid in enumerate(ordered, 1):
                cur.execute("UPDATE comm_questions SET section_id = %s, section_name = %s, question_number = %s, updated_at = NOW() WHERE id = %s",
                            (target['section_id'], target['section_name'], start + self.OFFSET + n, qid))
            for name in set(sources) | {target['section_name']}:
                self._renumber(cur, 'comm_questions', "test_key = %s AND section_name = %s", (test_key, name))
            return len(ordered)
        return self._transaction(work)

    def rename_section(self, description_id, section_id, new_name):
        _, q_table = self._tables_for_description_id(description_id)

        def work(cur):
            cur.execute(f"UPDATE {q_table} SET section_name = %s, updated_at = NOW() "
                        f"WHERE test_description_id = %s AND section_id = %s", (new_name, description_id, section_id))
            return cur.rowcount
        return self._transaction(work)

    def update_comm_section(self, section_pk, title, instruction, duration):
        self._execute_query("""
            UPDATE comm_sections SET section_title = %s, section_instruction = %s, section_duration_seconds = %s
             WHERE id = %s
        """, (title, instruction, duration, section_pk))

    def sections_for_description(self, description_id):
        _, q_table = self._tables_for_description_id(description_id)
        return self._fetch_all(f"""
            SELECT section_id, MAX(section_name) AS section_name, COUNT(*) AS questions,
                   COALESCE(SUM(correct_marks), 0) AS marks
            FROM {q_table} WHERE test_description_id = %s
            GROUP BY section_id ORDER BY MIN(id)
        """, (description_id,))

    def get_comm_question(self, qid):
        return self._fetch_one("SELECT * FROM comm_questions WHERE id = %s", (qid,))

    def update_comm_question(self, qid, data):
        self._execute_query("""
            UPDATE comm_questions SET section_id = %s, section_name = %s, question_number = %s,
                   question_type = %s, instruction_text = %s, question_text = %s, media_url = %s,
                   options_title = %s, option_a = %s, option_b = %s, option_c = %s, option_d = %s,
                   correct_option = %s, recording_time_seconds = %s, thinking_time_seconds = %s,
                   word_limit = %s, correct_marks = %s, negative_marks = %s, question_level = %s,
                   updated_at = NOW()
             WHERE id = %s
        """, (data['section_id'], data['section_name'], data['question_number'], data['question_type'],
              data.get('instruction_text'), data['question_text'], data.get('media_url'),
              data.get('options_title'), data.get('option_a'), data.get('option_b'),
              data.get('option_c'), data.get('option_d'), data.get('correct_option'),
              data.get('recording_time_seconds') or 0, data.get('thinking_time_seconds') or 0,
              data.get('word_limit') or 0, data.get('correct_marks') or 0,
              data.get('negative_marks') or 0, data.get('question_level') or 'Medium', qid))

    def get_student_log_courses(self):
        query = """
            SELECT cc.code, MAX(c.name) AS name,
                   COUNT(DISTINCT utl.email) AS unique_students,
                   COUNT(*) AS total_attempts,
                   COUNT(DISTINCT utl.test_key) AS tests_attempted,
                   MAX(utl.start_time) AS last_activity
            FROM user_test_log utl
            JOIN course_content cc ON cc.section_id = utl.test_id
            LEFT JOIN courses c ON c.code = cc.code
            GROUP BY cc.code
            ORDER BY unique_students DESC
        """
        rows = self._fetch_all(query)
        logger.info(f"DB STUDENT LOGS: {len(rows)} course(s) with test activity")
        return rows

    def get_student_log_totals(self):
        row = self._fetch_one(
            "SELECT COUNT(DISTINCT email) AS unique_students, COUNT(*) AS total_attempts FROM user_test_log")
        return row or {'unique_students': 0, 'total_attempts': 0}

    def get_student_log_details(self, course_code):
        query = """
            SELECT utl.email, MAX(a.username) AS username,
                   COUNT(DISTINCT utl.test_key) AS tests_taken,
                   COUNT(*) AS total_attempts,
                   MIN(utl.start_time) AS first_activity,
                   MAX(utl.start_time) AS last_activity
            FROM user_test_log utl
            JOIN course_content cc ON cc.section_id = utl.test_id
            LEFT JOIN auth a ON a.email = utl.email
            WHERE cc.code = %s
            GROUP BY utl.email
            ORDER BY total_attempts DESC, last_activity DESC
        """
        rows = self._fetch_all(query, (course_code,))
        logger.info(f"DB STUDENT LOGS: {len(rows)} unique student(s) in {course_code!r}")
        return rows

    def get_feedback_courses(self):
        query = """
            SELECT cc.code, MAX(c.name) AS name, COUNT(tf.id) AS feedback_count
            FROM test_feedback tf
            JOIN course_content cc ON cc.section_id = tf.test_id
            LEFT JOIN courses c ON c.code = cc.code
            GROUP BY cc.code
            ORDER BY cc.code
        """
        rows = self._fetch_all(query)
        logger.info(f"DB FEEDBACK: {len(rows)} course(s) with feedback")
        return rows

    def get_feedback_contents(self, course_code):
        query = """
            SELECT cc.section_id, MAX(cc.title) AS title, MAX(cc.subtitle) AS subtitle,
                   MAX(cc.label) AS label, MAX(cc.section) AS section,
                   COUNT(tf.id) AS feedback_count, MAX(tf.submission_time) AS last_feedback
            FROM test_feedback tf
            JOIN course_content cc ON cc.section_id = tf.test_id
            WHERE cc.code = %s
            GROUP BY cc.section_id
            ORDER BY MAX(tf.submission_time) DESC
        """
        rows = self._fetch_all(query, (course_code,))
        logger.info(f"DB FEEDBACK: {len(rows)} content block(s) with feedback in {course_code!r}")
        return rows

    def get_feedback_tests(self, course_code, section_id=None):
        query = """
            SELECT tf.test_key, MAX(td.subject_title) AS subject_title,
                   MAX(td.subject_subtitle) AS subject_subtitle,
                   MAX(COALESCE(td.access_label, 'inherit')) AS access_label,
                   COUNT(tf.id) AS feedback_count, MAX(tf.submission_time) AS last_feedback
            FROM test_feedback tf
            JOIN course_content cc ON cc.section_id = tf.test_id
            LEFT JOIN test_description td ON td.test_key = tf.test_key
            WHERE cc.code = %s
        """
        params = [course_code]
        if section_id:
            query += " AND cc.section_id = %s"
            params.append(section_id)
        query += " GROUP BY tf.test_key ORDER BY MAX(tf.submission_time) DESC"
        rows = self._fetch_all(query, tuple(params))
        logger.info(f"DB FEEDBACK: {len(rows)} test(s) with feedback in {course_code!r}/{section_id!r}")
        return rows

    def get_feedback_for_test(self, test_key):
        query = """
            SELECT tf.*, a.username, td.subject_title, td.subject_subtitle
            FROM test_feedback tf
            LEFT JOIN auth a ON a.email = tf.email
            LEFT JOIN test_description td ON td.test_key = tf.test_key
            WHERE tf.test_key = %s
            ORDER BY tf.submission_time DESC
        """
        rows = self._fetch_all(query, (test_key,))
        logger.info(f"DB FEEDBACK: {len(rows)} feedback row(s) for test {test_key!r}")
        return rows

    def feedback_email_exists(self, email):
        row = self._fetch_one("SELECT id FROM test_feedback WHERE email = %s LIMIT 1", (email,))
        return row is not None

    def delete_feedback_entry(self, feedback_id):
        self._execute_query("DELETE FROM test_feedback WHERE id = %s", (feedback_id,))
        logger.warning(f"DB FEEDBACK: deleted feedback id={feedback_id}")
        return True

    def get_all_feedback_entries(self, page=1, per_page=50):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            offset = (page - 1) * per_page
            query = "SELECT SQL_CALC_FOUND_ROWS * FROM test_feedback ORDER BY submission_time DESC LIMIT %s OFFSET %s"
            cursor.execute(query, (per_page, offset))
            feedbacks = cursor.fetchall()
            cursor.execute("SELECT FOUND_ROWS() as total")
            total = cursor.fetchone()['total']
            return feedbacks, total
        except Exception as e:
            logger.exception("Error fetching all feedback entries")
            return [], 0
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def truncate_all_feedback(self):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor()
            cursor.execute("TRUNCATE TABLE test_feedback")
            db.commit()
            logger.info("Successfully truncated test_feedback table.")
            return True
        except Exception as e:
            logger.exception("Error truncating test_feedback table")
            if db: db.rollback()
            return False
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def get_selected_user_test_logs(self, page=1, per_page=50):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            offset = (page - 1) * per_page
            query = "SELECT SQL_CALC_FOUND_ROWS email, username, test_id, test_key, start_time, end_time FROM user_test_log ORDER BY start_time DESC LIMIT %s OFFSET %s"
            cursor.execute(query, (per_page, offset))
            logs = cursor.fetchall()
            cursor.execute("SELECT FOUND_ROWS() as total")
            total = cursor.fetchone()['total']
            return logs, total
        except Exception as e:
            logger.exception("Error fetching selected user test logs")
            return [], 0
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def count_unique_test_attempts(self):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor()
            query = "SELECT COUNT(DISTINCT email) FROM user_test_log"
            cursor.execute(query)
            result = cursor.fetchone()
            count = result[0] if result else 0
            logger.info(f"Counted {count} unique test attempts by email.")
            return count
        except Exception as e:
            logger.exception("Error counting unique test attempts")
            return 0
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def _fetch_one(self, query, params=None):
        conn = self.connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(query, params or ())
            return cursor.fetchone()
        finally:
            cursor.close()
            conn.close()

    def _fetch_all(self, query, params=None):
        conn = self.connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(query, params or ())
            return cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

    def _execute_query(self, query, params=None):
        conn = self.connection()
        cursor = conn.cursor()
        try:
            cursor.execute(query, params or ())
            conn.commit()
        except mysql.connector.Error as err:
            conn.rollback()
            raise err
        finally:
            cursor.close()
            conn.close()