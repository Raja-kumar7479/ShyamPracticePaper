import sys
from pathlib import Path
import mysql.connector
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
v = dotenv_values(ROOT / 'user_app' / '.env')

COURSE = 'PLA'
SECTION_ID = 'TCS_NQT_2026_SET1'
APT_KEY = 'tcs_nqt_2026_set1_apt'
CODE_KEY = 'tcs_nqt_2026_set1_code'
CODE_SLUG = 'tcs-nqt-2026-set1-coding'
TITLE = 'TCS NQT 2026 - Set 1'

NUMERICAL = [
    ('A train 180 m long passes a pole in 9 seconds. What is its speed in km/h?', '60', '72', '80', '90', 'B',
     '180 m in 9 s = 20 m/s. 20 x 18/5 = 72 km/h.'),
    ('The average of 5 numbers is 27. When one number is removed, the average of the remaining 4 becomes 25. Which number was removed?',
     '30', '32', '35', '37', 'C', 'Total = 5 x 27 = 135. Remaining total = 4 x 25 = 100. Removed = 135 - 100 = 35.'),
    ('What is the simple interest on Rs. 8,000 at 5% per annum for 3 years?', 'Rs. 1,000', 'Rs. 1,200', 'Rs. 1,500', 'Rs. 1,600', 'B',
     'SI = 8000 x 5 x 3 / 100 = 1,200.'),
    ('If 3x + 7 = 25, what is the value of x?', '5', '6', '7', '8', 'B', '3x = 18, so x = 6.'),
    ('Two numbers are in the ratio 3 : 5 and their sum is 96. What is the larger number?', '48', '56', '60', '64', 'C',
     'One part = 96 / 8 = 12. Larger = 5 x 12 = 60.'),
    ('What is the LCM of 12, 18 and 24?', '48', '72', '96', '144', 'B', '12 = 2^2 x 3, 18 = 2 x 3^2, 24 = 2^3 x 3. LCM = 2^3 x 3^2 = 72.'),
    ('An article bought for Rs. 250 is sold for Rs. 300. What is the profit percentage?', '15%', '20%', '25%', '30%', 'B',
     'Profit = 50. 50 / 250 x 100 = 20%.'),
    ('40% of a number is 120. What is the number?', '240', '280', '300', '320', 'C', 'Number = 120 x 100 / 40 = 300.'),
    ('Pipe A fills a tank in 12 hours and pipe B in 24 hours. Working together, how long do they take to fill the tank?',
     '6 hours', '8 hours', '9 hours', '10 hours', 'B', 'Per hour: 1/12 + 1/24 = 3/24 = 1/8. So 8 hours.'),
    ('What is the compound interest on Rs. 10,000 at 10% per annum for 2 years, compounded annually?',
     'Rs. 2,000', 'Rs. 2,100', 'Rs. 2,200', 'Rs. 2,400', 'B', 'Amount = 10000 x 1.1 x 1.1 = 12,100. CI = 2,100.'),
]

VERBAL = [
    ('Choose the word closest in meaning to ABUNDANT.', 'Scarce', 'Plentiful', 'Rare', 'Meagre', 'B', 'Abundant means existing in large quantities - plentiful.'),
    ('Choose the word opposite in meaning to TRANSPARENT.', 'Clear', 'Obvious', 'Opaque', 'Lucid', 'C', 'Transparent lets light through; opaque does not.'),
    ('Choose the correctly spelt word.', 'Acommodate', 'Accomodate', 'Accommodate', 'Acomodate', 'C', 'Accommodate has double c and double m.'),
    ('Fill in the blank: She has been working here ____ 2019.', 'for', 'since', 'from', 'by', 'B',
     '"Since" is used with a point in time; "for" is used with a duration.'),
    ('Fill in the blank: Neither of the boys ____ present at the meeting.', 'were', 'was', 'are', 'have been', 'B',
     '"Neither of" takes a singular verb: was.'),
    ('One word for "a person who knows and speaks many languages".', 'Linguist', 'Polyglot', 'Orator', 'Bilingual', 'B',
     'A polyglot speaks several languages; a linguist studies language.'),
    ('What does the idiom "to hit the nail on the head" mean?', 'To hurt someone badly', 'To say exactly the right thing',
     'To finish a task quickly', 'To make a serious mistake', 'B', 'The idiom means to describe a situation or point exactly.'),
    ('Change to passive voice: "The manager approved the plan."', 'The plan is approved by the manager.', 'The plan has approved by the manager.',
     'The plan was approved by the manager.', 'The plan approved by the manager.', 'C', 'Past simple active becomes was/were + past participle.'),
    ('Find the part of the sentence that has an error: "Each of the students (A) / have submitted (B) / the assignment on time. (C) / No error (D)"',
     'Each of the students', 'have submitted', 'the assignment on time', 'No error', 'B', '"Each of" takes a singular verb: has submitted.'),
    ('"The report was concise." Here "concise" means:', 'Long and detailed', 'Brief and clear', 'Confusing', 'Incomplete', 'B',
     'Concise means giving a lot of information clearly in few words.'),
]

