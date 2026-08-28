"""SQL section: Run Query (preview) and Check Query (grade)."""
import logging

from flask import Blueprint, request, jsonify, abort

from .. import models
from ..auth_bridge import login_required, current_user, csrf_protect
from ..extensions import limiter
from ..services import sql_executor
from ..services.sql_executor import SqlError

logger = logging.getLogger(__name__)
bp = Blueprint("coding_sql", __name__, url_prefix="/api/coding-portal/sql")

MAX_QUERY_BYTES = 20_000


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
    if section["section_type"] != "sql":
        return None, None, (jsonify({"error": "Not a SQL question"}), 400)

    query = payload.get("query") or ""
    if len(query.encode("utf-8")) > MAX_QUERY_BYTES:
        return None, None, (jsonify({"error": "Query is too long"}), 413)

    return attempt, question, None


@bp.route("/<int:attempt_id>/run", methods=["POST"])
@login_required
@csrf_protect
@limiter.limit("60 per minute")
def run_query(attempt_id):
    payload = request.get_json(silent=True) or {}
    attempt, question, error = _guard(attempt_id, payload)
    if error:
        return error

    try:
        result = sql_executor.run_query(
            question["id"], question["sandbox_schema_sql"], payload.get("query"))
    except SqlError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"result": result})


@bp.route("/<int:attempt_id>/check", methods=["POST"])
@login_required
@csrf_protect
@limiter.limit("30 per minute")
def check_query(attempt_id):
    payload = request.get_json(silent=True) or {}
    attempt, question, error = _guard(attempt_id, payload)
    if error:
        return error

    if not question.get("solution_query"):
        return jsonify({"error": "No reference solution configured"}), 400

    query = payload.get("query") or ""
    try:
        outcome = sql_executor.check_query(
            question["id"], question["sandbox_schema_sql"], query,
            question["solution_query"],
            ordered=bool(question.get("ordered_comparison")),
        )
    except SqlError as e:
        return jsonify({"error": str(e)}), 400

    score = question["marks"] if outcome["correct"] else 0
    verdict = "AC" if outcome["correct"] else "WA"

    models.save_answer(attempt_id, question["id"], code=query, attempted=True)
    models.store_submission(
        attempt_id, question["id"], language="sql", code=query,
        verdict=verdict, passed=1 if outcome["correct"] else 0, total=1,
        score=score, execution_time=0,
        error_message=outcome["reason"] or None,
    )

    return jsonify({
        "correct": outcome["correct"],
        "reason": outcome["reason"],
        "result": outcome["result"],
        "score": score,
    })
