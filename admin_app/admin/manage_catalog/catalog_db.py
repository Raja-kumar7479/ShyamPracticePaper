import logging

import mysql.connector

logger = logging.getLogger(__name__)

LIVE_PORTALS = {
    'competitive': 'Competitive exam portal (mock tests)',
    'coding': 'Coding portal (programming rounds)',
    'communication': 'Communication portal (speaking / writing)',
    'coding_practice': 'Coding practice portal (LeetCode-style problems)',
    'tcs': 'TCS portal (aptitude sections + coding section)',
    'notes': 'Study notes',
}

LEGACY_PORTALS = {'lecture', 'community', 'blog'}

EDITORS = {
    'competitive': 'Competitive question editor',
    'coding': 'Coding question editor',
    'communication': 'Communication question editor',
}


class CatalogDB:
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
            logger.exception('CATALOG: read failed')
            return []
        finally:
            if cur: cur.close()
            if conn: conn.close()

    def _scalar(self, sql, params=None):
        rows = self._fetch_all(sql, params)
        return list(rows[0].values())[0] if rows else 0

    def _execute(self, sql, params=None):
        conn = cur = None
        try:
            conn = self.connection()
            cur = conn.cursor()
            cur.execute(sql, params or ())
            conn.commit()
            return cur.rowcount
        except mysql.connector.Error:
            if conn:
                conn.rollback()
            raise
        finally:
            if cur: cur.close()
            if conn: conn.close()

    def groups(self):
        return self._fetch_all("""
            SELECT g.*,
                   (SELECT COUNT(*) FROM course_group_codes c WHERE c.group_name = g.group_name) AS code_count,
                   (SELECT COUNT(*) FROM course_group_sections s WHERE s.group_name = g.group_name) AS section_count,
                   (SELECT COUNT(*) FROM courses co WHERE co.name = g.group_name) AS course_count
            FROM course_groups g ORDER BY g.position, g.group_name
        """)

    def codes(self):
        return self._fetch_all("""
            SELECT c.*,
                   (SELECT COUNT(*) FROM courses co WHERE co.code = c.code) AS course_count
            FROM course_group_codes c ORDER BY c.group_name, c.position, c.code
        """)

    def sections(self):
        return self._fetch_all("""
            SELECT s.*,
                   (SELECT COUNT(*) FROM course_content cc WHERE cc.section = s.section_key) AS content_count,
                   (SELECT COUNT(*) FROM course_group_sections g WHERE g.section_key = s.section_key) AS group_count
            FROM content_sections s ORDER BY s.position, s.section_key
        """)

    def group_sections(self):
        rows = self._fetch_all("SELECT group_name, section_key FROM course_group_sections")
        out = {}
        for r in rows:
            out.setdefault(r['group_name'], []).append(r['section_key'])
        return out

    def group_exists(self, name):
        return self._scalar("SELECT COUNT(*) FROM course_groups WHERE group_name = %s", (name,)) > 0

    def add_group(self, name, label, position, platform='competitive'):
        return self._execute(
            "INSERT INTO course_groups (group_name, label, position, platform) VALUES (%s, %s, %s, %s)",
            (name, label, position, platform))

    def update_group(self, name, label, position, is_active, platform=None):
        if platform:
            return self._execute(
                "UPDATE course_groups SET label=%s, position=%s, is_active=%s, platform=%s WHERE group_name=%s",
                (label, position, 1 if is_active else 0, platform, name))
        return self._execute(
            "UPDATE course_groups SET label=%s, position=%s, is_active=%s WHERE group_name=%s",
            (label, position, 1 if is_active else 0, name))

    def group_platform(self, name):
        return self._scalar("SELECT platform FROM course_groups WHERE group_name = %s", (name,)) or 'competitive'

    def section_portal(self, key):
        return self._scalar("SELECT portal FROM content_sections WHERE section_key = %s", (key,))

    def group_usage(self, name):
        return self._scalar("SELECT COUNT(*) FROM courses WHERE name = %s", (name,))

    def group_code_count(self, name):
        return self._scalar("SELECT COUNT(*) FROM course_group_codes WHERE group_name = %s", (name,))

    def delete_group(self, name):
        return self._execute("DELETE FROM course_groups WHERE group_name = %s", (name,))

    def code_exists(self, code):
        return self._scalar("SELECT COUNT(*) FROM course_group_codes WHERE code = %s", (code,)) > 0

    def code_pair_exists(self, group_name, code):
        return self._scalar(
            "SELECT COUNT(*) FROM course_group_codes WHERE group_name = %s AND code = %s",
            (group_name, code)) > 0

    def add_code(self, group_name, code, label, position):
        return self._execute(
            "INSERT INTO course_group_codes (group_name, code, label, position) VALUES (%s,%s,%s,%s)",
            (group_name, code, label, position))

    def code_usage(self, code):
        return self._scalar("SELECT COUNT(*) FROM courses WHERE code = %s", (code,))

    def delete_code(self, group_name, code):
        return self._execute(
            "DELETE FROM course_group_codes WHERE group_name = %s AND code = %s", (group_name, code))

    def section_exists(self, key):
        return self._scalar("SELECT COUNT(*) FROM content_sections WHERE section_key = %s", (key,)) > 0

    def add_section(self, key, label, help_text, portal, editor, is_available, position):
        return self._execute("""
            INSERT INTO content_sections
              (section_key, label, help_text, portal, editor, is_available, position)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (key, label, help_text, portal or None, editor or None,
              1 if is_available else 0, position))

    def update_section(self, key, label, help_text, portal, editor, is_available, position):
        return self._execute("""
            UPDATE content_sections
               SET label=%s, help_text=%s, portal=%s, editor=%s, is_available=%s, position=%s
             WHERE section_key=%s
        """, (label, help_text, portal or None, editor or None,
              1 if is_available else 0, position, key))

    def section_usage(self, key):
        return self._scalar("SELECT COUNT(*) FROM course_content WHERE section = %s", (key,))

    def delete_section(self, key):
        return self._execute("DELETE FROM content_sections WHERE section_key = %s", (key,))

    def link_section(self, group_name, section_key, position=0):
        return self._execute("""
            INSERT INTO course_group_sections (group_name, section_key, position)
            VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE position = VALUES(position)
        """, (group_name, section_key, position))

    def unlink_section(self, group_name, section_key):
        return self._execute(
            "DELETE FROM course_group_sections WHERE group_name = %s AND section_key = %s",
            (group_name, section_key))

    def link_usage(self, group_name, section_key):
        return self._scalar("""
            SELECT COUNT(*) FROM course_content cc
              JOIN courses c ON c.code = cc.code
             WHERE c.name = %s AND cc.section = %s
        """, (group_name, section_key))
