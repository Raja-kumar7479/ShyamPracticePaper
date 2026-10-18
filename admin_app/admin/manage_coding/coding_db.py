import logging

import mysql.connector

logger = logging.getLogger(__name__)

SECTION_TYPES = ('coding', 'sql', 'web')
LANGUAGES = ('python', 'java', 'c', 'cpp', 'csharp', 'javascript')
ASSERTION_KINDS = ('element_exists', 'text_equals', 'text_contains',
                   'attr_equals', 'css_property', 'count_equals')


class CodingOperation:
    def connection(self):
        from admin.db_pool import get_connection
        return get_connection()

    def _fetch_all(self, query, params=None):
        conn = cur = None
        try:
            conn = self.connection()
            cur = conn.cursor(dictionary=True)
            cur.execute(query, params or ())
            return cur.fetchall()
        except mysql.connector.Error:
            logger.exception("CODING DB: fetch failed")
            return []
        finally:
            if cur: cur.close()
            if conn: conn.close()

    def _fetch_one(self, query, params=None):
        rows = self._fetch_all(query, params)
        return rows[0] if rows else None

    def _execute(self, query, params=None, last_id=False):
        conn = cur = None
        try:
            conn = self.connection()
            cur = conn.cursor()
            cur.execute(query, params or ())
            result = cur.lastrowid if last_id else cur.rowcount
            conn.commit()
            return result
        except mysql.connector.Error:
            if conn:
                conn.rollback()
            raise
        finally:
            if cur: cur.close()
            if conn: conn.close()

    def set_test_languages(self, test_id, languages):
        value = ','.join(languages) if languages else None
        return self._execute("UPDATE cp_tests SET allowed_languages = %s WHERE id = %s",
                             (value, test_id))

    def list_tests(self):
        return self._fetch_all("""
            SELECT t.*,
                   (SELECT COUNT(*) FROM cp_sections s WHERE s.test_id = t.id) AS section_count,
                   (SELECT COUNT(*) FROM cp_questions q
                     JOIN cp_sections s2 ON s2.id = q.section_id
                    WHERE s2.test_id = t.id) AS question_count
            FROM cp_tests t ORDER BY t.created_at DESC
        """)

    def get_test(self, test_id):
        return self._fetch_one("SELECT * FROM cp_tests WHERE id = %s", (test_id,))

    def slug_exists(self, slug):
        return self._fetch_one("SELECT id FROM cp_tests WHERE slug = %s", (slug,)) is not None

    def create_test(self, data):
        return self._execute("""
            INSERT INTO cp_tests (slug, title, description, total_duration_min, is_published)
            VALUES (%s, %s, %s, %s, %s)
        """, (data['slug'], data['title'], data.get('description'),
              data['total_duration_min'], 1 if data.get('is_published') else 0), last_id=True)

    def update_test(self, test_id, data):
        return self._execute("""
            UPDATE cp_tests SET title=%s, description=%s, total_duration_min=%s, is_published=%s
            WHERE id=%s
        """, (data['title'], data.get('description'), data['total_duration_min'],
              1 if data.get('is_published') else 0, test_id))

    def _purge_test_children(self, test_ids):
        if not test_ids:
            return
        marks = ','.join(['%s'] * len(test_ids))
        self._execute(f"DELETE FROM cp_questions WHERE section_id IN "
                      f"(SELECT id FROM cp_sections WHERE test_id IN ({marks}))", tuple(test_ids))
        self._execute(f"DELETE FROM cp_sections WHERE test_id IN ({marks})", tuple(test_ids))

    def delete_test(self, test_id):
        self._purge_test_children([test_id])
        return self._execute("DELETE FROM cp_tests WHERE id = %s", (test_id,))

    def delete_tests_by_key(self, test_key):
        rows = self._fetch_all("SELECT id FROM cp_tests WHERE test_key = %s", (test_key,))
        ids = [r['id'] for r in rows]
        if not ids:
            return 0
        self._purge_test_children(ids)
        marks = ','.join(['%s'] * len(ids))
        return self._execute(f"DELETE FROM cp_tests WHERE id IN ({marks})", tuple(ids))

    def list_sections(self, test_id):
        return self._fetch_all("""
            SELECT s.*, (SELECT COUNT(*) FROM cp_questions q WHERE q.section_id = s.id) AS question_count
            FROM cp_sections s WHERE s.test_id = %s ORDER BY s.position, s.id
        """, (test_id,))

    def get_section(self, section_id):
        return self._fetch_one("""
            SELECT s.*, t.title AS test_title, t.slug AS test_slug
            FROM cp_sections s JOIN cp_tests t ON t.id = s.test_id
            WHERE s.id = %s
        """, (section_id,))

    def create_section(self, test_id, title, section_type, duration_min):
        rows = self._fetch_all("SELECT COALESCE(MAX(position),0)+1 AS p FROM cp_sections WHERE test_id=%s",
                               (test_id,))
        pos = rows[0]['p'] if rows else 1
        return self._execute("""
            INSERT INTO cp_sections (test_id, title, section_type, duration_min, position)
            VALUES (%s, %s, %s, %s, %s)
        """, (test_id, title, section_type, duration_min, pos), last_id=True)

    def delete_section(self, section_id):
        self._execute("DELETE FROM cp_questions WHERE section_id = %s", (section_id,))
        return self._execute("DELETE FROM cp_sections WHERE id = %s", (section_id,))

    def list_questions(self, section_id):
        return self._fetch_all("""
            SELECT q.*,
                   (SELECT COUNT(*) FROM cp_testcases tc WHERE tc.question_id = q.id) AS testcase_count,
                   (SELECT COUNT(*) FROM cp_web_assertions wa WHERE wa.question_id = q.id) AS assertion_count
            FROM cp_questions q WHERE q.section_id = %s ORDER BY q.position, q.id
        """, (section_id,))

    def get_question(self, question_id):
        return self._fetch_one("""
            SELECT q.*, s.section_type, s.title AS section_title, s.test_id
            FROM cp_questions q JOIN cp_sections s ON s.id = q.section_id
            WHERE q.id = %s
        """, (question_id,))

    def next_position(self, section_id):
        rows = self._fetch_all("SELECT COALESCE(MAX(position),0)+1 AS p FROM cp_questions WHERE section_id=%s",
                               (section_id,))
        return rows[0]['p'] if rows else 1

    def create_question(self, data):
        return self._execute("""
            INSERT INTO cp_questions
              (section_id, position, title, statement_html, input_spec, example_html,
               statement_image, input_image, example_image,
               marks, difficulty, time_limit_sec, memory_limit,
               allowed_languages, output_spec, compare_mode, float_tolerance,
               schema_image_path, sandbox_schema_sql, solution_query, ordered_comparison,
               starter_html, starter_css, starter_js)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            data['section_id'], data['position'], data['title'],
            data.get('statement_html'), data.get('input_spec'), data.get('example_html'),
            data.get('statement_image'), data.get('input_image'), data.get('example_image'),
            data.get('marks', 10), data.get('difficulty', 'Medium'),
            data.get('time_limit_sec', 10), data.get('memory_limit', '512m'),
            data.get('allowed_languages'), data.get('output_spec'),
            data.get('compare_mode', 'exact'), data.get('float_tolerance'),
            data.get('schema_image_path'), data.get('sandbox_schema_sql'),
            data.get('solution_query'), 1 if data.get('ordered_comparison') else 0,
            data.get('starter_html'), data.get('starter_css'), data.get('starter_js'),
        ), last_id=True)

    UPDATABLE = ('title', 'statement_html', 'input_spec', 'example_html',
                 'statement_image', 'input_image', 'example_image',
                 'marks', 'difficulty', 'time_limit_sec', 'memory_limit',
                 'allowed_languages', 'output_spec', 'compare_mode', 'float_tolerance',
                 'schema_image_path',
                 'sandbox_schema_sql', 'solution_query', 'ordered_comparison',
                 'starter_html', 'starter_css', 'starter_js', 'position')

    def update_question(self, question_id, data):
        fields = [c for c in self.UPDATABLE if c in data]
        if not fields:
            return 0
        assigns = ', '.join(f"{c} = %s" for c in fields)
        params = tuple(data[c] for c in fields) + (question_id,)
        return self._execute(f"UPDATE cp_questions SET {assigns} WHERE id = %s", params)

    def delete_question(self, question_id):
        return self._execute("DELETE FROM cp_questions WHERE id = %s", (question_id,))

    def list_testcases(self, question_id):
        return self._fetch_all(
            "SELECT * FROM cp_testcases WHERE question_id = %s ORDER BY position, id",
            (question_id,))

    def replace_testcases(self, question_id, cases):
        conn = cur = None
        try:
            conn = self.connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM cp_testcases WHERE question_id = %s", (question_id,))
            if cases:
                cur.executemany("""
                    INSERT INTO cp_testcases (question_id, input_text, expected_output, is_hidden, position)
                    VALUES (%s, %s, %s, %s, %s)
                """, [(question_id, c.get('input_text', ''), c.get('expected_output', ''),
                       1 if c.get('is_hidden') else 0, i + 1) for i, c in enumerate(cases)])
            conn.commit()
            return len(cases)
        except mysql.connector.Error:
            if conn:
                conn.rollback()
            raise
        finally:
            if cur: cur.close()
            if conn: conn.close()

    def list_templates(self, question_id):
        return self._fetch_all(
            "SELECT * FROM cp_question_templates WHERE question_id = %s", (question_id,))

    def replace_templates(self, question_id, templates):
        conn = cur = None
        try:
            conn = self.connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM cp_question_templates WHERE question_id = %s", (question_id,))
            rows = [(question_id, lang, code) for lang, code in (templates or {}).items()
                    if lang in LANGUAGES and (code or '').strip()]
            if rows:
                cur.executemany("""
                    INSERT INTO cp_question_templates (question_id, language, template_code)
                    VALUES (%s, %s, %s)
                """, rows)
            conn.commit()
            return len(rows)
        except mysql.connector.Error:
            if conn:
                conn.rollback()
            raise
        finally:
            if cur: cur.close()
            if conn: conn.close()

    def list_assertions(self, question_id):
        return self._fetch_all(
            "SELECT * FROM cp_web_assertions WHERE question_id = %s ORDER BY position, id",
            (question_id,))

    def replace_assertions(self, question_id, assertions):
        conn = cur = None
        try:
            conn = self.connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM cp_web_assertions WHERE question_id = %s", (question_id,))
            rows = []
            for i, a in enumerate(assertions or []):
                kind = (a.get('kind') or '').strip()
                if kind not in ASSERTION_KINDS or not (a.get('selector') or '').strip():
                    continue
                rows.append((question_id, kind, a['selector'].strip(),
                             a.get('property_name') or None, a.get('expected_value') or None,
                             a.get('message') or None, 1 if a.get('is_hidden') else 0, i + 1))
            if rows:
                cur.executemany("""
                    INSERT INTO cp_web_assertions
                      (question_id, kind, selector, property_name, expected_value, message, is_hidden, position)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """, rows)
            conn.commit()
            return len(rows)
        except mysql.connector.Error:
            if conn:
                conn.rollback()
            raise
        finally:
            if cur: cur.close()
            if conn: conn.close()