REASONING = [
    ('Find the next number in the series: 2, 6, 12, 20, 30, ?', '40', '42', '44', '48', 'B',
     'Differences are 4, 6, 8, 10, so the next difference is 12: 30 + 12 = 42.'),
    ('In a certain code, CAT is written as DBU. How is DOG written in that code?', 'EPH', 'EPG', 'DPH', 'FQI', 'A',
     'Each letter moves one step forward: D->E, O->P, G->H.'),
    ('Find the odd one out.', 'Apple', 'Mango', 'Carrot', 'Banana', 'C', 'Carrot is a vegetable; the others are fruits.'),
    ('Pointing to a photograph, Raj says, "She is the daughter of my father\'s only son." Raj has no brother. How is the girl related to Raj?',
     'Sister', 'Daughter', 'Niece', 'Cousin', 'B', 'Raj is his father\'s only son, so the girl is Raj\'s daughter.'),
    ('A person walks 5 km north, turns right and walks 3 km, then turns right again and walks 5 km. How far is he from the starting point?',
     '3 km', '5 km', '8 km', '13 km', 'A', 'The two 5 km legs cancel out; he is 3 km east of the start.'),
    ('What is the angle between the hour hand and the minute hand of a clock at 3:00?', '60 degrees', '90 degrees', '120 degrees', '180 degrees', 'B',
     'At 3:00 the hands are a quarter turn apart: 90 degrees.'),
    ('Which letter is 5th to the right of the 8th letter from the left in the English alphabet?', 'L', 'M', 'N', 'K', 'B',
     'The 8th letter is H. Five letters to the right: I, J, K, L, M.'),
    ('Statements: All pens are tools. All tools are objects. Conclusions: I. All pens are objects. II. Some objects are tools.',
     'Only I follows', 'Only II follows', 'Neither follows', 'Both I and II follow', 'D',
     'Pens are inside tools, which are inside objects, so I follows; some objects are tools, so II follows.'),
    ('If + means x, x means -, - means / and / means +, then the value of 8 + 4 - 2 x 3 / 6 is:', '17', '19', '21', '23', 'B',
     'Rewrite: 8 x 4 / 2 - 3 + 6 = 16 - 3 + 6 = 19.'),
    ('Five friends A, B, C, D and E sit in a row. E is at the left end and C is at the right end. D sits between A and B, and A sits to the left of B. Who sits in the middle?',
     'A', 'B', 'D', 'E', 'C', 'The order is E, A, D, B, C, so D is in the middle.'),
]

SECTIONS = [('1', 'Numerical Ability', NUMERICAL), ('2', 'Verbal Ability', VERBAL), ('3', 'Reasoning Ability', REASONING)]


def reverse_words(line):
    return ' '.join(w[::-1] for w in line.split(' '))


def primes_in_range(line):
    lo, hi = map(int, line.split())
    found = [n for n in range(max(lo, 2), hi + 1) if all(n % d for d in range(2, int(n ** 0.5) + 1))]
    return ' '.join(map(str, found)) if found else 'NONE'


