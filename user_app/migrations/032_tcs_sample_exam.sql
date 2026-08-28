INSERT INTO course_content (code, name, stream, section, title, subtitle, label, price, details, status, section_id)
SELECT 'PLA', 'Placement', 'Placement', 'tcs_test', 'TCS NQT Mock Exam 1',
       'Numerical, Verbal and Reasoning sections followed by a coding section',
       'Free', 0.00, 'Sample TCS NQT style exam: 45 minutes aptitude + 30 minutes coding.', 'active',
       'TCS_NQT_MOCK_1'
WHERE NOT EXISTS (SELECT 1 FROM course_content WHERE section_id = 'TCS_NQT_MOCK_1');

INSERT INTO test_description (test_id, code, test_key, subject_title, subject_subtitle,
                              total_questions, total_marks, total_duration_minutes, show_calculator, access_label)
SELECT 'TCS_NQT_MOCK_1', (SELECT code FROM enrollment WHERE code = 'PLA' LIMIT 1), 'TCS_NQT_MOCK_1_APT', 'TCS NQT Aptitude',
       'Numerical Ability, Verbal Ability, Reasoning Ability', 15, 15, 45, 0, 'inherit'
WHERE NOT EXISTS (SELECT 1 FROM test_description WHERE test_key = 'TCS_NQT_MOCK_1_APT');

SET @apt_id := (SELECT id FROM test_description WHERE test_key = 'TCS_NQT_MOCK_1_APT');

INSERT INTO test_questions (test_id, test_key, test_description_id, section_id, section_name, question_number,
                            question_type, question_text, option_a, option_b, option_c, option_d,
                            correct_option, correct_marks, negative_marks, question_level, answer_text)
