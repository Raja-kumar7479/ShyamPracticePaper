from .db import query_all, query_one, execute, get_cursor

LANGUAGES = ["python", "java", "c", "cpp", "csharp", "javascript"]
SECTION_TYPES = ["coding", "sql", "web"]


def list_published_tests(course_code=None, test_id=None):
    sql = ("SELECT id, slug, title, description, total_duration_min, access_label, code, test_id "
           "FROM cp_tests WHERE is_published = TRUE")
    params = []
    if test_id:
        sql += " AND test_id = %s"
        params.append(test_id)
    elif course_code:
        sql += " AND code = %s"
        params.append(course_code)
    sql += " ORDER BY created_at DESC"
    return query_all(sql, tuple(params))


def test_allowed_languages(test_id):
    row = query_one("SELECT allowed_languages FROM cp_tests WHERE id = %s", (test_id,))
    raw = (row or {}).get("allowed_languages") or ""
    langs = [l.strip() for l in raw.split(",") if l.strip() in LANGUAGES]
    return langs or None


def get_test_by_slug(slug):
    return query_one("SELECT * FROM cp_tests WHERE slug = %s", (slug,))


def get_test(test_id):
    return query_one("SELECT * FROM cp_tests WHERE id = %s", (test_id,))


def get_sections(test_id):
    return query_all(
        "SELECT s.id, s.title, s.section_type, s.duration_min, s.position, "
        "       (SELECT COUNT(*) FROM cp_questions q WHERE q.section_id = s.id) AS question_count "
        "FROM cp_sections s WHERE s.test_id = %s ORDER BY s.position, s.id",
        (test_id,),
    )


def get_section_totals(test_id):
    return query_all(
        "SELECT s.id, s.title, s.section_type, COUNT(q.id) AS question_count, "
        "       COALESCE(SUM(q.marks), 0) AS marks "
        "FROM cp_sections s LEFT JOIN cp_questions q ON q.section_id = s.id "
        "WHERE s.test_id = %s GROUP BY s.id, s.title, s.section_type, s.position "
        "ORDER BY s.position, s.id",
        (test_id,),
    )


def get_section(section_id):
    return query_one("SELECT * FROM cp_sections WHERE id = %s", (section_id,))


def get_questions(section_id):
    return query_all(
        "SELECT id, position, title, marks FROM cp_questions "
        "WHERE section_id = %s ORDER BY position, id",
        (section_id,),
    )


def get_question(question_id):
    return query_one("SELECT * FROM cp_questions WHERE id = %s", (question_id,))


def get_question_full(question_id):
    q = get_question(question_id)
    if not q:
        return None
    section = get_section(q["section_id"])
    q["section_type"] = section["section_type"] if section else None
    q["section_title"] = section["title"] if section else None

    if q["section_type"] == "coding":
        q["templates"] = {
            r["language"]: r["template_code"]
            for r in query_all(
                "SELECT language, template_code FROM cp_question_templates "
                "WHERE question_id = %s", (question_id,))
        }
        q["languages"] = [
            l.strip() for l in (q.get("allowed_languages") or "").split(",")
            if l.strip() in LANGUAGES
        ] or LANGUAGES
        test_langs = test_allowed_languages(section["test_id"]) if section else None
        if test_langs:
            narrowed = [l for l in q["languages"] if l in test_langs]
            q["languages"] = narrowed or test_langs
        from .starter_templates import with_defaults
        q["templates"] = with_defaults(q["templates"], q["languages"])
        q["sample_testcases"] = query_all(
            "SELECT id, input_text, expected_output FROM cp_testcases "
            "WHERE question_id = %s AND is_hidden = FALSE ORDER BY position, id",
            (question_id,),
        )
    elif q["section_type"] == "web":
        q["assertions"] = query_all(
            "SELECT id, kind, selector, property_name, expected_value, message, "
            "is_hidden FROM cp_web_assertions WHERE question_id = %s "
            "ORDER BY position, id", (question_id,),
        )
    return q


def get_testcases(question_id, include_hidden=True):
    sql = ("SELECT id, input_text, expected_output, is_hidden FROM cp_testcases "
           "WHERE question_id = %s")
    if not include_hidden:
        sql += " AND is_hidden = FALSE"
    sql += " ORDER BY position, id"
    return query_all(sql, (question_id,))


def get_web_assertions(question_id):
    return query_all(
        "SELECT id, kind, selector, property_name, expected_value, message, "
        "is_hidden FROM cp_web_assertions WHERE question_id = %s "
        "ORDER BY position, id", (question_id,),
    )