CODING = [
    {
        'title': 'Reverse Each Word',
        'statement': '<p>You are given one line of text made of words separated by single spaces. Reverse the letters of every word while keeping the words in their original order.</p>',
        'input_spec': 'A single line containing between 1 and 1000 characters: lowercase or uppercase letters, digits and single spaces.',
        'output_spec': 'One line: the same words, each reversed, separated by single spaces.',
        'example': 'Input:\nhello world\n\nOutput:\nolleh dlrow',
        'solve': reverse_words,
        'cases': [('hello world', False), ('TCS NQT 2026', False), ('a', True), ('coding is fun', True), ('Madam In Eden Im Adam', True)],
    },
    {
        'title': 'Primes In Range',
        'statement': '<p>You are given two integers L and R. Print every prime number between L and R (both inclusive) in increasing order, separated by single spaces. If there is no prime in the range, print <code>NONE</code>.</p>',
        'input_spec': 'A single line with two integers L and R (1 <= L <= R <= 100000), separated by a space.',
        'output_spec': 'One line with the primes separated by spaces, or NONE.',
        'example': 'Input:\n10 20\n\nOutput:\n11 13 17 19',
        'solve': primes_in_range,
        'cases': [('10 20', False), ('1 10', False), ('14 16', True), ('2 2', True), ('90 100', True)],
    },
]

TEMPLATES = {
    'python': 'line = input().strip()\n\nprint(line)\n',
    'java': 'import java.util.*;\n\npublic class Main {\n    public static void main(String[] args) {\n        Scanner sc = new Scanner(System.in);\n        String line = sc.nextLine();\n        System.out.println(line);\n    }\n}\n',
    'cpp': '#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    string line;\n    getline(cin, line);\n    cout << line << endl;\n    return 0;\n}\n',
}


def connect():
    return mysql.connector.connect(host=v['DATABASE_HOST'], user=v['DATABASE_USER'], password=v['DATABASE_PASSWORD'],
                                   database=v['DATABASE_NAME'])


def present(cur):
    cur.execute("SELECT 1 FROM course_content WHERE section_id = %s", (SECTION_ID,))
    return cur.fetchone() is not None


def remove(cur):
    cur.execute("SELECT id FROM cp_tests WHERE slug = %s", (CODE_SLUG,))
    for (tid,) in cur.fetchall():
        cur.execute("SELECT id FROM cp_questions WHERE section_id IN (SELECT id FROM cp_sections WHERE test_id = %s)", (tid,))
        qids = [r[0] for r in cur.fetchall()]
        if qids:
            marks = ','.join(['%s'] * len(qids))
            cur.execute(f"DELETE FROM cp_testcases WHERE question_id IN ({marks})", qids)
            cur.execute(f"DELETE FROM cp_question_templates WHERE question_id IN ({marks})", qids)
            cur.execute(f"DELETE FROM cp_questions WHERE id IN ({marks})", qids)
        cur.execute("DELETE FROM cp_sections WHERE test_id = %s", (tid,))
        cur.execute("DELETE FROM tcs_exams WHERE coding_test_id = %s", (tid,))
        cur.execute("DELETE FROM cp_tests WHERE id = %s", (tid,))
    cur.execute("DELETE FROM tcs_exams WHERE aptitude_test_key = %s", (APT_KEY,))
    cur.execute("DELETE FROM test_questions WHERE test_key = %s", (APT_KEY,))
    cur.execute("DELETE FROM test_description WHERE test_key = %s", (APT_KEY,))
    cur.execute("DELETE FROM course_content WHERE section_id = %s", (SECTION_ID,))


def attempts(cur):
    cur.execute("SELECT COUNT(*) FROM user_test_log WHERE test_key = %s", (APT_KEY,))
    return cur.fetchone()[0]