SELECT * FROM (
  SELECT 'TCS_NQT_MOCK_1' AS test_id, 'TCS_NQT_MOCK_1_APT' AS test_key, @apt_id AS test_description_id,
         '1' AS section_id, 'Numerical Ability' AS section_name, 1 AS question_number, 'MCQ' AS question_type,
         'A shopkeeper marks an article 40% above cost and allows a 15% discount. What is the profit percent?' AS question_text,
         '19%' AS option_a, '21%' AS option_b, '25%' AS option_c, '15%' AS option_d,
         'A' AS correct_option, 1 AS correct_marks, 0 AS negative_marks, 'Medium' AS question_level,
         'Selling price = 140 x 0.85 = 119 on a cost of 100, so profit is 19%.' AS answer_text
  UNION ALL SELECT 'TCS_NQT_MOCK_1','TCS_NQT_MOCK_1_APT',@apt_id,'1','Numerical Ability',2,'MCQ',
         'The average of five consecutive odd numbers is 27. What is the largest of them?',
         '29','31','33','35','B',1,0,'Easy','The numbers are 23, 25, 27, 29, 31.'
  UNION ALL SELECT 'TCS_NQT_MOCK_1','TCS_NQT_MOCK_1_APT',@apt_id,'1','Numerical Ability',3,'MCQ',
         'A train 240 m long passes a pole in 12 seconds. Its speed in km/h is:',
         '60','72','80','90','B',1,0,'Easy','240/12 = 20 m/s = 72 km/h.'
  UNION ALL SELECT 'TCS_NQT_MOCK_1','TCS_NQT_MOCK_1_APT',@apt_id,'1','Numerical Ability',4,'MCQ',
         'If 12 workers finish a job in 18 days, how many days will 9 workers take?',
         '20','22','24','27','C',1,0,'Medium','Work is constant: 12 x 18 = 9 x d, so d = 24.'
  UNION ALL SELECT 'TCS_NQT_MOCK_1','TCS_NQT_MOCK_1_APT',@apt_id,'1','Numerical Ability',5,'MCQ',
         'Simple interest on Rs 8000 at 7.5% per annum for 2 years is:',
         'Rs 1000','Rs 1100','Rs 1200','Rs 1250','C',1,0,'Easy','8000 x 7.5 x 2 / 100 = 1200.'
  UNION ALL SELECT 'TCS_NQT_MOCK_1','TCS_NQT_MOCK_1_APT',@apt_id,'2','Verbal Ability',6,'MCQ',
         'Choose the word closest in meaning to CANDID.',
         'Secretive','Frank','Polite','Cautious','B',1,0,'Easy','Candid means frank or outspoken.'
  UNION ALL SELECT 'TCS_NQT_MOCK_1','TCS_NQT_MOCK_1_APT',@apt_id,'2','Verbal Ability',7,'MCQ',
         'Pick the grammatically correct sentence.',
         'Neither of the answers are correct.','Neither of the answers is correct.',
         'Neither of the answer is correct.','Neither answers is correct.','B',1,0,'Medium',
         'Neither takes a singular verb.'
  UNION ALL SELECT 'TCS_NQT_MOCK_1','TCS_NQT_MOCK_1_APT',@apt_id,'2','Verbal Ability',8,'MCQ',
         'Choose the antonym of SCARCE.',
         'Rare','Abundant','Limited','Meagre','B',1,0,'Easy','Scarce means in short supply; abundant is the opposite.'
  UNION ALL SELECT 'TCS_NQT_MOCK_1','TCS_NQT_MOCK_1_APT',@apt_id,'2','Verbal Ability',9,'MCQ',
         'Fill in the blank: The committee ____ its report by Friday.',
         'will submitting','submits','will have submitted','submitting','C',1,0,'Medium',
         'A deadline in the future takes the future perfect tense.'
  UNION ALL SELECT 'TCS_NQT_MOCK_1','TCS_NQT_MOCK_1_APT',@apt_id,'2','Verbal Ability',10,'MCQ',
         'Identify the correctly spelt word.',
         'Occurence','Occurrence','Ocurrence','Occurrance','B',1,0,'Easy','Occurrence has double c and double r.'
  UNION ALL SELECT 'TCS_NQT_MOCK_1','TCS_NQT_MOCK_1_APT',@apt_id,'3','Reasoning Ability',11,'MCQ',
         'Find the next number in the series: 2, 6, 12, 20, 30, ?',
         '40','42','44','48','B',1,0,'Easy','Differences grow by 2: 4, 6, 8, 10, 12.'
  UNION ALL SELECT 'TCS_NQT_MOCK_1','TCS_NQT_MOCK_1_APT',@apt_id,'3','Reasoning Ability',12,'MCQ',
         'If CAT is coded as DBU, how is DOG coded?',
         'EPH','EQH','FPH','EPI','A',1,0,'Easy','Each letter shifts forward by one.'
  UNION ALL SELECT 'TCS_NQT_MOCK_1','TCS_NQT_MOCK_1_APT',@apt_id,'3','Reasoning Ability',13,'MCQ',
         'Pointing to a photograph, Ravi says, "She is the daughter of my grandfather''s only son." How is she related to Ravi?',
         'Mother','Sister','Aunt','Cousin','B',1,0,'Medium','The grandfather''s only son is Ravi''s father; his daughter is Ravi''s sister.'
  UNION ALL SELECT 'TCS_NQT_MOCK_1','TCS_NQT_MOCK_1_APT',@apt_id,'3','Reasoning Ability',14,'MCQ',
         'A is to the north of B, C is to the east of B. In which direction is A from C?',
         'North-east','North-west','South-west','South-east','B',1,0,'Medium','A is north and west of C.'
  UNION ALL SELECT 'TCS_NQT_MOCK_1','TCS_NQT_MOCK_1_APT',@apt_id,'3','Reasoning Ability',15,'MCQ',
         'Which word does not belong with the others?',
         'Copper','Iron','Brass','Zinc','C',1,0,'Medium','Brass is an alloy; the rest are elements.'
) AS seed
WHERE @apt_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM test_questions WHERE test_key = 'TCS_NQT_MOCK_1_APT');

INSERT INTO cp_tests (slug, test_id, code, test_key, title, description, total_duration_min, allowed_languages, is_published)
SELECT 'tcs-nqt-mock-1-coding', 'TCS_NQT_MOCK_1', 'PLA', 'TCS_NQT_MOCK_1_CODE', 'TCS NQT Coding',
       'Two programming problems. Java, Python and C++ only.', 30, 'java,python,cpp', 1
WHERE NOT EXISTS (SELECT 1 FROM cp_tests WHERE slug = 'tcs-nqt-mock-1-coding');

SET @cp_test := (SELECT id FROM cp_tests WHERE slug = 'tcs-nqt-mock-1-coding');

INSERT INTO cp_sections (test_id, title, section_type, duration_min, position)
SELECT @cp_test, 'Coding', 'coding', 30, 1
WHERE @cp_test IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM cp_sections WHERE test_id = @cp_test);

SET @cp_sec := (SELECT id FROM cp_sections WHERE test_id = @cp_test ORDER BY id LIMIT 1);

INSERT INTO cp_questions (section_id, position, title, statement_html, marks, time_limit_sec, memory_limit,
                          allowed_languages, output_spec, input_spec, example_html, difficulty)
