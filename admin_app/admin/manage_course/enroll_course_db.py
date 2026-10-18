import logging
import secrets
import mysql.connector
from config import Config
from contextlib import closing

logger = logging.getLogger(__name__)

class UserOperation:
    def connection(self):
        from admin.db_pool import get_connection
        return get_connection()

    def count_courses(self):
        try:
            with closing(self.connection()) as db, closing(db.cursor()) as cursor:
                cursor.execute("SELECT COUNT(*) FROM courses")
                result = cursor.fetchone()
                return result[0] if result else 0
        except mysql.connector.Error as err:
            logger.error(f"Error counting courses: {err}")
            return 0

    def get_courses_paginated(self, limit=10, offset=0):
        try:
            with closing(self.connection()) as db, closing(db.cursor(dictionary=True, buffered=True)) as cursor:
                query = "SELECT code, name, description FROM courses ORDER BY name ASC LIMIT %s OFFSET %s"
                cursor.execute(query, (limit, offset))
                results = cursor.fetchall()
                logger.info(f"Fetched {len(results)} courses with limit {limit} and offset {offset}.")
                return results
        except mysql.connector.Error as err:
            logger.error(f"Error fetching paginated courses: {err}")
            raise err

    def get_all_courses(self):
        try:
            with closing(self.connection()) as db, closing(db.cursor(dictionary=True, buffered=True)) as cursor:
                cursor.execute("SELECT code, name, subgroup, description FROM courses ORDER BY name ASC, subgroup ASC")
                results = cursor.fetchall()
                logger.info("Fetched all courses successfully.")
                return results
        except mysql.connector.Error as err:
            logger.error(f"Error fetching all courses: {err}")
            raise err

    def get_course_by_code(self, code):
        try:
            with closing(self.connection()) as db, closing(db.cursor(dictionary=True, buffered=True)) as cursor:
                cursor.execute("SELECT code, name, subgroup, description FROM courses WHERE code = %s", (code,))
                result = cursor.fetchone()
                return result
        except mysql.connector.Error as err:
            logger.error(f"Error fetching course '{code}': {err}")
            return None

    def insert_course(self, code, name, description, subgroup=None):
        try:
            with closing(self.connection()) as db, closing(db.cursor(buffered=True)) as cursor:
                cursor.execute(
                    "INSERT INTO courses (code, name, subgroup, description, guest_access_code) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (code, name, subgroup or None, description, secrets.token_hex(8))
                )
                db.commit()
                return True
        except mysql.connector.Error as err:
            logger.error(f"Error inserting course '{code}': {err}")
            return False

    def update_course(self, code, name, description, subgroup=None):
        try:
            with closing(self.connection()) as db, closing(db.cursor(buffered=True)) as cursor:
                cursor.execute(
                    "UPDATE courses SET name = %s, subgroup = %s, description = %s WHERE code = %s",
                    (name, subgroup or None, description, code)
                )
                db.commit()
                return cursor.rowcount > 0
        except mysql.connector.Error as err:
            logger.error(f"Error updating course '{code}': {err}")
            return False

    USAGE_CHECKS = (
        ('enrolled student(s)', "SELECT COUNT(*) FROM enrollment WHERE code = %s"),
        ('purchase(s)', "SELECT COUNT(*) FROM purchase WHERE course_code = %s"),
        ('premium subscription(s)', "SELECT COUNT(*) FROM pcp_subscriptions WHERE course_code = %s AND status <> 'failed'"),
        ('payment order(s)', "SELECT COUNT(*) FROM content_orders WHERE course_code = %s AND status <> 'failed'"),
        ('enrolment fee payment(s)', "SELECT COUNT(*) FROM enrollment_payment WHERE course_code = %s"),
        ('content item(s)', "SELECT COUNT(*) FROM course_content WHERE code = %s"),
    )

    EXTRA_CHECKS = (
        ('premium plan(s)', "SELECT COUNT(*) FROM premium_plans WHERE code = %s"),
        ('premium page text', "SELECT COUNT(*) FROM premium_catalog WHERE code = %s"),
    )

    def _count(self, cursor, checks, code):
        counts = {}
        for label, sql in checks:
            cursor.execute(sql, (code,))
            found = cursor.fetchone()
            if found and found[0]:
                counts[label] = int(found[0])
        return counts

    def course_usage(self, code):
        try:
            with closing(self.connection()) as db, closing(db.cursor(buffered=True)) as cursor:
                return self._count(cursor, self.USAGE_CHECKS, code)
        except mysql.connector.Error as err:
            logger.error(f"Could not check what uses course '{code}': {err}")
            return {'unknown use': 1}

    def course_extras(self, code):
        try:
            with closing(self.connection()) as db, closing(db.cursor(buffered=True)) as cursor:
                return self._count(cursor, self.EXTRA_CHECKS, code)
        except mysql.connector.Error as err:
            logger.error(f"Could not check premium setup of course '{code}': {err}")
            return {}

    def delete_course(self, code):
        try:
            with closing(self.connection()) as db, closing(db.cursor(buffered=True)) as cursor:
                db.start_transaction()
                cursor.execute("SELECT code FROM courses WHERE code = %s FOR UPDATE", (code,))
                if not cursor.fetchone():
                    db.rollback()
                    return {'status': 'missing'}
                used = self._count(cursor, self.USAGE_CHECKS, code)
                if used:
                    db.rollback()
                    return {'status': 'in_use', 'used': used}
                removed = self._count(cursor, self.EXTRA_CHECKS, code)
                cursor.execute("DELETE FROM premium_plans WHERE code = %s", (code,))
                cursor.execute("DELETE FROM premium_catalog WHERE code = %s", (code,))
                cursor.execute("DELETE FROM courses WHERE code = %s", (code,))
                deleted = cursor.rowcount
                db.commit()
                return {'status': 'deleted' if deleted else 'missing', 'removed': removed}
        except mysql.connector.Error as err:
            logger.error(f"Error deleting course '{code}': {err}")
            return {'status': 'error'}
