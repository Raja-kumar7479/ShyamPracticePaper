"""Quiz / assessment pages and APIs.

Mode contract:
  quiz       - the browser collects picks locally and submits them all at the
               end; the server grades in one shot and builds the attempt.
  assessment - every pick is POSTed immediately; the server records it (the DB
               unique key makes it final) and only then returns the correct
               option and explanation for the instant-feedback panel.

In both modes the answer key never appears in a page or a pre-answer response.
"""
import logging

from flask import abort, jsonify, redirect, render_template, request, url_for

from extensions import limiter
from . import models_quiz as quiz
from .auth import csrf_protect, current_user, login_required
from .routes_practice import bp, has_premium

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------
@bp.route("/quiz")
@bp.route("/quiz/<course_code>/<unique_code>")
@login_required
def quiz_home():
    user = current_user()
    premium = has_premium(user["email"])
    return render_template(
        "users/exam_platform/placement_exam_portal/practice_coding/quiz_home.html",
        user=user, premium=premium,
        subjects=quiz.subjects(premium),
        recent_count=len(quiz.recent_attempts(user["id"])),
        premium_quiz_count=quiz.premium_quiz_count())


@bp.route("/quiz/attempts")
@bp.route("/quiz/attempts/<course_code>/<unique_code>")
@login_required
def quiz_attempts():
    """Past attempts on their own page, reached from the sidebar.

    They used to sit at the bottom of the subject list, which pushed the
    subjects up and grew without limit as a student practised.
    """
    user = current_user()
    return render_template(
        "users/exam_platform/placement_exam_portal/practice_coding/quiz_attempts.html",
        user=user, premium=has_premium(user["email"]),
        recent=quiz.recent_attempts(user["id"], limit=50))


@bp.route("/quiz/<subject>/start")
@bp.route("/quiz/<subject>/start/<course_code>/<unique_code>")
@login_required
def quiz_start(subject):
    user = current_user()
    mode = request.args.get("mode", "quiz")
    if mode not in quiz.MODES:
        mode = "quiz"
    premium = has_premium(user["email"])

    questions = quiz.questions_for_taking(subject, premium)
    if not questions:
        return redirect(url_for("practice_coding.quiz_home"))

    attempt_id = quiz.create_attempt(user["id"], subject, mode, len(questions))
    logger.info("QUIZ: [%s] started %s on %r (%d questions, attempt %s)",
                user["email"], mode, subject, len(questions), attempt_id)
    return render_template(
        "users/exam_platform/placement_exam_portal/practice_coding/quiz_window.html",
        user=user, subject=subject, mode=mode,
        attempt_id=attempt_id, questions=questions)


@bp.route("/quiz/review/<int:attempt_id>")
@bp.route("/quiz/review/<int:attempt_id>/<course_code>/<unique_code>")
@login_required
def quiz_review(attempt_id):
    user = current_user()
    attempt = quiz.get_attempt(attempt_id, user["id"])
    if not attempt:
        abort(404)
    if attempt["status"] != "finished":
        return redirect(url_for("practice_coding.quiz_home"))
    return render_template(
        "users/exam_platform/placement_exam_portal/practice_coding/quiz_review.html",
        user=user, attempt=attempt, rows=quiz.attempt_review(attempt_id))


# --------------------------------------------------------------------------
# APIs
# --------------------------------------------------------------------------
def _own_open_attempt(attempt_id):
    user = current_user()
    attempt = quiz.get_attempt(attempt_id or 0, user["id"])
    if not attempt:
        return None, None, (jsonify({"error": "Unknown attempt"}), 404)
    if attempt["status"] != "in_progress":
        return None, None, (jsonify({"error": "This attempt is already finished"}), 409)
    return user, attempt, None


