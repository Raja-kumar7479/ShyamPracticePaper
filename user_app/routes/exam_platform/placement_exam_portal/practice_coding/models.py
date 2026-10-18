from datetime import datetime

from routes.db_pool import get_connection

LANGUAGES = ["python", "java", "c", "cpp", "csharp", "javascript"]
DIFFICULTIES = ["Easy", "Moderate", "Hard"]


def _all(sql, params=None):
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(sql, params or ())
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def _one(sql, params=None):
    rows = _all(sql, params)
    return rows[0] if rows else None


def _write(sql, params=None):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(sql, params or ())
        conn.commit()
        return cur.lastrowid or cur.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


PAGE_SIZE = 100

PREVIEW_FREE_LIMIT = 20


def preview_question_ids(subject=None, limit=PREVIEW_FREE_LIMIT):
    tail, params = "", []
    if subject:
        tail = " AND subject = %s"
        params.append(subject)
    rows = _all(
        "SELECT id FROM pcp_questions "
        "WHERE is_active = 1 AND is_paid = 0 "
        "  AND id NOT IN (SELECT question_id FROM pcp_question_companies)"
        + tail + " ORDER BY position, id LIMIT %s",
        tuple(params + [int(limit)]))
    return {r["id"] for r in rows}


def _question_filters(subject, difficulty, paid, search):
    sql, params = "", []
    if subject:
        sql += " AND q.subject = %s"
        params.append(subject)
    if difficulty:
        sql += " AND q.difficulty = %s"
        params.append(difficulty)
    if paid is not None:
        sql += " AND q.is_paid = %s"
        params.append(1 if paid else 0)
    if search:
        sql += " AND q.title LIKE %s"
        params.append('%' + search + '%')
    return sql, params


def _status_clause(status, user_id):
    if status not in ("solved", "attempted", "todo") or not user_id:
        return "", []

    solved_count = ("(SELECT SUM(verdict = 'AC') FROM pcp_submissions s2 "
                    " WHERE s2.question_id = q.id AND s2.user_id = %s)")
    has_tried = ("EXISTS (SELECT 1 FROM pcp_submissions s3 "
                 " WHERE s3.question_id = q.id AND s3.user_id = %s)")

    if status == "solved":
        return f" AND COALESCE({solved_count}, 0) > 0", [user_id]
    if status == "attempted":
        return f" AND {has_tried} AND COALESCE({solved_count}, 0) = 0", [user_id, user_id]
    return f" AND NOT {has_tried}", [user_id]


def count_questions(subject=None, difficulty=None, paid=None, search=None,
                    status=None, user_id=None):
    tail, params = _question_filters(subject, difficulty, paid, search)
    status_sql, status_params = _status_clause(status, user_id)
    params.extend(status_params)
    row = _one(
        "SELECT COUNT(*) AS n FROM pcp_questions q "
        "WHERE q.is_active = 1 "
        "  AND q.id NOT IN (SELECT question_id FROM pcp_question_companies)"
        + tail + status_sql,
        tuple(params))
    return int(row["n"]) if row else 0


SORTS = {
    "default": "q.position, q.id",
    "title": "q.title ASC",
    "title_desc": "q.title DESC",
    "difficulty": "FIELD(q.difficulty, 'Easy', 'Moderate', 'Hard'), q.position",
    "difficulty_desc": "FIELD(q.difficulty, 'Hard', 'Moderate', 'Easy'), q.position",
    "acceptance": "acceptance IS NULL, acceptance ASC",
    "acceptance_desc": "acceptance IS NULL, acceptance DESC",
}


def list_questions(subject=None, difficulty=None, paid=None, search=None,
                   limit=PAGE_SIZE, offset=0, status=None, user_id=None,
                   sort="default"):
    tail, params = _question_filters(subject, difficulty, paid, search)
    sql = """
        SELECT q.id, q.title, q.slug, q.difficulty, q.subject, q.is_paid, q.position,
               ROUND(100 * agg.accepted / agg.attempts, 1) AS acceptance
        FROM pcp_questions q
        LEFT JOIN (
            SELECT question_id,
                   COUNT(*) AS attempts,
                   SUM(verdict = 'AC') AS accepted
              FROM pcp_submissions
             GROUP BY question_id
        ) agg ON agg.question_id = q.id
        WHERE q.is_active = 1
          AND q.id NOT IN (SELECT question_id FROM pcp_question_companies)
    """ + tail

    status_sql, status_params = _status_clause(status, user_id)
    sql += status_sql
    params.extend(status_params)

    sql += " ORDER BY " + SORTS.get(sort or "default", SORTS["default"])
    sql += " LIMIT %s OFFSET %s"
    params.extend([int(limit), int(offset)])
    return _all(sql, tuple(params))


