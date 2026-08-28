import mysql.connector
from mysql.connector import Error
from config import Config
import logging

logger = logging.getLogger(__name__)

class UserOperation:
    def connection(self):
        try:
            conn = mysql.connector.connect(
                host=Config.DATABASE_HOST,
                user=Config.DATABASE_USER,
                password=Config.DATABASE_PASSWORD,
                database=Config.DATABASE_NAME
            )
            return conn
        except Error as e:
            logger.critical(f"DATABASE CONNECTION ERROR: {e}")
            raise e

    def get_course_groups(self):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            cursor.execute("SELECT DISTINCT name FROM courses ORDER BY name")
            result = cursor.fetchall()
            return result
        except Exception as e:
            logger.error(f"DB Error fetching course groups: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def get_groups_with_counts(self):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            cursor.execute("SELECT name, subgroup FROM courses")
            groups = {}
            for row in cursor.fetchall():
                bucket = groups.setdefault(row['name'], {'course_count': 0, 'subs': {}})
                bucket['course_count'] += 1
                sub = (row['subgroup'] or '').strip()
                if sub:
                    bucket['subs'][sub] = bucket['subs'].get(sub, 0) + 1
            return [{'name': name,
                     'course_count': data['course_count'],
                     'subgroup_count': sum(1 for n in data['subs'].values() if n > 1)}
                    for name, data in sorted(groups.items(), key=lambda kv: kv[0].lower())]
        except Exception as e:
            logger.error(f"DB Error fetching groups with counts: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def get_subgroups_for_group(self, group_name):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            query = ("SELECT subgroup, COUNT(*) AS course_count FROM courses "
                     "WHERE name = %s AND subgroup IS NOT NULL AND subgroup <> '' "
                     "GROUP BY subgroup ORDER BY subgroup ASC")
            cursor.execute(query, (group_name,))
            return [{'subgroup': row['subgroup'], 'course_count': int(row['course_count'])}
                    for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"DB Error fetching subgroups for group {group_name}: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def get_courses_in_group(self, group_name):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            cursor.execute(
                "SELECT code, name, subgroup, description FROM courses "
                "WHERE name = %s ORDER BY code ASC",
                (group_name,)
            )
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"DB Error fetching all courses for group {group_name}: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def get_courses_by_group(self, group_name, subgroup=None):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            if subgroup:
                query = "SELECT code, name, subgroup, description FROM courses WHERE name = %s AND subgroup = %s ORDER BY code ASC"
                params = (group_name, subgroup)
            else:
                query = ("SELECT code, name, subgroup, description FROM courses "
                         "WHERE name = %s AND (subgroup IS NULL OR subgroup = '') ORDER BY code ASC")
                params = (group_name,)
            cursor.execute(query, params)
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"DB Error fetching courses for group {group_name}/{subgroup}: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if db: db.close()

    def get_enrolled_courses(self, email):
        db = None
        cursor = None
        try:
            db = self.connection()
            cursor = db.cursor(dictionary=True)
            query = """
                SELECT
                    e.code, e.unique_code,
                    COALESCE(ep.payment_status, 'FREE') AS payment_status,
                    ep.amount_paid
                FROM enrollment e
                LEFT JOIN enrollment_payment ep ON e.payment_id = ep.payment_id
                WHERE e.email = %s
                AND (ep.payment_status IN ('Paid', 'FREE') OR ep.payment_status IS NULL)
            """
            cursor.execute(query, (email,))
            result = cursor.fetchall()
            logger.info(f"DB: Fetched {len(result)} enrolled courses for {email}")
            return result
        except Exception as e:
            logger.error(f"DB Error in get_enrolled_courses for {email}: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if db: db.close()