def seed(cur):
    cur.execute("SELECT name FROM courses WHERE code = %s", (COURSE,))
    row = cur.fetchone()
    if not row:
        raise SystemExit(f"Course {COURSE} does not exist - create it in Courses & Groups first.")
    group = row[0]
    cur.execute("""
        INSERT INTO course_content (code, name, stream, section, section_id, title, subtitle, label, price, discount, details, status)
        VALUES (%s, %s, 'Placement', 'tcs_test', %s, %s,
                'Numerical, Verbal and Reasoning sections followed by two coding problems', 'Free', 0, 0,
                '<p>TCS NQT style exam: 30 aptitude questions in 45 minutes, then 2 coding problems in 30 minutes. One window, one clock.</p>',
                'active')
    """, (COURSE, group, SECTION_ID, TITLE))
    cur.execute("""
        INSERT INTO test_description (test_id, code, test_key, subject_title, subject_subtitle, total_questions, total_marks,
                                      total_duration_minutes, show_calculator, access_label)
        VALUES (%s, %s, %s, 'TCS NQT Aptitude - Set 1', 'Numerical Ability, Verbal Ability, Reasoning Ability', 30, 30, 45, 0, 'inherit')
    """, (SECTION_ID, COURSE, APT_KEY))
    desc_id = cur.lastrowid
    rows = []
    for sid, sname, items in SECTIONS:
        for n, (text, a, b, c, d, ans, why) in enumerate(items, 1):
            rows.append((SECTION_ID, APT_KEY, desc_id, sid, sname, n, 'MCQ', f'<p>{text}</p>',
                         f'<p>{a}</p>', f'<p>{b}</p>', f'<p>{c}</p>', f'<p>{d}</p>', ans, 1, 0, 'Medium', f'<p>{why}</p>'))
    cur.executemany("""
        INSERT INTO test_questions (test_id, test_key, test_description_id, section_id, section_name, question_number,
                                    question_type, question_text, option_a, option_b, option_c, option_d,
                                    correct_option, correct_marks, negative_marks, question_level, answer_text)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, rows)

    cur.execute("""
        INSERT INTO cp_tests (slug, test_id, code, test_key, title, description, total_duration_min, allowed_languages, is_published, access_label)
        VALUES (%s, %s, %s, %s, 'TCS NQT Coding - Set 1', 'Two coding problems, 30 minutes', 30, 'python,java,cpp', 1, 'inherit')
    """, (CODE_SLUG, SECTION_ID, COURSE, CODE_KEY))
    cp_test = cur.lastrowid
    cur.execute("INSERT INTO cp_sections (test_id, title, section_type, duration_min, position) VALUES (%s, 'Coding', 'coding', 30, 1)", (cp_test,))
    section = cur.lastrowid
    for pos, q in enumerate(CODING, 1):
        cur.execute("""
            INSERT INTO cp_questions (section_id, position, title, statement_html, input_spec, example_html, output_spec,
                                      marks, difficulty, time_limit_sec, memory_limit, allowed_languages, compare_mode)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 10, 'Medium', 5, '256m', 'python,java,cpp', 'exact')
        """, (section, pos, q['title'], q['statement'], q['input_spec'], q['example'], q['output_spec']))
        qid = cur.lastrowid
        cur.executemany("INSERT INTO cp_testcases (question_id, input_text, expected_output, is_hidden, position) VALUES (%s,%s,%s,%s,%s)",
                        [(qid, inp, q['solve'](inp), int(hidden), i + 1) for i, (inp, hidden) in enumerate(q['cases'])])
        cur.executemany("INSERT INTO cp_question_templates (question_id, language, template_code) VALUES (%s,%s,%s)",
                        [(qid, lang, code) for lang, code in TEMPLATES.items()])
    cur.execute("""
        INSERT INTO tcs_exams (section_id, code, title, subtitle, aptitude_test_key, coding_test_id, coding_label, is_published)
        VALUES (%s, %s, %s, '45 min aptitude + 30 min coding', %s, %s, 'Coding', 1)
    """, (SECTION_ID, COURSE, TITLE, APT_KEY, cp_test))
    return desc_id, cp_test


def main():
    replace = '--replace' in sys.argv
    conn = connect()
    cur = conn.cursor()
    try:
        conn.start_transaction()
        if present(cur):
            if not replace:
                print(f"{TITLE} is already in the database - nothing changed. Run with --replace to rebuild it.")
                conn.rollback()
                return
            n = attempts(cur)
            if n:
                print(f"Refusing to replace: {n} student attempt(s) exist on this exam.")
                conn.rollback()
                return
            remove(cur)
        desc_id, cp_test = seed(cur)
        conn.commit()
        print(f"Stored {TITLE} under {COURSE}: description {desc_id} with 30 questions in 3 sections, coding test {cp_test} with 2 problems, exam published.")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()
