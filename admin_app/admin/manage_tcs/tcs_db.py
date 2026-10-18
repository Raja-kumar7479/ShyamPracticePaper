import logging

import mysql.connector

logger = logging.getLogger(__name__)


class TcsDB:
    def connection(self):
        from admin.db_pool import get_connection
        return get_connection()

    def _fetch_all(self, sql, params=None):
        conn = cur = None
        try:
            conn = self.connection()
            cur = conn.cursor(dictionary=True)
            cur.execute(sql, params or ())
            return cur.fetchall()
        except mysql.connector.Error:
            logger.exception('TCS: read failed')
            return []
        finally:
            if cur: cur.close()
            if conn: conn.close()

    def _fetch_one(self, sql, params=None):
        rows = self._fetch_all(sql, params)
        return rows[0] if rows else None

    def _execute(self, sql, params=None):
        conn = cur = None
        try:
            conn = self.connection()
            cur = conn.cursor()
            cur.execute(sql, params or ())
            conn.commit()
            return cur.lastrowid or cur.rowcount
        except mysql.connector.Error:
            if conn:
                conn.rollback()
            raise
        finally:
            if cur: cur.close()
            if conn: conn.close()

    def exams(self):
        return self._fetch_all("""
            SELECT e.*, cc.title AS block_title, cc.label AS block_label, cc.name AS course_name,
                   td.subject_title AS aptitude_title, td.total_duration_minutes AS aptitude_minutes,
                   ct.title AS coding_title, ct.total_duration_min AS coding_minutes,
                   ct.is_published AS coding_published,
                   (SELECT COUNT(*) FROM tcs_attempts a WHERE a.tcs_exam_id = e.id) AS attempt_count,
                   (SELECT COUNT(*) FROM tcs_attempts a WHERE a.tcs_exam_id = e.id AND a.stage = 'completed') AS completed_count
            FROM tcs_exams e
            LEFT JOIN course_content cc ON cc.section_id = e.section_id
            LEFT JOIN test_description td ON td.test_key = e.aptitude_test_key
            LEFT JOIN cp_tests ct ON ct.id = e.coding_test_id
            ORDER BY e.created_at DESC
        """)

    def get_exam(self, exam_id):
        return self._fetch_one("SELECT * FROM tcs_exams WHERE id = %s", (exam_id,))

    def tcs_blocks(self):
        return self._fetch_all("""
            SELECT section_id, code, name AS course_name, title, label, status
            FROM course_content
            WHERE section = 'tcs_test'
            ORDER BY code, title
        """)

    def aptitude_tests(self):
        return self._fetch_all("""
            SELECT td.test_key, td.subject_title, td.subject_subtitle, td.total_questions,
                   td.total_marks, td.total_duration_minutes, td.test_id,
                   cc.code, cc.title AS block_title, cc.section,
                   (SELECT COUNT(DISTINCT tq.section_name) FROM test_questions tq WHERE tq.test_key = td.test_key) AS section_count,
                   (SELECT COUNT(*) FROM test_questions tq WHERE tq.test_key = td.test_key) AS question_count
            FROM test_description td
            LEFT JOIN course_content cc ON cc.section_id = td.test_id
            ORDER BY cc.code, td.subject_title
        """)

    def coding_tests(self):
        return self._fetch_all("""
            SELECT t.id, t.slug, t.title, t.total_duration_min, t.is_published, t.code, t.test_key,
                   (SELECT COUNT(*) FROM cp_sections s WHERE s.test_id = t.id) AS section_count,
                   (SELECT COUNT(*) FROM cp_questions q JOIN cp_sections s ON s.id = q.section_id WHERE s.test_id = t.id) AS question_count
            FROM cp_tests t
            ORDER BY t.created_at DESC
        """)

    def block_code(self, section_id):
        row = self._fetch_one("SELECT code FROM course_content WHERE section_id = %s", (section_id,))
        return row['code'] if row else None

    def aptitude_exists(self, test_key):
        return self._fetch_one("SELECT 1 FROM test_description WHERE test_key = %s", (test_key,)) is not None

    def coding_exists(self, test_id):
        return self._fetch_one("SELECT 1 FROM cp_tests WHERE id = %s", (test_id,)) is not None

    def add_exam(self, section_id, code, title, subtitle, aptitude_test_key, coding_test_id, coding_label, is_published):
        return self._execute("""
            INSERT INTO tcs_exams (section_id, code, title, subtitle, aptitude_test_key, coding_test_id, coding_label, is_published)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (section_id, code, title, subtitle, aptitude_test_key, coding_test_id, coding_label, int(bool(is_published))))

    def update_exam(self, exam_id, section_id, code, title, subtitle, aptitude_test_key, coding_test_id, coding_label, is_published):
        return self._execute("""
            UPDATE tcs_exams
               SET section_id = %s, code = %s, title = %s, subtitle = %s,
                   aptitude_test_key = %s, coding_test_id = %s, coding_label = %s, is_published = %s
             WHERE id = %s
        """, (section_id, code, title, subtitle, aptitude_test_key, coding_test_id, coding_label,
              int(bool(is_published)), exam_id))

    def set_published(self, exam_id, is_published):
        return self._execute("UPDATE tcs_exams SET is_published = %s WHERE id = %s",
                             (int(bool(is_published)), exam_id))

    def delete_exam(self, exam_id):
        return self._execute("DELETE FROM tcs_exams WHERE id = %s", (exam_id,))

    def attempt_count(self, exam_id):
        row = self._fetch_one("SELECT COUNT(*) AS n FROM tcs_attempts WHERE tcs_exam_id = %s", (exam_id,))
        return int(row['n']) if row else 0
