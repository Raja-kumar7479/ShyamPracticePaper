import random
from datetime import datetime

from .models import _all, _one, _write

OPTIONS = ('A', 'B', 'C', 'D')
MODES = ('quiz', 'assessment')


def subjects(premium):
    rows = _all("""
        SELECT subject,
               COUNT(*) AS total,
               SUM(is_paid = 0) AS free_count,
               SUM(is_paid = 1) AS paid_count
        FROM pcq_questions WHERE is_active = 1
        GROUP BY subject ORDER BY total DESC, subject
    """)
    for r in rows:
        r['available'] = r['total'] if premium else r['free_count']
    return rows


def questions_for_taking(subject, premium, limit=30):
    sql = """
        SELECT id, question_text, question_image,
               option_a, option_b, option_c, option_d, is_paid
        FROM pcq_questions WHERE is_active = 1 AND subject = %s
    """
    params = [subject]
    if not premium:
        sql += " AND is_paid = 0"
    rows = _all(sql + " ORDER BY position, id", tuple(params))
    random.shuffle(rows)
    return rows[:limit]


def answer_key(question_ids, subject=None):
    if not question_ids:
        return {}
    marks = ','.join(['%s'] * len(question_ids))
    sql = (f"SELECT id, subject, correct_option, explanation, is_paid "
           f"FROM pcq_questions WHERE id IN ({marks}) AND is_active = 1")
    params = list(question_ids)
    if subject is not None:
        sql += " AND subject = %s"
        params.append(subject)
    return {r['id']: r for r in _all(sql, tuple(params))}


def get_question(question_id):
    return _one("SELECT * FROM pcq_questions WHERE id = %s AND is_active = 1",
                (question_id,))


def create_attempt(user_id, subject, mode, total):
    return _write("""
        INSERT INTO pcq_attempts (user_id, subject, mode, total)
        VALUES (%s,%s,%s,%s)
    """, (user_id, subject, mode, total))


def get_attempt(attempt_id, user_id):
    return _one("SELECT * FROM pcq_attempts WHERE id = %s AND user_id = %s",
                (attempt_id, user_id))


def record_answer(attempt_id, question_id, selected, is_correct):
    return _write("""
        INSERT INTO pcq_attempt_answers (attempt_id, question_id, selected, is_correct)
        VALUES (%s,%s,%s,%s)
    """, (attempt_id, question_id, selected, is_correct))


def has_answered(attempt_id, question_id):
    return _one("SELECT id FROM pcq_attempt_answers WHERE attempt_id = %s AND question_id = %s",
                (attempt_id, question_id)) is not None


def finish_attempt(attempt_id, total, correct, wrong, skipped):
    return _write("""
        UPDATE pcq_attempts
           SET status = 'finished', total = %s, correct = %s, wrong = %s,
               skipped = %s, finished_at = %s
         WHERE id = %s AND status = 'in_progress'
    """, (total, correct, wrong, skipped, datetime.now(), attempt_id))


def attempt_review(attempt_id):
    return _all("""
        SELECT q.id, q.question_text, q.question_image,
               q.option_a, q.option_b, q.option_c, q.option_d,
               q.correct_option, q.explanation,
               a.selected, a.is_correct
        FROM pcq_attempt_answers a
        JOIN pcq_questions q ON q.id = a.question_id
        WHERE a.attempt_id = %s
        ORDER BY a.id
    """, (attempt_id,))


def recent_attempts(user_id, limit=8):
    return _all("""
        SELECT id, subject, mode, total, correct, wrong, skipped, created_at, status
        FROM pcq_attempts WHERE user_id = %s AND status = 'finished'
        ORDER BY id DESC LIMIT %s
    """, (user_id, int(limit)))


def premium_quiz_count():
    row = _one("SELECT COUNT(*) AS n FROM pcq_questions WHERE is_active = 1 AND is_paid = 1")
    return row['n'] if row else 0
