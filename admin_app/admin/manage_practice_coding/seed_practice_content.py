import logging

logger = logging.getLogger(__name__)

SEED_MARKER = "__seeded__"

COMPANIES = ["Google", "Amazon", "Microsoft", "Meta", "TCS", "Infosys"]

CODING = [
    ("Two Sum", "Easy", "Array", 0,
     "Given n integers and a target, print the 0-based indices of the two "
     "numbers that add up to the target. Exactly one solution exists.",
     "Line 1: n and target.\nLine 2: n space-separated integers.",
     "Input:\n4 9\n2 7 11 15\n\nOutput:\n0 1",
     "Two space-separated indices, smaller first.",
     ["Google", "Amazon"],
     [("4 9\n2 7 11 15", "0 1", 0), ("3 6\n3 2 4", "1 2", 1), ("2 6\n3 3", "0 1", 1)],
     {"python": "n, target = map(int, input().split())\nnums = list(map(int, input().split()))\n# your code here\n"}),

    ("Reverse a String", "Easy", "String", 0,
     "Read a line and print it reversed.",
     "One line of text.", "Input:\nhello\n\nOutput:\nolleh",
     "The reversed line.",
     ["TCS", "Infosys"],
     [("hello", "olleh", 0), ("abcd", "dcba", 1), ("a", "a", 1)],
     {"python": "s = input()\nprint(s[::-1])\n"}),

    ("Count Vowels", "Easy", "String", 0,
     "Count how many vowels (a, e, i, o, u, case-insensitive) are in the line.",
     "One line of text.", "Input:\nEducation\n\nOutput:\n5",
     "A single integer.",
     ["Infosys"],
     [("Education", "5", 0), ("xyz", "0", 1), ("AEIOU", "5", 1)],
     {"python": "s = input().lower()\nprint(sum(c in 'aeiou' for c in s))\n"}),

    ("FizzBuzz", "Easy", "Math", 0,
     "Print numbers 1..n, but 'Fizz' for multiples of 3, 'Buzz' for multiples "
     "of 5, and 'FizzBuzz' for multiples of both, one per line.",
     "A single integer n.", "Input:\n5\n\nOutput:\n1\n2\nFizz\n4\nBuzz",
     "n lines.",
     ["Amazon"],
     [("5", "1\n2\nFizz\n4\nBuzz", 0), ("3", "1\n2\nFizz", 1)],
     {"python": "n = int(input())\nfor i in range(1, n+1):\n    pass\n"}),

    ("Second Largest Element", "Moderate", "Array", 1,
     "Given n integers, print the second largest DISTINCT value, or -1 if it "
     "does not exist.",
     "Line 1: n.\nLine 2: n space-separated integers.",
     "Input:\n5\n1 2 3 4 5\n\nOutput:\n4",
     "A single integer.",
     ["Google", "Microsoft"],
     [("5\n1 2 3 4 5", "4", 0), ("3\n7 7 7", "-1", 1), ("2\n9 1", "1", 1)],
     {"python": "n = int(input())\nnums = list(map(int, input().split()))\n# your code here\n"}),

    ("Valid Parentheses", "Moderate", "Stack", 1,
     "Given a string of brackets ()[]{}, print YES if every bracket is "
     "correctly matched and nested, else NO.",
     "One line containing only bracket characters.",
     "Input:\n([{}])\n\nOutput:\nYES",
     "YES or NO.",
     ["Meta", "Amazon"],
     [("([{}])", "YES", 0), ("([)]", "NO", 1), ("(((", "NO", 1)],
     {"python": "s = input()\n# your code here\n"}),
]

