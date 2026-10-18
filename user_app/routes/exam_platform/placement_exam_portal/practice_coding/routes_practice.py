import logging
from datetime import datetime

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect,
                   render_template, request, session, url_for)

from extensions import limiter
from . import models
from .auth import csrf_protect, current_user, login_required
from .services import code_executor

logger = logging.getLogger(__name__)

bp = Blueprint("practice_coding", __name__, url_prefix="/practice-coding")

CODE_EXEMPT_ENDPOINTS = {"subscribe_webhook", "subscription_receipt", "premium",
                         "subscribe_order", "subscribe_verify"}

CODES_ARE_ORIGIN = {"premium"}


@bp.url_value_preprocessor
def _pull_course_codes(endpoint, values):
    if not values:
        return
    if (endpoint or "").rsplit(".", 1)[-1] in CODES_ARE_ORIGIN:
        return
    course_code = values.pop("course_code", None)
    unique_code = values.pop("unique_code", None)
    if course_code:
        session["pcp_course_code"] = course_code
    if unique_code:
        session["pcp_unique_code"] = unique_code


@bp.url_defaults
def _add_course_codes(endpoint, values):
    if not current_app.url_map.is_endpoint_expecting(endpoint, "course_code"):
        return
    course_code = session.get("pcp_course_code")
    unique_code = session.get("pcp_unique_code")
    if course_code and unique_code:
        values.setdefault("course_code", course_code)
        values.setdefault("unique_code", unique_code)


@bp.before_request
def _require_course_codes():
    if request.method == "OPTIONS":
        return None
    name = (request.endpoint or "").rsplit(".", 1)[-1]
    if name in CODE_EXEMPT_ENDPOINTS or "/api/" in request.path:
        return None
    if session.get("pcp_course_code") and session.get("pcp_unique_code"):
        return None
    logger.warning("PRACTICE CODING: no course context for %s", request.path)
    flash("Open coding practice from your course dashboard.", "test_error")
    return redirect(url_for("users.index"))

MAX_CODE_BYTES = 128 * 1024

VERDICT_LABEL = {
    "AC": "Accepted", "WA": "Wrong Answer", "TLE": "Time Limit Exceeded",
    "MLE": "Memory Limit Exceeded", "CE": "Compilation Error",
    "RE": "Runtime Error", "IE": "Internal Error",
}


def has_premium(email):
    return models.active_subscription(email, session.get("pcp_course_code")) is not None


def can_open(question, email):
    return not question["is_paid"] or has_premium(email)


def question_access(question, logged_in, premium, preview_ids):
    if question["is_paid"]:
        return "open" if premium else "premium"
    if logged_in:
        return "open"
    return "open" if question["id"] in preview_ids else "login"


def _course_ctx(course_code=None, unique_code=None):
    return (course_code or session.get("pcp_course_code"),
            unique_code or session.get("pcp_unique_code"))


@bp.route("/")
@bp.route("/<course_code>/<unique_code>")
def home():
    user = current_user()
    course_code, unique_code = _course_ctx()

    subject = request.args.get("subject") or None
    difficulty = request.args.get("difficulty") or None
    tier = request.args.get("tier")
    search = request.args.get("q") or None
    paid = True if tier == "paid" else (False if tier == "free" else None)

    status = request.args.get("status") or None
    sort = request.args.get("sort") or "default"

    user_id = user["id"] if user else None
    email = user["email"] if user else None
    premium = has_premium(email)
    preview_ids = set() if user else models.preview_question_ids(subject=subject)

    questions = models.list_questions(subject=subject, difficulty=difficulty,
                                      paid=paid, search=search,
                                      limit=models.PAGE_SIZE, offset=0,
                                      status=status, user_id=user_id, sort=sort)
    total_questions = models.count_questions(subject=subject, difficulty=difficulty,
                                             paid=paid, search=search,
                                             status=status, user_id=user_id)
    solved = models.solved_question_ids(user_id) if user_id else set()
    attempted = models.attempted_question_ids(user_id) if user_id else set()
    stats = (models.practice_stats(user_id) if user_id
             else {"by_difficulty": {}, "total": 0, "solved": 0})
    saved = models.bookmarked_question_ids(user_id) if user_id else set()
    company_map = models.companies_for_questions([q["id"] for q in questions])

    from .routes_billing import PLANS
    return render_template(
        "users/exam_platform/placement_exam_portal/practice_coding/practice_home.html",
        user=user, is_anon=user is None, preview_ids=preview_ids,
        course_code=course_code, unique_code=unique_code,
        login_url=url_for("users.user_login", next=request.full_path.rstrip("?")),
        questions=questions, solved=solved,
        subjects=models.subject_counts(), premium=premium,
        active_subject=subject, active_difficulty=difficulty,
        active_tier=tier, search=search or "",
        solved_count=len(solved),
        companies=models.list_companies(),
        company_map=company_map,
        daily=models.daily_challenge(),
        streak=models.solve_streak(user_id) if user_id else 0,
        leaderboard=models.monthly_leaderboard(),
        my_user_id=user_id,
        progress=models.subject_progress(user_id) if user_id else [],
        total_questions=total_questions,
        page_size=models.PAGE_SIZE,
        attempted=attempted, stats=stats,
        bookmarked=saved, bookmark_count=len(saved),
        active_status=status, active_sort=sort,
        sort_options=models.SORTS,
        monthly_price=PLANS["monthly"]["amount"] / 100.0,
        yearly_price=PLANS["yearly"]["amount"] / 100.0)