def subject_counts():
    return _all("""
        SELECT subject, COUNT(*) AS n
        FROM pcp_questions
        WHERE is_active = 1
          AND id NOT IN (SELECT question_id FROM pcp_question_companies)
        GROUP BY subject ORDER BY n DESC, subject
    """)


def get_question(question_id):
    return _one("SELECT * FROM pcp_questions WHERE id = %s AND is_active = 1",
                (question_id,))


def get_question_by_slug(slug):
    return _one("SELECT * FROM pcp_questions WHERE slug = %s AND is_active = 1",
                (slug,))


def slug_for(question_id):
    row = _one("SELECT slug FROM pcp_questions WHERE id = %s", (question_id,))
    return row["slug"] if row and row.get("slug") else None


def get_templates(question_id):
    return {r["language"]: r["template_code"] for r in _all(
        "SELECT language, template_code FROM pcp_templates WHERE question_id = %s",
        (question_id,))}


def get_testcases(question_id, include_hidden=True):
    sql = ("SELECT id, input_text, expected_output, is_hidden FROM pcp_testcases "
           "WHERE question_id = %s")
    if not include_hidden:
        sql += " AND is_hidden = 0"
    return _all(sql + " ORDER BY position, id", (question_id,))


def record_submission(user_id, question_id, language, code, result):
    return _write("""
        INSERT INTO pcp_submissions
          (user_id, question_id, language, code, verdict, passed, total,
           execution_time, error_message)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (user_id, question_id, language, code, result["verdict"],
          result["passed"], result["total"], result.get("execution_time", 0),
          result.get("error_message")))


def solved_question_ids(user_id):
    return {r["question_id"] for r in _all(
        "SELECT DISTINCT question_id FROM pcp_submissions "
        "WHERE user_id = %s AND verdict = 'AC'", (user_id,))}


def attempted_question_ids(user_id):
    return {r["question_id"] for r in _all(
        "SELECT question_id FROM pcp_submissions WHERE user_id = %s "
        "GROUP BY question_id HAVING SUM(verdict = 'AC') = 0", (user_id,))}


def practice_stats(user_id):
    rows = _all("""
        SELECT q.difficulty,
               COUNT(DISTINCT q.id) AS total,
               COUNT(DISTINCT CASE WHEN s.solved > 0 THEN q.id END) AS solved
          FROM pcp_questions q
          LEFT JOIN (SELECT question_id, SUM(verdict = 'AC') AS solved
                       FROM pcp_submissions WHERE user_id = %s
                      GROUP BY question_id) s ON s.question_id = q.id
         WHERE q.is_active = 1
           AND q.id NOT IN (SELECT question_id FROM pcp_question_companies)
         GROUP BY q.difficulty
    """, (user_id,))
    by_difficulty = {r["difficulty"]: {"total": int(r["total"]), "solved": int(r["solved"] or 0)}
                     for r in rows}
    return {
        "by_difficulty": by_difficulty,
        "total": sum(v["total"] for v in by_difficulty.values()),
        "solved": sum(v["solved"] for v in by_difficulty.values()),
    }


def recent_submissions(user_id, question_id, limit=10):
    return _all("""
        SELECT id, language, code, verdict, passed, total, execution_time,
               error_message, created_at
        FROM pcp_submissions WHERE user_id = %s AND question_id = %s
        ORDER BY id DESC LIMIT %s
    """, (user_id, question_id, int(limit)))


def get_editorials(question_id):
    approaches = _all("""
        SELECT id, position, title, intro_html, outro_html,
               time_complexity, space_complexity
          FROM pcp_editorials
         WHERE question_id = %s AND is_published = 1
         ORDER BY position, id
    """, (question_id,))
    if not approaches:
        return []

    ids = [a["id"] for a in approaches]
    placeholders = ",".join(["%s"] * len(ids))
    code_rows = _all(
        f"SELECT editorial_id, language, code FROM pcp_editorial_code "
        f"WHERE editorial_id IN ({placeholders})", tuple(ids))

    by_editorial = {}
    for r in code_rows:
        by_editorial.setdefault(r["editorial_id"], {})[r["language"]] = r["code"]

    order = {lang: i for i, lang in enumerate(LANGUAGES)}
    for a in approaches:
        codes = by_editorial.get(a["id"], {})
        a["codes"] = sorted(
            ({"language": lang, "code": code} for lang, code in codes.items() if code),
            key=lambda c: order.get(c["language"], 99))
    return approaches


def is_bookmarked(user_id, question_id):
    return _one("SELECT id FROM pcp_bookmarks WHERE user_id = %s AND question_id = %s",
                (user_id, question_id)) is not None


def bookmarked_question_ids(user_id):
    return {r["question_id"] for r in _all(
        "SELECT question_id FROM pcp_bookmarks WHERE user_id = %s", (user_id,))}


def bookmarked_questions(user_id):
    return _all("""
        SELECT q.id, q.title, q.slug, q.difficulty, q.subject, q.is_paid,
               b.created_at AS saved_at,
               COALESCE(s.attempts, 0)  AS attempts,
               COALESCE(s.accepted, 0)  AS accepted
          FROM pcp_bookmarks b
          JOIN pcp_questions q ON q.id = b.question_id
          LEFT JOIN (SELECT question_id,
                            COUNT(*) AS attempts,
                            SUM(verdict = 'AC') AS accepted
                       FROM pcp_submissions WHERE user_id = %s
                      GROUP BY question_id) s ON s.question_id = q.id
         WHERE b.user_id = %s AND q.is_active = 1
         ORDER BY b.created_at DESC, q.id
    """, (user_id, user_id))


def toggle_bookmark(user_id, question_id):
    if is_bookmarked(user_id, question_id):
        _write("DELETE FROM pcp_bookmarks WHERE user_id = %s AND question_id = %s",
               (user_id, question_id))
        return False
    _write("INSERT INTO pcp_bookmarks (user_id, question_id) VALUES (%s, %s)",
           (user_id, question_id))
    return True


def list_companies():
    return _all("""
        SELECT c.id, c.name, c.slug,
               COUNT(qc.question_id) AS question_count
        FROM pcp_companies c
        LEFT JOIN pcp_question_companies qc ON qc.company_id = c.id
        LEFT JOIN pcp_questions q ON q.id = qc.question_id AND q.is_active = 1
        WHERE c.slug <> '__seeded__'
        GROUP BY c.id, c.name, c.slug
        ORDER BY question_count DESC, c.position, c.name
    """)


def get_company(slug):
    return _one("SELECT * FROM pcp_companies WHERE slug = %s", (slug,))


def company_questions(company_id):
    return _all("""
        SELECT q.id, q.title, q.slug, q.difficulty, q.subject, q.is_paid,
               (SELECT ROUND(100 * SUM(s.verdict = 'AC') / COUNT(*), 1)
                  FROM pcp_submissions s WHERE s.question_id = q.id) AS acceptance
        FROM pcp_questions q
        JOIN pcp_question_companies qc ON qc.question_id = q.id
        WHERE qc.company_id = %s AND q.is_active = 1
        ORDER BY q.position, q.id
    """, (company_id,))


def companies_for_questions(question_ids):
    if not question_ids:
        return {}
    marks = ','.join(['%s'] * len(question_ids))
    rows = _all(f"""
        SELECT qc.question_id, c.name
        FROM pcp_question_companies qc
        JOIN pcp_companies c ON c.id = qc.company_id
        WHERE qc.question_id IN ({marks})
        ORDER BY c.name
    """, tuple(question_ids))
    out = {}
    for r in rows:
        out.setdefault(r['question_id'], []).append(r['name'])
    return out


def daily_challenge(on_date=None):
    rows = _all("SELECT id FROM pcp_questions WHERE is_active = 1 ORDER BY id")
    if not rows:
        return None
    day = (on_date or datetime.now().date()).toordinal()
    pick = rows[day % len(rows)]['id']
    return _one("SELECT id, title, difficulty, subject, is_paid "
                "FROM pcp_questions WHERE id = %s", (pick,))


def solve_streak(user_id):
    rows = _all("""
        SELECT DISTINCT DATE(created_at) AS d FROM pcp_submissions
        WHERE user_id = %s AND verdict = 'AC'
        ORDER BY d DESC LIMIT 366
    """, (user_id,))
    days = [r['d'] for r in rows]
    if not days:
        return 0
    from datetime import date, timedelta
    today = date.today()
    if days[0] not in (today, today - timedelta(days=1)):
        return 0
    streak = 1
    for previous, current in zip(days, days[1:]):
        if (previous - current).days == 1:
            streak += 1
        else:
            break
    return streak


def monthly_leaderboard(limit=10):
    return _all("""
        SELECT u.id AS user_id, u.username,
               COUNT(DISTINCT s.question_id) AS solved,
               MIN(s.created_at) AS first_ac
        FROM pcp_submissions s
        JOIN auth u ON u.id = s.user_id
        WHERE s.verdict = 'AC'
          AND s.created_at >= (CURDATE() - INTERVAL (DAY(CURDATE()) - 1) DAY)
        GROUP BY u.id, u.username
        ORDER BY solved DESC, first_ac ASC
        LIMIT {}
    """.format(int(limit)))


def subject_progress(user_id):
    return _all("""
        SELECT q.subject,
               COUNT(*) AS total,
               COUNT(DISTINCT CASE WHEN s.verdict = 'AC' THEN q.id END) AS solved
        FROM pcp_questions q
        LEFT JOIN pcp_submissions s
               ON s.question_id = q.id AND s.user_id = %s AND s.verdict = 'AC'
        WHERE q.is_active = 1
        GROUP BY q.subject
        ORDER BY total DESC, q.subject
    """, (user_id,))


def random_unsolved(user_id, premium):
    sql = """
        SELECT q.id FROM pcp_questions q
        WHERE q.is_active = 1
          AND q.id NOT IN (SELECT question_id FROM pcp_question_companies)
          AND q.id NOT IN (SELECT question_id FROM pcp_submissions
                            WHERE user_id = %s AND verdict = 'AC')
    """
    params = [user_id]
    if not premium:
        sql += " AND q.is_paid = 0"
    sql += " ORDER BY RAND() LIMIT 1"
    row = _one(sql, tuple(params))
    return row['id'] if row else None


def active_subscription(email, course_code=None):
    if not email:
        return None
    if course_code:
        return _one("""
            SELECT * FROM pcp_subscriptions
            WHERE email = %s AND status = 'active' AND expires_at > %s
              AND (course_code = %s OR course_code IS NULL)
            ORDER BY expires_at DESC LIMIT 1
        """, (email, datetime.now(), course_code))
    return _one("""
        SELECT * FROM pcp_subscriptions
        WHERE email = %s AND status = 'active' AND expires_at > %s
        ORDER BY expires_at DESC LIMIT 1
    """, (email, datetime.now()))


def active_subscriptions(email):
    if not email:
        return []
    return _all("""
        SELECT * FROM pcp_subscriptions
        WHERE email = %s AND status = 'active' AND expires_at > %s
        ORDER BY expires_at ASC
    """, (email, datetime.now()))


def create_subscription_order(email, plan, amount_paise, order_id, phone=None, course_code=None,
                              list_paise=None, discount_pct=None, plan_label=None, plan_ends_at=None):
    return _write("""
        INSERT INTO pcp_subscriptions
            (email, plan, plan_label, amount_paise, razorpay_order_id, phone, course_code, list_paise, discount_pct, plan_ends_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (email, plan, plan_label or plan, amount_paise, order_id, phone, course_code, list_paise, discount_pct, plan_ends_at))


def get_subscription_by_payment(payment_id):
    return _one("SELECT * FROM pcp_subscriptions WHERE razorpay_payment_id = %s "
                "ORDER BY id DESC LIMIT 1", (payment_id,))


def subscription_history(email):
    return _all("SELECT * FROM pcp_subscriptions WHERE email = %s AND status = 'active' "
                "ORDER BY starts_at DESC, id DESC", (email,))


def get_subscription_by_order(order_id):
    return _one("SELECT * FROM pcp_subscriptions WHERE razorpay_order_id = %s",
                (order_id,))


def activate_subscription(order_id, payment_id, starts_at, expires_at, fulfilled_by='browser'):
    return _write("""
        UPDATE pcp_subscriptions
           SET status = 'active', razorpay_payment_id = %s, gateway_status = 'captured', fulfilled_by = %s,
               starts_at = %s, expires_at = %s
         WHERE razorpay_order_id = %s AND status = 'created'
    """, (payment_id, fulfilled_by, starts_at, expires_at, order_id))