SELECT @cp_sec, 1, 'Second Largest Element',
       '<p>Given N integers, print the second largest distinct value. If no such value exists, print -1.</p>',
       10, 5, '256m', 'java,python,cpp',
       'A single integer: the second largest distinct value, or -1.',
       'First line: N (2 &lt;= N &lt;= 100000). Second line: N space-separated integers.',
       '<pre>Input\n5\n4 9 2 9 7\nOutput\n7</pre>', 'Easy'
WHERE @cp_sec IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM cp_questions WHERE section_id = @cp_sec AND title = 'Second Largest Element');

INSERT INTO cp_questions (section_id, position, title, statement_html, marks, time_limit_sec, memory_limit,
                          allowed_languages, output_spec, input_spec, example_html, difficulty)
SELECT @cp_sec, 2, 'Balanced Brackets',
       '<p>Given a string of brackets ( ) [ ] { }, print YES if every bracket is closed in the correct order, otherwise NO.</p>',
       10, 5, '256m', 'java,python,cpp',
       'YES or NO.',
       'A single line containing the string (1 &lt;= length &lt;= 100000).',
       '<pre>Input\n{[()]}\nOutput\nYES</pre>', 'Medium'
WHERE @cp_sec IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM cp_questions WHERE section_id = @cp_sec AND title = 'Balanced Brackets');

SET @q1 := (SELECT id FROM cp_questions WHERE section_id = @cp_sec AND title = 'Second Largest Element');
SET @q2 := (SELECT id FROM cp_questions WHERE section_id = @cp_sec AND title = 'Balanced Brackets');

INSERT INTO cp_question_templates (question_id, language, template_code)
SELECT * FROM (
  SELECT @q1 AS question_id, 'java' AS language,
         'import java.util.*;\n\npublic class Main {\n    public static void main(String[] args) {\n        Scanner sc = new Scanner(System.in);\n        int n = sc.nextInt();\n        long[] a = new long[n];\n        for (int i = 0; i < n; i++) a[i] = sc.nextLong();\n        // write your code here\n    }\n}\n' AS template_code
  UNION ALL SELECT @q1, 'python',
         'import sys\n\ndef main():\n    data = sys.stdin.read().split()\n    n = int(data[0])\n    a = list(map(int, data[1:1 + n]))\n    # write your code here\n\nmain()\n'
  UNION ALL SELECT @q1, 'cpp',
         '#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    int n;\n    cin >> n;\n    vector<long long> a(n);\n    for (auto &x : a) cin >> x;\n    // write your code here\n    return 0;\n}\n'
  UNION ALL SELECT @q2, 'java',
         'import java.util.*;\n\npublic class Main {\n    public static void main(String[] args) {\n        Scanner sc = new Scanner(System.in);\n        String s = sc.next();\n        // write your code here\n    }\n}\n'
  UNION ALL SELECT @q2, 'python',
         'import sys\n\ndef main():\n    s = sys.stdin.readline().strip()\n    # write your code here\n\nmain()\n'
  UNION ALL SELECT @q2, 'cpp',
         '#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    string s;\n    cin >> s;\n    // write your code here\n    return 0;\n}\n'
) AS seed
WHERE @q1 IS NOT NULL AND @q2 IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM cp_question_templates WHERE question_id = @q1);

INSERT INTO cp_testcases (question_id, input_text, expected_output, is_hidden, position)
SELECT * FROM (
  SELECT @q1 AS question_id, '5\n4 9 2 9 7' AS input_text, '7' AS expected_output, 0 AS is_hidden, 1 AS position
  UNION ALL SELECT @q1, '3\n5 5 5', '-1', 0, 2
  UNION ALL SELECT @q1, '6\n-1 -5 -3 -1 -2 -5', '-2', 1, 3
  UNION ALL SELECT @q1, '4\n1000000000 999999999 1000000000 1', '999999999', 1, 4
  UNION ALL SELECT @q2, '{[()]}', 'YES', 0, 1
  UNION ALL SELECT @q2, '([)]', 'NO', 0, 2
  UNION ALL SELECT @q2, '((((', 'NO', 1, 3
  UNION ALL SELECT @q2, '{}[]()', 'YES', 1, 4
) AS seed
WHERE @q1 IS NOT NULL AND @q2 IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM cp_testcases WHERE question_id = @q1);

INSERT INTO tcs_exams (section_id, code, title, subtitle, aptitude_test_key, coding_test_id, is_published)
SELECT 'TCS_NQT_MOCK_1', 'PLA', 'TCS NQT Mock Exam 1',
       '15 aptitude questions in 45 min, then 2 coding problems in 30 min',
       'TCS_NQT_MOCK_1_APT', @cp_test, 1
WHERE @cp_test IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM tcs_exams WHERE aptitude_test_key = 'TCS_NQT_MOCK_1_APT');