def get_or_create_attempt(test_id, user_id):
    row = query_one(
        "SELECT * FROM cp_attempts WHERE test_id = %s AND user_id = %s",
        (test_id, user_id),
    )
    if row:
        return row
    execute("INSERT INTO cp_attempts (test_id, user_id) VALUES (%s, %s)",
            (test_id, user_id))
    return query_one(
        "SELECT * FROM cp_attempts WHERE test_id = %s AND user_id = %s",
        (test_id, user_id),
    )


def get_attempt(attempt_id, user_id=None):
    if user_id is None:
        return query_one("SELECT * FROM cp_attempts WHERE id = %s", (attempt_id,))
    return query_one(
        "SELECT * FROM cp_attempts WHERE id = %s AND user_id = %s",
        (attempt_id, user_id),
    )


def submit_attempt(attempt_id):
    execute(
        "UPDATE cp_attempts SET "
        "  elapsed_seconds = elapsed_seconds + "
        "    IFNULL(TIMESTAMPDIFF(SECOND, resumed_at, NOW()), 0), "
        "  resumed_at = NULL, status = 'submitted', submitted_at = NOW() "
        "WHERE id = %s AND status = 'in_progress'", (attempt_id,),
    )


def mark_resumed(attempt_id):
    execute(
        "UPDATE cp_attempts SET resumed_at = IFNULL(resumed_at, NOW()), last_seen = NOW() "
        "WHERE id = %s AND status = 'in_progress'",
        (attempt_id,),
    )


def touch_attempt(attempt_id, user_id):
    execute(
        "UPDATE cp_attempts SET last_seen = NOW() "
        "WHERE id = %s AND user_id = %s AND status = 'in_progress'",
        (attempt_id, user_id),
    )


def pause_clock(attempt_id):
    execute(
        "UPDATE cp_attempts SET "
        "  elapsed_seconds = elapsed_seconds + "
        "    IFNULL(TIMESTAMPDIFF(SECOND, resumed_at, NOW()), 0), "
        "  resumed_at = NULL "
        "WHERE id = %s AND status = 'in_progress'", (attempt_id,),
    )


def active_seconds(attempt_id):
    row = query_one(
        "SELECT elapsed_seconds + "
        "       IFNULL(TIMESTAMPDIFF(SECOND, resumed_at, NOW()), 0) AS secs "
        "FROM cp_attempts WHERE id = %s", (attempt_id,),
    )
    return int(row["secs"] or 0) if row else 0


def save_answer(attempt_id, question_id, *, language=None, code=None,
                code_html=None, code_css=None, code_js=None, attempted=None):
    execute(
        """
        INSERT INTO cp_answers (attempt_id, question_id, language, code,
                             code_html, code_css, code_js, is_attempted)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            language     = COALESCE(VALUES(language), language),
            code         = COALESCE(VALUES(code), code),
            code_html    = COALESCE(VALUES(code_html), code_html),
            code_css     = COALESCE(VALUES(code_css), code_css),
            code_js      = COALESCE(VALUES(code_js), code_js),
            is_attempted = GREATEST(is_attempted, VALUES(is_attempted))
        """,
        (attempt_id, question_id, language, code, code_html, code_css,
         code_js, 1 if attempted else 0),
    )


def get_answer(attempt_id, question_id):
    return query_one(
        "SELECT * FROM cp_answers WHERE attempt_id = %s AND question_id = %s",
        (attempt_id, question_id),
    )


def set_review(attempt_id, question_id, review):
    execute(
        """
        INSERT INTO cp_answers (attempt_id, question_id, is_attempted, is_review)
        VALUES (%s, %s, 0, %s)
        ON DUPLICATE KEY UPDATE is_review = VALUES(is_review)
        """,
        (attempt_id, question_id, 1 if review else 0),
    )


def get_answer_flags(attempt_id, section_id):
    rows = query_all(
        "SELECT q.id AS question_id, "
        "       EXISTS(SELECT 1 FROM cp_submissions sub "
        "               WHERE sub.attempt_id = %s AND sub.question_id = q.id) AS submitted, "
        "       COALESCE((SELECT a.is_review FROM cp_answers a "
        "                  WHERE a.attempt_id = %s AND a.question_id = q.id), 0) AS is_review "
        "FROM cp_questions q WHERE q.section_id = %s",
        (attempt_id, attempt_id, section_id),
    )
    return {r["question_id"]: {"attempted": bool(r["submitted"]), "review": bool(r["is_review"])}
            for r in rows}


def get_attempted_map(attempt_id, section_id):
    return {qid: flags["attempted"] for qid, flags in get_answer_flags(attempt_id, section_id).items()}


