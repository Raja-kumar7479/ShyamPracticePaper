"""Coding section: compile & test, submit."""
import logging

from flask import Blueprint, request, jsonify, abort

from .. import models
from ..auth_bridge import login_required, current_user, csrf_protect
from ..extensions import limiter
from ..services import code_executor

logger = logging.getLogger(__name__)
bp = Blueprint("coding_run", __name__, url_prefix="/api/coding-portal/coding")

MAX_CODE_BYTES = 200_000

VERDICT_LABEL = {
    "AC": "Accepted", "WA": "Wrong Answer", "TLE": "Time Limit Exceeded",
    "MLE": "Memory Limit Exceeded", "CE": "Compilation Error",
    "RE": "Runtime Error", "IE": "Internal Error",
}


def _guard(attempt_id, payload):
    """Shared validation: ownership, open attempt, question type, code size."""
    user = current_user()
    attempt = models.get_attempt(attempt_id, user["id"])
    if not attempt:
        abort(404)
    if attempt["status"] != "in_progress":
        return None, None, (jsonify({"error": "This attempt is already submitted"}), 409)

    question_id = payload.get("question_id")
    question = models.get_question(question_id) if question_id else None
    if not question:
        return None, None, (jsonify({"error": "Unknown question"}), 404)

    section = models.get_section(question["section_id"])
    if not section or section["test_id"] != attempt["test_id"]:
        return None, None, (jsonify({"error": "Question not part of this attempt"}), 403)
    if section["section_type"] != "coding":
        return None, None, (jsonify({"error": "Not a coding question"}), 400)

    code = payload.get("code") or ""
    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        return None, None, (jsonify({"error": "Submission is too large"}), 413)

    language = payload.get("language")
    if language not in code_executor.LANGUAGES:
        return None, None, (jsonify({"error": "Unsupported language"}), 400)

    allowed = [l.strip() for l in (question.get("allowed_languages") or "").split(",")]
    if allowed and language not in allowed:
        return None, None, (jsonify({"error": "Language not allowed here"}), 400)
    test_langs = models.test_allowed_languages(section["test_id"])
    if test_langs and language not in test_langs:
        return None, None, (jsonify({"error": "Language not allowed in this test"}), 400)

    return attempt, question, None


@bp.route("/<int:attempt_id>/run", methods=["POST"])
@login_required
@csrf_protect
@limiter.limit("40 per minute")
def run(attempt_id):
    payload = request.get_json(silent=True) or {}
    attempt, question, error = _guard(attempt_id, payload)
    if error:
        return error

    language = payload["language"]
    code = payload.get("code") or ""
    custom_input = payload.get("custom_input")

    # Custom input is a single ad-hoc run, not a graded attempt.
    if custom_input is not None:
        result = code_executor.run_custom_input(
            code, language, custom_input,
            time_limit=question["time_limit_sec"],
            memory_limit=question["memory_limit"],
        )
        return jsonify(result)

    # Visible testcases only -- running must never leak hidden cases.
    testcases = models.get_testcases(question["id"], include_hidden=False)
    if not testcases:
        return jsonify({"error": "No sample testcases for this question"}), 400

    result = code_executor.execute(
        code, language, testcases,
        time_limit=question["time_limit_sec"],
        memory_limit=question["memory_limit"],
        compare_mode=question.get("compare_mode") or "exact",
        float_tolerance=question.get("float_tolerance"),
    )
    return jsonify(_serialise(result, testcases, reveal=True))


@bp.route("/<int:attempt_id>/submit", methods=["POST"])
@login_required
@csrf_protect
@limiter.limit("20 per minute")
def submit(attempt_id):
    payload = request.get_json(silent=True) or {}
    attempt, question, error = _guard(attempt_id, payload)
    if error:
        return error

    language = payload["language"]
    code = payload.get("code") or ""

    testcases = models.get_testcases(question["id"], include_hidden=True)
    if not testcases:
        return jsonify({"error": "No testcases configured"}), 400

    result = code_executor.execute(
        code, language, testcases,
        time_limit=question["time_limit_sec"],
        memory_limit=question["memory_limit"],
        compare_mode=question.get("compare_mode") or "exact",
        float_tolerance=question.get("float_tolerance"),
    )

    verdict = result.verdict()
    score = (question["marks"] if verdict == "AC"
             else int(question["marks"] * result.passed / max(1, result.total)))

    models.save_answer(attempt_id, question["id"], language=language,
                       code=code, attempted=True)

    submission_id = models.store_submission(
        attempt_id, question["id"], language=language, code=code,
        verdict=verdict, passed=result.passed, total=result.total,
        score=score,
        execution_time=max((c.execution_time for c in result.cases), default=0),
        error_message=result.error or None,
    )
    models.store_submission_cases(submission_id, [
        {"testcase_id": tc["id"], "status": c.status,
         "execution_time": c.execution_time, "output": c.output, "error": c.error}
        for tc, c in zip(testcases, result.cases)
    ])

    body = _serialise(result, testcases, reveal=False)
    body["score"] = score
    return jsonify(body)


def _serialise(result, testcases, reveal):
    """
    Shape a RunResult for the client.

    reveal=False (submit) hides the input/expected of hidden testcases so a
    candidate cannot recover them from the response.
    """
    if not result.compiled:
        return {"compiled": False, "error": result.error, "verdict": "CE",
                "verdict_label": VERDICT_LABEL["CE"],
                "passed": 0, "total": len(testcases), "cases": []}

    cases = []
    for tc, c in zip(testcases, result.cases):
        hidden = bool(tc.get("is_hidden"))
        show = reveal or not hidden
        cases.append({
            "status": c.status,
            "is_hidden": hidden,
            "input": tc.get("input_text") if show else None,
            "expected": tc.get("expected_output") if show else None,
            "output": c.output if show else None,
            "error": c.error if show else ("Failed" if c.status != "PASS" else ""),
            "execution_time": c.execution_time,
        })

    verdict = result.verdict()
    return {
        "compiled": True,
        "verdict": verdict,
        "verdict_label": VERDICT_LABEL.get(verdict, verdict),
        "passed": result.passed,
        "total": result.total,
        "error": result.error,
        "cases": cases,
    }
