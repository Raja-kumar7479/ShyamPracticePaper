import selftest_student

MOCK_SID = 'SELFTESTMOCK'
COMM_SID = 'SELFTESTCOMM'
CODE_SID = 'SELFTESTCODE'
TCS_SID = 'SELFTESTTCS'
MOCK_KEY = 'free_selftest0000000001'
COMM_KEY = 'free_selftest0000000002'
CODING_KEY = 'free_selftest0000000003'
TCS_KEY = 'free_5e1f7e57000000000004'


def remove(db):
    db("DELETE FROM tcs_attempts WHERE tcs_exam_id IN (SELECT id FROM tcs_exams WHERE aptitude_test_key=%s)", (TCS_KEY,))
    db("DELETE FROM tcs_exams WHERE aptitude_test_key=%s OR section_id=%s", (TCS_KEY, TCS_SID))
    tests = [r['id'] for r in db("SELECT id FROM cp_tests WHERE test_key IN (%s, %s)", (CODING_KEY, TCS_KEY + '_code'))]
    for tid in tests:
        db("DELETE FROM cp_questions WHERE section_id IN (SELECT id FROM cp_sections WHERE test_id=%s)", (tid,))
        db("DELETE FROM cp_sections WHERE test_id=%s", (tid,))
        db("DELETE FROM cp_tests WHERE id=%s", (tid,))
    for key in (MOCK_KEY, COMM_KEY, CODING_KEY, TCS_KEY):
        for t in ('test_attempt_details', 'test_result', 'user_test_log', 'test_feedback'):
            db(f"DELETE FROM {t} WHERE test_key=%s", (key,))
        db("DELETE FROM test_questions WHERE test_key=%s", (key,))
        db("DELETE FROM test_description WHERE test_key=%s", (key,))
        db("DELETE FROM comm_questions WHERE test_key=%s", (key,))
        db("DELETE FROM comm_sections WHERE test_key=%s", (key,))
        db("DELETE FROM comm_description WHERE test_key=%s", (key,))
    db("DELETE FROM test_description WHERE subject_title LIKE 'SELFTEST%%' AND test_id=%s", (MOCK_SID,))
    db("DELETE FROM course_content WHERE section_id IN (%s, %s, %s, %s)", (MOCK_SID, COMM_SID, CODE_SID, TCS_SID))
    selftest_student.remove(db)


def setup(db, total=40):
    remove(db)
    student = selftest_student.setup(db)
    code, name = student['code'], student['name']
    db("INSERT INTO course_content (code,name,stream,section,section_id,title,subtitle,label,price,discount,details,status)"
       " VALUES (%s,%s,'Self test','mock_test',%s,'SELFTEST mock block','s','Free',0,0,'<p>x</p>','active')", (code, name, MOCK_SID))
    db("INSERT INTO course_content (code,name,stream,section,section_id,title,subtitle,label,price,discount,details,status)"
       " VALUES (%s,%s,'Self test','communication_test',%s,'SELFTEST comm block','s','Free',0,0,'<p>x</p>','active')", (code, name, COMM_SID))
    db("INSERT INTO test_description (test_id,test_key,subject_title,subject_subtitle,total_questions,total_marks,"
       "total_duration_minutes,show_calculator,access_label) VALUES (%s,%s,'SELFTEST mock paper','x',%s,%s,60,1,'free')",
       (MOCK_SID, MOCK_KEY, total, total * 2))
    db("INSERT INTO comm_description (test_id,test_key,subject_title,subject_subtitle,total_questions,total_marks,"
       "total_duration_minutes,show_calculator,access_label) VALUES (%s,%s,'SELFTEST comm paper','x',%s,%s,60,0,'free')",
       (COMM_SID, COMM_KEY, total, total * 5))
    db("INSERT INTO course_content (code,name,stream,section,section_id,title,subtitle,label,price,discount,details,status)"
       " VALUES (%s,%s,'Self test','coding_test',%s,'SELFTEST coding block','s','Free',0,0,'<p>x</p>','active')", (code, name, CODE_SID))
    db("INSERT INTO comm_description (test_id,test_key,subject_title,subject_subtitle,total_questions,total_marks,"
       "total_duration_minutes,show_calculator,access_label) VALUES (%s,%s,'SELFTEST coding paper','x',10,100,60,0,'free')",
       (CODE_SID, CODING_KEY))
    db("INSERT INTO course_content (code,name,stream,section,section_id,title,subtitle,label,price,discount,details,status)"
       " VALUES (%s,%s,'Self test','tcs_test',%s,'SELFTEST tcs block','s','Free',0,0,'<p>x</p>','active')", (code, name, TCS_SID))
    coding = db("SELECT id FROM comm_description WHERE test_key=%s", (CODING_KEY,))[0]['id']
    mock = db("SELECT id FROM test_description WHERE test_key=%s", (MOCK_KEY,))[0]['id']
    comm = db("SELECT id FROM comm_description WHERE test_key=%s", (COMM_KEY,))[0]['id']
    return {'code': code, 'mock_sid': MOCK_SID, 'comm_sid': COMM_SID, 'code_sid': CODE_SID, 'tcs_sid': TCS_SID, 'tcs_key': TCS_KEY, 'coding_id': coding,
            'coding_key': CODING_KEY, 'mock_id': mock, 'comm_id': comm,
            'mock_key': MOCK_KEY, 'comm_key': COMM_KEY, 'student': student}