@bp.route("/api/questions")
def api_questions():
    user = current_user()
    user_id = user["id"] if user else None
    subject = request.args.get("subject") or None
    tier = request.args.get("tier")
    paid = True if tier == "paid" else (False if tier == "free" else None)
    try:
        offset = max(0, int(request.args.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0

    rows = models.list_questions(
        subject=subject,
        difficulty=request.args.get("difficulty") or None,
        paid=paid, search=request.args.get("q") or None,
        limit=models.PAGE_SIZE, offset=offset,
        status=request.args.get("status") or None,
        user_id=user_id, sort=request.args.get("sort") or "default")

    solved = models.solved_question_ids(user_id) if user_id else set()
    attempted = models.attempted_question_ids(user_id) if user_id else set()
    premium = has_premium(user["email"] if user else None)
    preview_ids = set() if user else models.preview_question_ids(subject=subject)
    company_map = models.companies_for_questions([r["id"] for r in rows])

    def _row(r):
        access = question_access(r, user is not None, premium, preview_ids)
        return {
            "id": r["id"],
            "title": r["title"],
            "difficulty": r["difficulty"],
            "subject": r["subject"],
            "is_paid": bool(r["is_paid"]),
            "acceptance": r["acceptance"],
            "solved": r["id"] in solved,
            "attempted": r["id"] in attempted,
            "locked": access != "open",
            "lock_reason": None if access == "open" else access,
            "companies": company_map.get(r["id"], []),
            "url": url_for("practice_coding.solve", slug=r["slug"]),
        }

    return jsonify({
        "questions": [_row(r) for r in rows],
        "is_anon": user is None,
        "next_offset": offset + len(rows),
        "has_more": len(rows) == models.PAGE_SIZE,
    })


@bp.route("/company/<slug>")
@bp.route("/company/<slug>/<course_code>/<unique_code>")
@login_required
def company(slug):
    user = current_user()
    row = models.get_company(slug)
    if not row:
        abort(404)
    questions = models.company_questions(row["id"])
    solved = models.solved_question_ids(user["id"])
    return render_template(
        "users/exam_platform/placement_exam_portal/practice_coding/company.html",
        user=user, company=row, questions=questions, solved=solved,
        premium=has_premium(user["email"]))


@bp.route("/daily")
@bp.route("/daily/<course_code>/<unique_code>")
@login_required
def daily():
    pick = models.daily_challenge()
    if not pick:
        return redirect(url_for("practice_coding.home"))
    return redirect(url_for("practice_coding.solve_by_id", question_id=pick["id"]))


@bp.route("/random")
@bp.route("/random/<course_code>/<unique_code>")
@login_required
def random_pick():
    user = current_user()
    qid = models.random_unsolved(user["id"], has_premium(user["email"]))
    if not qid:
        return redirect(url_for("practice_coding.home"))
    return redirect(url_for("practice_coding.solve_by_id", question_id=qid))


@bp.route("/problem/<int:question_id>")
@bp.route("/problem/<int:question_id>/<course_code>/<unique_code>")
@login_required
def solve_by_id(question_id):
    slug = models.slug_for(question_id)
    if not slug:
        abort(404)
    return redirect(url_for("practice_coding.solve", slug=slug), code=301)


@bp.route("/problem/<slug>")
@bp.route("/problem/<slug>/<course_code>/<unique_code>")
def solve(slug):
    user = current_user()
    question = models.get_question_by_slug(slug)
    if not question:
        abort(404)
    question_id = question["id"]
    course_code, unique_code = _course_ctx()

    email = user["email"] if user else None
    premium = has_premium(email)
    preview_ids = set() if user else models.preview_question_ids()
    access = question_access(question, user is not None, premium, preview_ids)
    locked = access != "open"
    lock_reason = None if not locked else access

    templates = {} if locked else models.get_templates(question_id)
    samples = [] if locked else models.get_testcases(question_id, include_hidden=False)
    history = ([] if locked or not user
               else models.recent_submissions(user["id"], question_id, limit=25))
    editorials = [] if locked else models.get_editorials(question_id)
    bookmarked = (False if locked or not user
                  else models.is_bookmarked(user["id"], question_id))

    if locked:
        for field in ("statement_html", "input_spec", "example_html",
                      "statement_image", "input_image", "example_image",
                      "output_spec"):
            question[field] = None

    languages = [l.strip() for l in (question.get("allowed_languages") or "").split(",")
                 if l.strip() in models.LANGUAGES] or models.LANGUAGES

    return render_template(
        "users/exam_platform/placement_exam_portal/practice_coding/solve.html",
        user=user, is_anon=user is None, question=question,
        locked=locked, lock_reason=lock_reason,
        course_code=course_code, unique_code=unique_code,
        login_url=url_for("users.user_login", next=request.path),
        templates=templates,
        samples=samples, history=history, languages=languages,
        editorials=editorials, bookmarked=bookmarked,
        premium=premium,
        verdict_labels=VERDICT_LABEL)


@bp.route("/bookmarks")
@bp.route("/bookmarks/<course_code>/<unique_code>")
@login_required
def bookmarks():
    user = current_user()
    rows = models.bookmarked_questions(user["id"])
    premium = has_premium(user["email"])
    for r in rows:
        if r["accepted"]:
            r["state"] = "solved"
        elif r["attempts"]:
            r["state"] = "attempted"
        else:
            r["state"] = "todo"
        r["locked"] = bool(r["is_paid"]) and not premium
    logger.info("PRACTICE BOOKMARKS: [%s] %d saved question(s)", user["email"], len(rows))
    return render_template(
        "users/exam_platform/placement_exam_portal/practice_coding/bookmarks.html",
        user=user, premium=premium, rows=rows,
        solved=sum(1 for r in rows if r["state"] == "solved"),
        attempted=sum(1 for r in rows if r["state"] == "attempted"),
        todo=sum(1 for r in rows if r["state"] == "todo"))


@bp.route("/api/bookmark/<int:question_id>", methods=["POST"])
@login_required
@csrf_protect
def api_bookmark(question_id):
    user = current_user()
    if not models.get_question(question_id):
        return jsonify({"error": "Unknown question"}), 404
    on = models.toggle_bookmark(user["id"], question_id)
    logger.info("PRACTICE BOOKMARK: [%s] question %s -> %s",
                user["email"], question_id, "on" if on else "off")
    return jsonify({"bookmarked": on})


def _guard(payload, allow_anon=False):
    user = current_user()
    question = models.get_question(payload.get("question_id") or 0)
    if not question:
        return None, None, (jsonify({"error": "Unknown question"}), 404)

    email = user["email"] if user else None
    if question["is_paid"]:
        if not has_premium(email):
            return None, None, (jsonify({"error": "premium_required",
                                         "message": "Subscribe to unlock this question."}), 402)
    elif user is None:
        if not allow_anon or question["id"] not in models.preview_question_ids():
            return None, None, (jsonify({"error": "login_required",
                                         "message": "Log in to continue."}), 401)

    code = payload.get("code") or ""
    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        return None, None, (jsonify({"error": "Submission is too large"}), 413)

    language = payload.get("language")
    if language not in code_executor.LANGUAGES:
        return None, None, (jsonify({"error": "Unsupported language"}), 400)
    allowed = [l.strip() for l in (question.get("allowed_languages") or "").split(",") if l.strip()]
    if allowed and language not in allowed:
        return None, None, (jsonify({"error": "Language not allowed here"}), 400)

    return user, question, None


@bp.route("/api/judge/health")
def judge_health():
    from ..coding_portal.services import judge_queue
    if judge_queue.enabled():
        stats = judge_queue.stats()
        stats["queue_ok"] = stats["waiting"] < stats["max_waiting"]
        stats["healthy"] = stats["queue_ok"] and stats["judge_workers"] > 0
        return jsonify(stats), (200 if stats["healthy"] else 503)
    from ..coding_portal.services.judge_gate import gate
    from ..coding_portal.services.docker_runner import docker_status
    stats = gate.stats()
    stats["mode"] = "local"
    docker = docker_status()
    stats["docker_running"] = docker["docker"]
    stats["judge_image_present"] = docker["image"]
    stats["queue_ok"] = stats["waiting"] < stats["max_waiting"]
    stats["healthy"] = stats["queue_ok"] and docker["docker"] and docker["image"]
    return jsonify(stats), (200 if stats["healthy"] else 503)


@bp.route("/api/run", methods=["POST"])
@csrf_protect
@limiter.limit("40 per minute")
def api_run(**kwargs):
    payload = request.get_json(silent=True) or {}
    user, question, error = _guard(payload, allow_anon=True)
    if error:
        return error

    language = payload["language"]
    code = payload.get("code") or ""
    custom_input = payload.get("custom_input")

    if custom_input is not None:
        return jsonify(code_executor.run_custom_input(
            code, language, custom_input,
            time_limit=question["time_limit_sec"],
            memory_limit=question["memory_limit"]))

    testcases = models.get_testcases(question["id"], include_hidden=False)
    if not testcases:
        return jsonify({"error": "No sample testcases for this question"}), 400

    result = code_executor.execute(code, language, testcases,
                                   time_limit=question["time_limit_sec"],
                                   memory_limit=question["memory_limit"],
                                   compare_mode=question.get("compare_mode") or "exact",
                                   float_tolerance=question.get("float_tolerance"))
    if result.compiled and result.error and not result.cases:
        return jsonify({"error": result.error, "busy": True}), 503
    return jsonify(_serialise(result, testcases, reveal=True))


@bp.route("/api/submit", methods=["POST"])
@login_required
@csrf_protect
@limiter.limit("20 per minute")
def api_submit(**kwargs):
    payload = request.get_json(silent=True) or {}
    user, question, error = _guard(payload)
    if error:
        return error

    language = payload["language"]
    code = payload.get("code") or ""
    testcases = models.get_testcases(question["id"], include_hidden=True)
    if not testcases:
        return jsonify({"error": "No testcases configured"}), 400

    result = code_executor.execute(code, language, testcases,
                                   time_limit=question["time_limit_sec"],
                                   memory_limit=question["memory_limit"],
                                   compare_mode=question.get("compare_mode") or "exact",
                                   float_tolerance=question.get("float_tolerance"))
    if result.compiled and result.error and not result.cases:
        return jsonify({"error": result.error, "busy": True}), 503
    verdict = result.verdict() if result.compiled else "CE"
    exec_time = max((c.execution_time for c in result.cases), default=0)
    sub_id = models.record_submission(user["id"], question["id"], language, code, {
        "verdict": verdict, "passed": result.passed, "total": result.total,
        "execution_time": exec_time,
        "error_message": result.error or None,
    })
    logger.info("PRACTICE: [%s] submit q=%s verdict=%s (%s/%s)",
                user["email"], question["id"], verdict, result.passed, result.total)

    body = _serialise(result, testcases, reveal=False)
    body["solved"] = verdict == "AC"
    body["submission"] = {
        "id": sub_id,
        "verdict": verdict,
        "verdict_label": VERDICT_LABEL.get(verdict, verdict),
        "language": language,
        "passed": result.passed,
        "total": result.total,
        "runtime_ms": int(round(exec_time * 1000)) if exec_time else None,
        "when": datetime.now().strftime("%d %b, %H:%M"),
        "code": code,
        "error_message": result.error or None,
    }
    return jsonify(body)


def _serialise(result, testcases, reveal):
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
    return {"compiled": True, "verdict": verdict,
            "verdict_label": VERDICT_LABEL.get(verdict, verdict),
            "passed": result.passed, "total": result.total,
            "error": result.error, "cases": cases}
