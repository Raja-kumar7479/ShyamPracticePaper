import logging

from flask import Blueprint, request, jsonify, abort

from .. import models
from ..auth_bridge import login_required, current_user, csrf_protect
from ..extensions import limiter
from ..services import web_evaluator

logger = logging.getLogger(__name__)
bp = Blueprint("coding_web", __name__, url_prefix="/api/coding-portal/web")

MAX_SOURCE_BYTES = 200_000


def _guard(attempt_id, payload):
    user = current_user()
    attempt = models.get_attempt(attempt_id, user["id"])
    if not attempt:
        abort(404)
    if attempt["status"] != "in_progress":
        return None, None, (jsonify({"error": "This attempt is already submitted"}), 409)

    question = models.get_question(payload.get("question_id") or 0)
    if not question:
        return None, None, (jsonify({"error": "Unknown question"}), 404)

    section = models.get_section(question["section_id"])
    if not section or section["test_id"] != attempt["test_id"]:
        return None, None, (jsonify({"error": "Question not part of this attempt"}), 403)
    if section["section_type"] != "web":
        return None, None, (jsonify({"error": "Not a web question"}), 400)

    total = sum(len((payload.get(k) or "").encode("utf-8"))
                for k in ("code_html", "code_css", "code_js"))
    if total > MAX_SOURCE_BYTES:
        return None, None, (jsonify({"error": "Submission is too large"}), 413)

    return attempt, question, None


def _evaluate(question, payload, reveal_hidden):
    assertions = models.get_web_assertions(question["id"])
    visible = assertions if reveal_hidden else [
        a for a in assertions if not a["is_hidden"]
    ]
    target = assertions if reveal_hidden else visible

    results, passed, total = web_evaluator.evaluate(
        payload.get("code_html"), payload.get("code_css"),
        payload.get("code_js"), target,
    )
    return results, passed, total


@bp.route("/<int:attempt_id>/run", methods=["POST"])
@login_required
@csrf_protect
@limiter.limit("60 per minute")
def run_checks(attempt_id):
    payload = request.get_json(silent=True) or {}
    attempt, question, error = _guard(attempt_id, payload)
    if error:
        return error

    results, passed, total = _evaluate(question, payload, reveal_hidden=False)
    return jsonify({"results": results, "passed": passed, "total": total})


@bp.route("/<int:attempt_id>/submit", methods=["POST"])
@login_required
@csrf_protect
@limiter.limit("20 per minute")
def submit(attempt_id):
    payload = request.get_json(silent=True) or {}
    attempt, question, error = _guard(attempt_id, payload)
    if error:
        return error

    results, passed, total = _evaluate(question, payload, reveal_hidden=True)
    score = question["marks"] if passed == total and total else \
        int(question["marks"] * passed / max(1, total))
    verdict = "AC" if total and passed == total else "WA"

    models.save_answer(
        attempt_id, question["id"],
        code_html=payload.get("code_html"),
        code_css=payload.get("code_css"),
        code_js=payload.get("code_js"),
        attempted=True,
    )
    submission_id = models.store_submission(
        attempt_id, question["id"], language="web",
        code=payload.get("code_html"),
        verdict=verdict, passed=passed, total=total, score=score,
        execution_time=0, error_message=None,
    )
    models.store_submission_cases(submission_id, [
        {"testcase_id": None,
         "status": "PASS" if r["status"] == "PASS" else "FAIL",
         "execution_time": 0, "output": r["message"], "error": r["detail"]}
        for r in results
    ])

    shaped = [
        {"message": r["message"] if not r["is_hidden"] else "Hidden check",
         "status": r["status"],
         "detail": r["detail"] if not r["is_hidden"] else ""}
        for r in results
    ]
    return jsonify({"results": shaped, "passed": passed,
                    "total": total, "score": score})
