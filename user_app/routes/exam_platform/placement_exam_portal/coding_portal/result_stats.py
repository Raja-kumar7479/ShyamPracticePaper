"""Everything the coding result page reports, built from what is actually recorded.

The portal stores one row per submission (verdict, test cases passed, score,
judge runtime, code, timestamp), so per-question detail and a cohort comparison
can both be derived without adding new tracking.

One caveat is called out rather than hidden: the portal never recorded how long
a candidate sat on each question. `approx_seconds` below is inferred from the
gaps between consecutive submissions, so it is an estimate and the page labels
it as one. Everything else on the page is measured.
"""
import logging
from datetime import datetime

from .db import query_all

logger = logging.getLogger(__name__)

# Verdicts the judge can return, with the wording students see.
VERDICT_LABEL = {
    'AC': 'Accepted', 'WA': 'Wrong Answer', 'TLE': 'Time Limit Exceeded',
    'MLE': 'Memory Limit Exceeded', 'CE': 'Compile Error',
    'RE': 'Runtime Error', 'IE': 'Internal Error',
}


def _seconds(a, b):
    if not isinstance(a, datetime) or not isinstance(b, datetime):
        return 0
    return max(0, int((b - a).total_seconds()))


def question_rows(attempt, test_id, allotted_minutes=None):
    """Per-question detail: best submission, test cases, tries, code, timing."""
    # case_count comes from the question itself, so a question that was never
    # attempted still reports how many cases it had rather than a bare dash.
    questions = query_all(
        """
        SELECT q.id, q.title, q.marks, q.difficulty, q.position,
               s.section_type, s.title AS section_title, s.position AS sec_pos,
               (SELECT COUNT(*) FROM cp_testcases tc WHERE tc.question_id = q.id) AS case_count
          FROM cp_questions q
          JOIN cp_sections s ON s.id = q.section_id
         WHERE s.test_id = %s
         ORDER BY s.position, s.id, q.position, q.id
        """,
        (test_id,),
    )

    subs = query_all(
        """
        SELECT id, question_id, language, code, verdict, passed, total, score,
               execution_time, error_message, created_at
          FROM cp_submissions
         WHERE attempt_id = %s
         ORDER BY created_at, id
        """,
        (attempt['id'],),
    )

    # Time is attributed to whichever question was submitted at the end of each
    # gap, starting from when the attempt opened.
    # A gap is capped at the allotted duration, so an attempt that sat open
    # overnight cannot attribute hours of idle time to one question.
    cap = int(allotted_minutes or 0) * 60
    approx = {}
    prev = attempt.get('started_at')
    for s in subs:
        gap = _seconds(prev, s['created_at'])
        if cap:
            gap = min(gap, cap)
        approx[s['question_id']] = approx.get(s['question_id'], 0) + gap
        prev = s['created_at'] or prev
    if cap:
        approx = {qid: min(secs, cap) for qid, secs in approx.items()}

    by_q = {}
    for s in subs:
        by_q.setdefault(s['question_id'], []).append(s)

    # Autosaved drafts. A question the candidate wrote code for but never ran
    # through Submit Code must still show that code on the result page instead
    # of a bare "Not attempted".
    saved = {a['question_id']: a for a in query_all(
        """
        SELECT question_id, language, code, is_attempted
          FROM cp_answers
         WHERE attempt_id = %s AND code IS NOT NULL AND code <> ''
        """,
        (attempt['id'],),
    )}

    rows = []
    for q in questions:
        tries = by_q.get(q['id'], [])
        # The score that counts is the best one, and the latest of equal bests.
        best = max(tries, key=lambda s: (s['score'] or 0, s['id'])) if tries else None
        draft = saved.get(q['id']) if not best else None
        row = dict(q)
        row.update({
            'tries': len(tries),
            'verdict': best['verdict'] if best else None,
            'verdict_label': (VERDICT_LABEL.get(best['verdict'], best['verdict']) if best
                              else ('Saved, not submitted' if draft else 'Not attempted')),
            'passed': (best['passed'] or 0) if best else 0,
            # Fall back to the question's own case count, so an unattempted
            # question reads "0 / 3" instead of "0 / -".
            'total_cases': ((best['total'] or 0) if best else 0) or int(q.get('case_count') or 0),
            'score': (best['score'] or 0) if best else 0,
            'runtime_ms': round((best['execution_time'] or 0) * 1000) if best else None,
            'language': best['language'] if best else (draft['language'] if draft else None),
            'code': best['code'] if best else (draft['code'] if draft else None),
            'error_message': best['error_message'] if best else None,
            'first_at': tries[0]['created_at'] if tries else None,
            'last_at': tries[-1]['created_at'] if tries else None,
            'approx_seconds': approx.get(q['id'], 0),
        })
        row['case_pct'] = round(100 * row['passed'] / row['total_cases']) if row['total_cases'] else 0
        row['solved'] = row['verdict'] == 'AC'
        rows.append(row)
    return rows


