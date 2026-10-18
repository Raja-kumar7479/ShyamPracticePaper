import bcrypt

EMAIL = 'selftest.student@example.com'
PASSWORD = 'Selftest@1234'
NAME = 'SELFTEST GROUP'
CODE = 'SLFT'
UNIQUE = 'SELFTEST-UNIQUE-CODE-0000000000000000000'


def remove(db):
    db("DELETE FROM purchase WHERE email=%s", (EMAIL,))
    db("DELETE FROM content_orders WHERE email=%s", (EMAIL,))
    db("DELETE FROM pcp_subscriptions WHERE email=%s", (EMAIL,))
    db("DELETE FROM enrollment WHERE email=%s", (EMAIL,))
    db("DELETE FROM auth WHERE email=%s", (EMAIL,))
    db("DELETE FROM premium_plans WHERE code=%s", (CODE,))
    db("DELETE FROM premium_catalog WHERE code=%s", (CODE,))
    db("DELETE FROM notes_content WHERE code=%s", (CODE,))
    for t in ('test_attempt_details', 'test_result', 'user_test_log', 'test_feedback', 'test_questions'):
        db(f"DELETE FROM {t} WHERE test_key IN (SELECT test_key FROM test_description WHERE test_id IN "
           f"(SELECT section_id FROM course_content WHERE code=%s))", (CODE,))
    db("DELETE FROM test_description WHERE test_id IN (SELECT section_id FROM course_content WHERE code=%s)", (CODE,))
    db("DELETE FROM course_content WHERE code=%s", (CODE,))
    db("DELETE FROM courses WHERE code=%s", (CODE,))
    db("DELETE FROM course_group_codes WHERE code=%s", (CODE,))
    db("DELETE FROM course_groups WHERE group_name=%s", (NAME,))


def setup(db):
    remove(db)
    db("INSERT INTO course_groups (group_name, label, position, is_active, platform) VALUES (%s,%s,99,1,'placement')", (NAME, NAME))
    db("INSERT INTO course_group_codes (group_name, code, label, position) VALUES (%s,%s,'SELFTEST COURSE',99)", (NAME, CODE))
    db("INSERT INTO courses (code, name, subgroup, description, guest_access_code) VALUES (%s,%s,'SELFTEST','<p>SELFTEST</p>','selftest00000000')", (CODE, NAME))
    pw = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()
    db("INSERT INTO auth (username, email, password, auth_type, is_verified) VALUES ('SELFTEST Student', %s, %s, 'manual', 1)", (EMAIL, pw))
    db("INSERT INTO enrollment (email, name, code, unique_code, payment_id, enrollment_date) VALUES (%s,%s,%s,%s,'SELFTEST_ENROLL',NOW())", (EMAIL, NAME, CODE, UNIQUE))
    return {'email': EMAIL, 'password': PASSWORD, 'code': CODE, 'name': NAME, 'unique_code': UNIQUE}