QUIZ = [
    ("Java", "Which keyword makes a variable's value unchangeable in Java?",
     "static", "final", "const", "immutable", "B",
     "'final' prevents reassignment after the first value is set.", 0),
    ("Java", "What is the default value of an int instance field in Java?",
     "0", "null", "undefined", "1", "A",
     "Numeric fields default to 0; only object references default to null.", 0),
    ("Python", "What does len('') return in Python?",
     "0", "None", "1", "Error", "A",
     "An empty string has length 0.", 0),
    ("Python", "Which structure does NOT allow duplicate elements?",
     "list", "tuple", "set", "dict keys can duplicate", "C",
     "A set stores only unique elements.", 0),
    ("SQL", "Which SQL clause filters rows BEFORE grouping?",
     "HAVING", "WHERE", "ORDER BY", "GROUP BY", "B",
     "WHERE filters rows first; HAVING filters after GROUP BY.", 0),
    ("SQL", "Which statement removes ALL rows but keeps the table structure fastest?",
     "DELETE", "DROP", "TRUNCATE", "REMOVE", "C",
     "TRUNCATE empties a table quickly without logging each row.", 0),
    ("Algorithms", "What is the average time complexity of binary search?",
     "O(n)", "O(log n)", "O(n log n)", "O(1)", "B",
     "Binary search halves the search space each step.", 0),
    ("Algorithms", "Which sort is stable and runs in O(n log n) worst case?",
     "Quick sort", "Merge sort", "Selection sort", "Bubble sort", "B",
     "Merge sort is stable and O(n log n) in the worst case.", 1),
    ("Data Structures", "Which structure gives O(1) average lookup by key?",
     "Array", "Linked list", "Hash table", "Binary tree", "C",
     "A hash table maps keys to buckets for average O(1) access.", 1),
    ("Operating Systems", "What is a deadlock?",
     "A crashed process", "Two processes each waiting on the other's resource",
     "A full disk", "A memory leak", "B",
     "Deadlock is a circular wait where neither side can proceed.", 1),
]


def _scalar(cur, sql, params=None):
    cur.execute(sql, params or ())
    row = cur.fetchone()
    return row[0] if row else None


def seed():
    from admin.db_pool import get_connection

    conn = get_connection()
    cur = conn.cursor()
    try:
        already = _scalar(cur, "SELECT COUNT(*) FROM pcp_companies WHERE slug = %s",
                          (SEED_MARKER,))
        if already:
            return False

        company_ids = {}
        for i, name in enumerate(COMPANIES):
            slug = name.lower().replace(" ", "-")
            cur.execute("INSERT INTO pcp_companies (name, slug, position) VALUES (%s,%s,%s)",
                        (name, slug, i))
            company_ids[name] = cur.lastrowid

        for pos, q in enumerate(CODING):
            (title, diff, subject, paid, statement, inspec, example,
             outspec, companies, cases, templates) = q
            cur.execute("""
                INSERT INTO pcp_questions
                  (title, difficulty, subject, statement_html, input_spec, example_html,
                   output_spec, allowed_languages, is_paid, position)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (title, diff, subject, statement, inspec, example, outspec,
                  "python,java,c,cpp,csharp,javascript", paid, pos))
            qid = cur.lastrowid
            cur.executemany("""
                INSERT INTO pcp_testcases (question_id, input_text, expected_output, is_hidden, position)
                VALUES (%s,%s,%s,%s,%s)
            """, [(qid, c[0], c[1], c[2], i) for i, c in enumerate(cases)])
            for lang, code in templates.items():
                cur.execute("INSERT INTO pcp_templates (question_id, language, template_code) "
                            "VALUES (%s,%s,%s)", (qid, lang, code))
            for name in companies:
                if name in company_ids:
                    cur.execute("INSERT IGNORE INTO pcp_question_companies (question_id, company_id) "
                                "VALUES (%s,%s)", (qid, company_ids[name]))

        cur.executemany("""
            INSERT INTO pcq_questions
              (subject, question_text, option_a, option_b, option_c, option_d,
               correct_option, explanation, is_paid, position)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, [(q[0], q[1], q[2], q[3], q[4], q[5], q[6], q[7], q[8], i)
              for i, q in enumerate(QUIZ)])

        cur.execute("INSERT INTO pcp_companies (name, slug, position) VALUES (%s,%s,%s)",
                    ("(seed marker)", SEED_MARKER, 999))
        conn.commit()
        logger.info("PRACTICE SEED: loaded %d coding, %d quiz question(s), %d companies",
                    len(CODING), len(QUIZ), len(COMPANIES))
        return True
    except Exception:
        conn.rollback()
        logger.exception("PRACTICE SEED: failed; nothing was written")
        return False
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    if seed():
        print(f"Seeded {len(CODING)} coding and {len(QUIZ)} quiz question(s).")
    else:
        print("Nothing to do - the starter content is already loaded.")
