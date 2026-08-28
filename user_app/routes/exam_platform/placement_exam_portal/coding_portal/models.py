"""Data access for tests, sections, questions, attempts and submissions."""
from .db import query_all, query_one, execute, get_cursor

LANGUAGES = ["python", "java", "c", "cpp", "csharp", "javascript"]
SECTION_TYPES = ["coding", "sql", "web"]


# --- tests / sections ---

def list_published_tests(course_code=None, test_id=None):
    """Published coding tests, scoped to the course the student came from.

    Without a scope this listed every coding test on the platform, so a student
    opening one course's coding round saw other courses' tests too. test_id
    narrows it further to a single content block when the caller knows which
    one was clicked.
    """
    sql = ("SELECT id, slug, title, description, total_duration_min "
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
    # question_count is carried here so the lobby can show what each section
    # holds without a second query per row.
    return query_all(
        "SELECT s.id, s.title, s.section_type, s.duration_min, s.position, "
        "       (SELECT COUNT(*) FROM cp_questions q WHERE q.section_id = s.id) AS question_count "
        "FROM cp_sections s WHERE s.test_id = %s ORDER BY s.position, s.id",
        (test_id,),
    )


def get_section(section_id):
    return query_one("SELECT * FROM cp_sections WHERE id = %s", (section_id,))


# --- questions ---

def get_questions(section_id):
    return query_all(
        "SELECT id, position, title, marks FROM cp_questions "
        "WHERE section_id = %s ORDER BY position, id",
        (section_id,),
    )


def get_question(question_id):
    return query_one("SELECT * FROM cp_questions WHERE id = %s", (question_id,))


def get_question_full(question_id):
    """Question plus the extras its section type needs."""
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


# --- attempts ---

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
    """Start (or continue) the active-time segment when the exam is on screen."""
    execute(
        "UPDATE cp_attempts SET resumed_at = NOW() "
        "WHERE id = %s AND resumed_at IS NULL AND status = 'in_progress'",
        (attempt_id,),
    )


def pause_clock(attempt_id):
    """Fold the running segment into elapsed_seconds; the timer stops while
    the candidate is away and continues when they resume."""
    execute(
        "UPDATE cp_attempts SET "
        "  elapsed_seconds = elapsed_seconds + "
        "    IFNULL(TIMESTAMPDIFF(SECOND, resumed_at, NOW()), 0), "
        "  resumed_at = NULL "
        "WHERE id = %s AND status = 'in_progress'", (attempt_id,),
    )


def active_seconds(attempt_id):
    """Time actually spent in the exam, computed entirely in DB time so the
    application clock can never skew the timer."""
    row = query_one(
        "SELECT elapsed_seconds + "
        "       IFNULL(TIMESTAMPDIFF(SECOND, resumed_at, NOW()), 0) AS secs "
        "FROM cp_attempts WHERE id = %s", (attempt_id,),
    )
    return int(row["secs"] or 0) if row else 0


# --- answers (autosave) ---

def save_answer(attempt_id, question_id, *, language=None, code=None,
                code_html=None, code_css=None, code_js=None, attempted=None):
    """
    Upsert a draft answer.

    COALESCE on update keeps columns the caller did not send -- a coding
    autosave must not blank the web editors and vice versa.
    """
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


def get_attempted_map(attempt_id, section_id):
    rows = query_all(
        "SELECT a.question_id, a.is_attempted FROM cp_answers a "
        "JOIN cp_questions q ON q.id = a.question_id "
        "WHERE a.attempt_id = %s AND q.section_id = %s",
        (attempt_id, section_id),
    )
    return {r["question_id"]: bool(r["is_attempted"]) for r in rows}


# --- submissions ---

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
    """The attempt's public certificate code, minted on first use. Random and
    unguessable, so the certificate URL can be public without exposing ids."""
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
    """Certificate lookup: the submitted attempt plus what the public page may
    show - the student's display name, never their email."""
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
    """Coding answers the candidate wrote (autosaved) but never ran through
    Submit Code. Finish grades these so written work is never scored as
    'not attempted'."""
    return query_all(
        """
        SELECT a.question_id, a.language, a.code
          FROM cp_answers a
          JOIN cp_questions q ON q.id = a.question_id
          JOIN cp_sections s ON s.id = q.section_id
         WHERE a.attempt_id = %s
           AND s.section_type = 'coding'
           AND a.code IS NOT NULL AND a.code <> ''
           AND NOT EXISTS (SELECT 1 FROM cp_submissions sub
                            WHERE sub.attempt_id = a.attempt_id
                              AND sub.question_id = a.question_id)
        """,
        (attempt_id,),
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