def reset_attempt(attempt_id):
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT status FROM cp_attempts WHERE id = %s FOR UPDATE", (attempt_id,))
        row = cur.fetchone()
        if not row or row["status"] == "submitted":
            return None
        cur.execute("DELETE FROM cp_submissions WHERE attempt_id = %s", (attempt_id,))
        cleared = cur.rowcount
        cur.execute("DELETE FROM cp_answers WHERE attempt_id = %s", (attempt_id,))
        cleared += cur.rowcount
        cur.execute(
            "UPDATE cp_attempts SET status = 'in_progress', submitted_at = NULL, progress_idx = 0, "
            "       elapsed_seconds = 0, resumed_at = NULL, last_seen = NULL, started_at = NOW() "
            "WHERE id = %s", (attempt_id,))
        return cleared


def store_submission(attempt_id, question_id, *, language, code, verdict,
                     passed, total, score, execution_time, error_message):
    return execute(
        """
        INSERT INTO cp_submissions (attempt_id, question_id, language, code,
            verdict, passed, total, score, execution_time, error_message)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (attempt_id, question_id, language, code, verdict, passed, total,
         score, execution_time, error_message),
    )


def store_submission_cases(submission_id, cases):
    if not cases:
        return
    with get_cursor(commit=True) as cur:
        cur.executemany(
            "INSERT INTO cp_submission_testcases (submission_id, testcase_id, "
            "status, execution_time, output, error_message) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            [(submission_id, c.get("testcase_id"), c.get("status"),
              c.get("execution_time", 0), c.get("output"), c.get("error"))
             for c in cases],
        )


def ensure_share_code(attempt_id):
    import secrets
    row = query_one("SELECT share_code FROM cp_attempts WHERE id = %s", (attempt_id,))
    if not row:
        return None
    if row.get("share_code"):
        return row["share_code"]
    code = secrets.token_urlsafe(12)[:16]
    execute("UPDATE cp_attempts SET share_code = %s "
            "WHERE id = %s AND share_code IS NULL", (code, attempt_id))
    row = query_one("SELECT share_code FROM cp_attempts WHERE id = %s", (attempt_id,))
    return row["share_code"] if row else code


def get_attempt_by_share_code(code):
    return query_one(
        """
        SELECT a.id, a.status, a.submitted_at, a.share_code,
               t.id AS test_id, t.title AS test_title, t.total_duration_min,
               u.username
          FROM cp_attempts a
          JOIN cp_tests t ON t.id = a.test_id
          JOIN auth u ON u.id = a.user_id
         WHERE a.share_code = %s AND a.status = 'submitted'
        """,
        (code,),
    )


def unsubmitted_saved_answers(attempt_id):
    return query_all(
        """
        SELECT a.question_id, a.language, a.code, s.section_type
          FROM cp_answers a
          JOIN cp_questions q ON q.id = a.question_id
          JOIN cp_sections s ON s.id = q.section_id
         WHERE a.attempt_id = %s
           AND s.section_type IN ('coding', 'sql')
           AND a.code IS NOT NULL AND a.code <> ''
           AND NOT EXISTS (SELECT 1 FROM cp_submissions sub
                            WHERE sub.attempt_id = a.attempt_id
                              AND sub.question_id = a.question_id)
        """,
        (attempt_id,),
    )


def pending_auto_grades(limit=20):
    return query_all(
        """
        SELECT a.attempt_id, a.question_id, a.language, a.code, s.section_type, u.email
          FROM cp_answers a
          JOIN cp_attempts t ON t.id = a.attempt_id
          JOIN cp_questions q ON q.id = a.question_id
          JOIN cp_sections s ON s.id = q.section_id
          JOIN auth u ON u.id = t.user_id
         WHERE t.status = 'submitted'
           AND t.submitted_at > NOW() - INTERVAL 6 HOUR
           AND a.code IS NOT NULL AND a.code <> ''
           AND ((s.section_type = 'coding' AND a.language IS NOT NULL
                 AND EXISTS (SELECT 1 FROM cp_testcases tc WHERE tc.question_id = q.id))
             OR (s.section_type = 'sql' AND q.solution_query IS NOT NULL AND q.solution_query <> ''))
           AND NOT EXISTS (SELECT 1 FROM cp_submissions sub
                            WHERE sub.attempt_id = a.attempt_id
                              AND sub.question_id = a.question_id)
         ORDER BY t.submitted_at, a.attempt_id, a.question_id
         LIMIT %s
        """,
        (int(limit),),
    )


def get_attempt_submissions(attempt_id):
    return query_all(
        "SELECT s.*, q.title FROM cp_submissions s "
        "JOIN cp_questions q ON q.id = s.question_id "
        "WHERE s.attempt_id = %s ORDER BY s.created_at DESC",
        (attempt_id,),
    )


def best_scores(attempt_id):
    return query_all(
        "SELECT question_id, MAX(score) AS score, MAX(passed) AS passed "
        "FROM cp_submissions WHERE attempt_id = %s GROUP BY question_id",
        (attempt_id,),
    )