def cohort(test_id, attempt_id):
    """How this attempt compares with everyone who finished the same test."""
    totals = query_all(
        """
        SELECT t.attempt_id, SUM(t.best) AS total
          FROM (SELECT attempt_id, question_id, MAX(score) AS best
                  FROM cp_submissions
                 GROUP BY attempt_id, question_id) t
          JOIN cp_attempts a ON a.id = t.attempt_id
         WHERE a.test_id = %s AND a.status = 'submitted'
         GROUP BY t.attempt_id
        """,
        (test_id,),
    )
    scores = sorted((float(r['total'] or 0) for r in totals), reverse=True)
    mine = next((float(r['total'] or 0) for r in totals if r['attempt_id'] == attempt_id), 0.0)

    if not scores:
        return {'participants': 0, 'topper': 0, 'average': 0, 'mine': mine,
                'rank': None, 'percentile': None, 'beaten': 0}

    rank = sum(1 for s in scores if s > mine) + 1
    beaten = sum(1 for s in scores if s < mine)
    return {
        'participants': len(scores),
        'topper': round(scores[0], 2),
        'average': round(sum(scores) / len(scores), 2),
        'mine': round(mine, 2),
        'rank': rank,
        'percentile': round(100 * beaten / len(scores)) if len(scores) > 1 else 100,
        'beaten': beaten,
    }


def summary(attempt, rows, cohort_stats, allotted_minutes=None):
    solved = sum(1 for r in rows if r['solved'])
    attempted = sum(1 for r in rows if r['verdict'])
    cases_passed = sum(r['passed'] for r in rows)
    cases_total = sum(r['total_cases'] for r in rows)
    score = sum(r['score'] for r in rows)
    max_score = sum(r['marks'] or 0 for r in rows)

    # Time actually spent in the exam. elapsed_seconds is accumulated on the
    # server while the attempt is on screen (paused when the candidate leaves,
    # folded on submit), so a resumed attempt no longer reports absent days -
    # a 60 minute test was showing "2h 01m". Attempts predating that column
    # fall back to wall clock, still capped at the allotted duration.
    allotted = int(allotted_minutes or 0) * 60
    elapsed = attempt.get('elapsed_seconds')
    if elapsed is None:
        elapsed = _seconds(attempt.get('started_at'), attempt.get('submitted_at'))
    elapsed = int(elapsed or 0)
    duration = min(elapsed, allotted) if allotted else elapsed
    ran_over = bool(allotted and elapsed > allotted)

    return {
        'score': score,
        'max_score': max_score,
        'score_pct': round(100 * score / max_score) if max_score else 0,
        'solved': solved,
        'attempted': attempted,
        'total_questions': len(rows),
        'unattempted': len(rows) - attempted,
        'cases_passed': cases_passed,
        'cases_total': cases_total,
        'case_pct': round(100 * cases_passed / cases_total) if cases_total else 0,
        'tries': sum(r['tries'] for r in rows),
        'duration_seconds': duration,
        'allotted_seconds': allotted,
        'ran_over': ran_over,
        'time_used_pct': round(100 * duration / allotted) if allotted else 0,
        'avg_seconds_per_question': round(duration / len(rows)) if rows and duration else 0,
        'vs_average': round(score - (cohort_stats['average'] or 0), 2),
        'vs_topper': round(score - (cohort_stats['topper'] or 0), 2),
    }


def fmt_duration(seconds):
    seconds = int(seconds or 0)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60:02d}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60:02d}m"