@bp.route("/quiz/api/answer", methods=["POST"])
@login_required
@csrf_protect
@limiter.limit("120 per minute")
def quiz_answer(**kwargs):
    """Assessment mode: commit one pick, then reveal the truth."""
    data = request.get_json(silent=True) or {}
    user, attempt, error = _own_open_attempt(data.get("attempt_id"))
    if error:
        return error
    if attempt["mode"] != "assessment":
        return jsonify({"error": "This attempt is not in assessment mode"}), 400

    question_id = data.get("question_id")
    selected = (data.get("selected") or "").upper()
    if selected not in quiz.OPTIONS:
        return jsonify({"error": "Pick one of the four options"}), 400

    # Scoped to the attempt's subject: an id from another subject cannot have
    # its answer revealed inside this attempt.
    key = quiz.answer_key([question_id], subject=attempt["subject"]).get(question_id)
    if not key:
        return jsonify({"error": "Unknown question"}), 404
    if key["is_paid"] and not has_premium(user["email"]):
        return jsonify({"error": "premium_required"}), 402
    if quiz.has_answered(attempt["id"], question_id):
        # The lock: the first committed answer is the only one that counts.
        return jsonify({"error": "already_answered",
                        "message": "You already answered this question."}), 409

    is_correct = selected == key["correct_option"]
    try:
        quiz.record_answer(attempt["id"], question_id, selected, is_correct)
    except Exception:
        # Two simultaneous submits raced past the check above; the unique key
        # kept the first one, so this one is simply "already answered".
        return jsonify({"error": "already_answered",
                        "message": "You already answered this question."}), 409
    return jsonify({"correct_option": key["correct_option"],
                    "explanation": key["explanation"],
                    "is_correct": is_correct})


@bp.route("/quiz/api/finish", methods=["POST"])
@login_required
@csrf_protect
@limiter.limit("30 per minute")
def quiz_finish(**kwargs):
    """Quiz mode: grade every pick at once. Assessment mode: close the attempt
    from the answers already recorded one by one."""
    data = request.get_json(silent=True) or {}
    user, attempt, error = _own_open_attempt(data.get("attempt_id"))
    if error:
        return error

    if attempt["mode"] == "quiz":
        answers = data.get("answers") or {}
        if not isinstance(answers, dict) or len(answers) > 200:
            return jsonify({"error": "Bad answers payload"}), 400
        try:
            picked = {int(k): (str(v) or "").upper() for k, v in answers.items()}
        except (TypeError, ValueError):
            return jsonify({"error": "Bad answers payload"}), 400

        # Subject-scoped, and capped at the attempt's size: padding the payload
        # with extra ids (from other subjects or beyond the served set) cannot
        # inflate the score past what was actually asked.
        key = quiz.answer_key(list(picked.keys()), subject=attempt["subject"])
        premium = has_premium(user["email"])
        total = attempt["total"]
        correct = wrong = graded = 0
        for question_id, row in key.items():
            if graded >= total:
                break
            if row["is_paid"] and not premium:
                continue
            selected = picked.get(question_id)
            if selected not in quiz.OPTIONS:
                continue
            ok = selected == row["correct_option"]
            try:
                quiz.record_answer(attempt["id"], question_id, selected, ok)
            except Exception:
                continue  # duplicate id in payload: first one stands
            graded += 1
            if ok:
                correct += 1
            else:
                wrong += 1
        skipped = max(0, total - correct - wrong)
    else:
        rows = quiz.attempt_review(attempt["id"])
        correct = sum(1 for r in rows if r["is_correct"])
        wrong = sum(1 for r in rows if r["selected"] and not r["is_correct"])
        total = attempt["total"]
        skipped = max(0, total - correct - wrong)

    quiz.finish_attempt(attempt["id"], total, correct, wrong, skipped)
    logger.info("QUIZ: [%s] finished attempt %s: %d/%d correct, %d wrong, %d skipped",
                user["email"], attempt["id"], correct, total, wrong, skipped)
    return jsonify({"success": True,
                    "redirect": url_for("practice_coding.quiz_review",
                                        attempt_id=attempt["id"])})
