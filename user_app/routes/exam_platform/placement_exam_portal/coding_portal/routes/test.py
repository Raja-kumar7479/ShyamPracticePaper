import logging
import re
import time

from flask import (Blueprint, render_template, request, redirect, url_for,
                   jsonify, abort, flash, session)

from .. import models
from ..auth_bridge import login_required, current_user, csrf_protect
from ..extensions import limiter
from ..db import query_all, execute
from ..round_sync import sync_round_status
from .. import result_stats
from routes.exam_platform.active_test_lock import active_test_redirect, blocked_message

logger = logging.getLogger(__name__)
bp = Blueprint("coding_test", __name__, url_prefix="/coding")

SECTION_TEMPLATE = {
    "coding": "users/exam_platform/placement_exam_portal/coding_portal/test/coding.html",
    "sql": "users/exam_platform/placement_exam_portal/coding_portal/test/sql.html",
    "web": "users/exam_platform/placement_exam_portal/coding_portal/test/web.html",
}

SECTION_ASSETS = {
    "coding": {
        "css": ["css/users/exam_platform/placement_exam_portal/coding_portal/editor.css"],
        "js": ["js/users/exam_platform/placement_exam_portal/coding_portal/coding.js"],
    },
    "sql": {
        "css": ["css/users/exam_platform/placement_exam_portal/coding_portal/editor.css", "css/users/exam_platform/placement_exam_portal/coding_portal/sql.css"],
        "js": ["js/users/exam_platform/placement_exam_portal/coding_portal/schema-viewer.js", "js/users/exam_platform/placement_exam_portal/coding_portal/sql.js"],
    },
    "web": {
        "css": ["css/users/exam_platform/placement_exam_portal/coding_portal/editor.css", "css/users/exam_platform/placement_exam_portal/coding_portal/web.css"],
        "js": ["js/users/exam_platform/placement_exam_portal/coding_portal/web.js"],
    },
}


_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _capture_codes(course_code, unique_code):
    if course_code and _CODE_RE.match(course_code):
        session["coding_course_code"] = course_code
    if unique_code and _CODE_RE.match(unique_code):
        session["coding_unique_code"] = unique_code


def _after_finish_url(attempt):
    flow = session.get("tcs_flow") or {}
    if flow.get("exam_id") and flow.get("coding_test_id") == attempt.get("test_id"):
        return url_for("tcs.after_coding", exam_id=flow["exam_id"])
    return url_for("coding_test.dashboard", **_code_kwargs())


def _code_kwargs():
    course = session.get("coding_course_code")
    code = session.get("coding_unique_code")
    if course and code:
        return {"course_code": course, "unique_code": code}
    return {}


@bp.route("/")
@bp.route("/<course_code>/<unique_code>")
@login_required
def dashboard(course_code=None, unique_code=None):
    _standalone_entry()
    user = current_user()
    from flask import session as _session
    _capture_codes(course_code, unique_code)

    section_id = request.args.get("section_id") or _session.get("coding_section_id")
    if section_id:
        _session["coding_section_id"] = section_id
    course_code = course_code or _session.get("coding_course_code")
    tests = models.list_published_tests(course_code=course_code, test_id=section_id)
    for t in tests:
        t["sections"] = models.get_sections(t["id"])
        attempt = query_all(
            "SELECT id, status, submitted_at FROM cp_attempts WHERE test_id = %s AND user_id = %s "
            "ORDER BY id DESC LIMIT 1",
            (t["id"], user["id"]),
        )
        t["attempt_status"] = attempt[0]["status"] if attempt else None
        t["attempt_id"] = attempt[0]["id"] if attempt else None
        t["submitted_at"] = attempt[0].get("submitted_at") if attempt else None
    from routes.exam_platform.subscription_access import has_platform_subscription, premium_url
    codes = _code_kwargs()
    subscribed = has_platform_subscription(user.get("email"), course_code) if user else False
    items, completed = [], []
    for t in tests:
        premium = (t.get("access_label") or "inherit") == "paid"
        locked = premium and not subscribed
        if t["attempt_status"] == "submitted":
            ts = t.get("submitted_at")
            completed.append({
                "title": t["title"], "subtitle": t.get("description"),
                "submitted_at": ts.strftime("%d %b %Y, %I:%M %p") if hasattr(ts, "strftime") else None,
                "score": None, "percentage": None, "result_label": "View Result",
                "result_url": url_for("coding_test.result", attempt_id=t["attempt_id"], **codes)})
            continue
        items.append({
            "title": t["title"], "subtitle": t.get("description") or "Coding, MySQL and web sections.",
            "status": "unperformed" if t["attempt_status"] in ("in_progress", "expired") else "pending",
            "access": "premium" if premium else "free", "locked": locked,
            "unlock_url": premium_url(codes.get("course_code"), codes.get("unique_code"), t.get("test_id")),
            "unlock_label": "Unlock Premium", "is_new": False,
            "tags": sorted({(s.get("section_type") or "").upper() for s in t["sections"] if s.get("section_type")}),
            "meta": [{"icon": "far fa-clock", "text": f"{t.get('total_duration_min')} Min"},
                     {"icon": "fas fa-layer-group", "text": f"{len(t['sections'])} Section{'' if len(t['sections']) == 1 else 's'}"},
                     {"icon": "far fa-question-circle", "text": f"{sum(int(s.get('question_count') or 0) for s in t['sections'])} Qs"}],
            "action_url": url_for("coding_test.lobby", slug=t["slug"], **codes),
            "action_label": "Start Test", "resume_label": "Resume Test", "launch": "same",
        })
    back_url = url_for("users.view_course_dashboard", **codes) if codes else url_for("users.index")
    return render_template("users/exam_platform/test_list.html",
                           portal_label="Coding Tests", portal_icon="fa-laptop-code",
                           intro="Programming rounds graded by test cases. Each test opens in a full-screen code editor.",
                           tests=items, completed=completed, paid_blocks=[],
                           username=(user or {}).get("username"), email=(user or {}).get("email"),
                           course_code=codes.get("course_code") or course_code or "", unique_code=codes.get("unique_code") or "",
                           dashboard_type="free", back_url=back_url,
                           shop_url=url_for("users.course_shop", **codes) if codes else url_for("users.index"),
                           extra_links=[{"label": "Coding Practice", "icon": "fa-code", "url": url_for("practice_coding.home")}])


def _intro_context(slug):
    test = models.get_test_by_slug(slug)
    if not test or not test["is_published"]:
        abort(404)

    sections = models.get_sections(test["id"])
    question_count = sum(int(s.get("question_count") or 0) for s in sections)
    return {
        "user": current_user(),
        "test": test,
        "sections": sections,
        "question_count": question_count,
        "code_kwargs": _code_kwargs(),
    }


@bp.route("/test/<slug>/system-check")
@bp.route("/test/<slug>/system-check/<course_code>/<unique_code>")
@login_required
def system_check(slug, course_code=None, unique_code=None):
    _standalone_entry()
    _capture_codes(course_code, unique_code)
    user = current_user()
    test = models.get_test_by_slug(slug)
    if test:
        running = active_test_redirect(user.get("email"), ignore_test_key=test.get("test_key"))
        if running:
            flash(blocked_message(), "coding_error")
            return redirect(url_for("coding_test.dashboard", **_code_kwargs()))
        blocked = _completed_block(test, user)
        if blocked:
            return blocked
        if _premium_block(test, user.get("email")):
            flash("This is a premium assessment. Subscribe to unlock all tests.", "coding_error")
            return redirect(_premium_page(test))
    return redirect(url_for("coding_test.lobby", slug=slug, **_code_kwargs()))


def _latest_attempt(test_id, user_id):
    rows = query_all(
        "SELECT id, status FROM cp_attempts WHERE test_id = %s AND user_id = %s "
        "ORDER BY id DESC LIMIT 1",
        (test_id, user_id),
    )
    return rows[0] if rows else None


def _render_already_submitted(test, attempt_id):
    return render_template(
        "users/exam_platform/placement_exam_portal/coding_portal/test/already_submitted.html",
        user=current_user(),
        test=test,
        result_url=url_for("coding_test.result", attempt_id=attempt_id, **_code_kwargs()),
        dashboard_url=url_for("coding_test.dashboard", **_code_kwargs()),
    ), 403


def _completed_block(test, user):
    attempt = _latest_attempt(test["id"], user["id"])
    if not attempt:
        return None

    if attempt["status"] == "submitted":
        logger.warning("CODING RE-ATTEMPT BLOCKED: [%s] test %s already submitted",
                       user.get("email"), test.get("slug"))
        return _render_already_submitted(test, attempt["id"])

    if attempt["status"] == "expired":
        execute("UPDATE cp_attempts SET status = 'in_progress', submitted_at = NULL "
                "WHERE id = %s AND status = 'expired'", (attempt["id"],))
        logger.info("CODING REOPEN: [%s] test %s reopened after leaving window",
                    user.get("email"), test.get("slug"))

    return None


def _premium_page(test=None):
    from routes.exam_platform.subscription_access import premium_url
    codes = _code_kwargs()
    return premium_url(codes.get("course_code"), codes.get("unique_code"),
                       (test or {}).get("test_id"))


def _premium_block(test, email):
    from routes.exam_platform.subscription_access import has_platform_subscription
    if (test.get("access_label") or "inherit") != "paid":
        return False
    if has_platform_subscription(email, test.get("code")):
        return False
    logger.warning("CODING PREMIUM BLOCKED: [%s] test %s without subscription", email, test.get("slug"))
    return True

@bp.route("/test/<slug>/lobby")
@bp.route("/test/<slug>/lobby/<course_code>/<unique_code>")
@login_required
def lobby(slug, course_code=None, unique_code=None):
    _standalone_entry()
    _capture_codes(course_code, unique_code)
    user = current_user()
    _t = models.get_test_by_slug(slug)
    if _t:
        blocked = _completed_block(_t, user)
        if blocked:
            return blocked
        if _premium_block(_t, user.get("email")):
            flash("This is a premium assessment. Subscribe to unlock all tests.", "coding_error")
            return redirect(_premium_page(_t))
    context = _intro_context(slug)
    if not context["sections"]:
        flash("This assessment has no sections yet. Please try again later.", "coding_error")
        return redirect(url_for("coding_test.dashboard"))
    return render_template(
        "users/exam_platform/placement_exam_portal/coding_portal/exam_lobby.html",
        **context)


@bp.route("/test/<slug>/start")
@bp.route("/test/<slug>/start/<course_code>/<unique_code>")
@login_required
def start(slug, course_code=None, unique_code=None):
    _capture_codes(course_code, unique_code)
    embedded_start = bool(session.pop("tcs_embedded_start", False))
    if not embedded_start:
        _standalone_entry()
    user = current_user()
    test = models.get_test_by_slug(slug)
    if not test or not test["is_published"]:
        abort(404)

    ignore = [test.get("test_key")]
    flow = session.get("tcs_flow") or {}
    if flow.get("coding_test_id") == test["id"] and flow.get("aptitude_test_key"):
        ignore.append(flow["aptitude_test_key"])
    running = active_test_redirect(user.get("email"), ignore_test_key=ignore)
    if running:
        flash(blocked_message(), "coding_error")
        return redirect(url_for("coding_test.dashboard", **_code_kwargs()))

    blocked = _completed_block(test, user)
    if blocked:
        return blocked
    if _premium_block(test, user.get("email")):
        flash("This is a premium assessment. Subscribe to unlock all tests.", "coding_error")
        return redirect(_premium_page(test))

    attempt = models.get_or_create_attempt(test["id"], user["id"])
    if attempt["status"] == "submitted":
        return _render_already_submitted(test, attempt["id"])

    if not embedded_start:
        cleared = models.reset_attempt(attempt["id"])
        if cleared:
            logger.info("CODING FRESH SITTING: [%s] test %s restarted, %s saved item(s) cleared",
                        user.get("email"), test.get("slug"), cleared)
    session[SITTING_KEY] = {"attempt": attempt["id"], "fresh": True}
    session.modified = True

    sync_round_status(test["id"], user.get("email"), "started")

    sections = models.get_sections(test["id"])
    if not sections:
        flash("This assessment has no sections yet. Please try again later.", "coding_error")
        logger.warning("CODING: test %s has no sections; start blocked", test["id"])
        return redirect(url_for("coding_test.dashboard"))
    return redirect(url_for("coding_test.section_page", attempt_id=attempt["id"],
                            section_id=sections[0]["id"]))


SITTING_KEY = "cp_sitting"


def _left_sitting(attempt_id, user, why):
    models.pause_clock(attempt_id)
    session.pop(SITTING_KEY, None)
    session.modified = True
    logger.warning("CODING LEFT WINDOW: [%s] attempt %s (%s) - the next start is a new sitting",
                   user.get("email"), attempt_id, why)
    target = url_for("coding_test.terminated", attempt_id=attempt_id)
    if _is_ajax():
        return jsonify({"redirect": target})
    return redirect(target)


def _is_embedded(attempt):
    if not session.get("tcs_embedded"):
        return False
    flow = session.get("tcs_flow") or {}
    return flow.get("coding_test_id") == attempt.get("test_id")


def _standalone_entry():
    session.pop("tcs_embedded", None)
    session.pop("tcs_embedded_start", None)


def _load_attempt(attempt_id):
    user = current_user()
    attempt = models.get_attempt(attempt_id, user["id"])
    if not attempt:
        abort(404)
    if attempt["status"] != "in_progress":
        return attempt, user, True
    return attempt, user, False


def _remaining_seconds(attempt, test):
    deadline = session.get("tcs_window_deadline")
    if _is_embedded(attempt) and deadline:
        return max(0, int(deadline) - int(time.time()))
    used = models.active_seconds(attempt["id"])
    return max(0, test["total_duration_min"] * 60 - used)


@bp.route("/attempt/<int:attempt_id>/summary")
@login_required
def finish_summary(attempt_id):
    attempt, user, done = _load_attempt(attempt_id)
    if done:
        return jsonify({"redirect": _after_finish_url(attempt)})
    test = models.get_test(attempt["test_id"])
    rows = query_all(
        """
        SELECT s.id, s.title, s.section_type,
               COUNT(q.id) AS total,
               COALESCE(SUM(CASE WHEN EXISTS(
                   SELECT 1 FROM cp_submissions sub
                    WHERE sub.attempt_id = %s AND sub.question_id = q.id) THEN 1 ELSE 0 END), 0)
                   AS attempted
          FROM cp_sections s
          LEFT JOIN cp_questions q ON q.section_id = s.id
         WHERE s.test_id = %s
         GROUP BY s.id, s.title, s.section_type, s.position
         ORDER BY s.position, s.id
        """,
        (attempt_id, test["id"]),
    )
    sections = [{"title": r["title"], "type": r["section_type"],
                 "total": int(r["total"] or 0),
                 "attempted": int(r["attempted"] or 0)} for r in rows]
    return jsonify({
        "remainingSeconds": _remaining_seconds(attempt, test),
        "sections": sections,
        "total": sum(s["total"] for s in sections),
        "attempted": sum(s["attempted"] for s in sections),
    })


@bp.route("/attempt/<int:attempt_id>/section/<int:section_id>")
@login_required
def section_page(attempt_id, section_id):
    attempt, user, done = _load_attempt(attempt_id)
    if done:
        return redirect(url_for("coding_test.dashboard", **_code_kwargs()))

    questions = models.get_questions(section_id)
    if not questions:
        abort(404)
    return redirect(url_for("coding_test.question_page", attempt_id=attempt_id,
                            question_id=questions[0]["id"]))


def _is_ajax():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _section_config(section, question, cfg_extra):
    base = {"questionId": question["id"]}
    if section["section_type"] == "coding":
        base.update({
            "languages": question["languages"],
            "templates": question["templates"],
            "savedCode": cfg_extra["answer"]["code"] if cfg_extra["answer"] else None,
            "savedLanguage": cfg_extra["answer"]["language"] if cfg_extra["answer"] else None,
            "runUrl": url_for("coding_run.run", attempt_id=cfg_extra["attempt_id"]),
            "submitUrl": url_for("coding_run.submit", attempt_id=cfg_extra["attempt_id"]),
            "saveUrl": url_for("coding_test.save_answer_api", attempt_id=cfg_extra["attempt_id"]),
        })
    elif section["section_type"] == "sql":
        base.update({
            "savedCode": cfg_extra["answer"]["code"] if cfg_extra["answer"] else None,
            "runUrl": url_for("coding_sql.run_query", attempt_id=cfg_extra["attempt_id"]),
            "checkUrl": url_for("coding_sql.check_query", attempt_id=cfg_extra["attempt_id"]),
            "saveUrl": url_for("coding_test.save_answer_api", attempt_id=cfg_extra["attempt_id"]),
        })
    elif section["section_type"] == "web":
        answer = cfg_extra["answer"]
        base.update({
            "starterHtml": question.get("starter_html") or "",
            "starterCss": question.get("starter_css") or "",
            "starterJs": question.get("starter_js") or "",
            "savedHtml": answer["code_html"] if answer else None,
            "savedCss": answer["code_css"] if answer else None,
            "savedJs": answer["code_js"] if answer else None,
            "runUrl": url_for("coding_web.run_checks", attempt_id=cfg_extra["attempt_id"]),
            "submitUrl": url_for("coding_web.submit", attempt_id=cfg_extra["attempt_id"]),
            "saveUrl": url_for("coding_test.save_answer_api", attempt_id=cfg_extra["attempt_id"]),
        })
    return base


@bp.route("/attempt/<int:attempt_id>/question/<int:question_id>")
@login_required
def question_page(attempt_id, question_id):
    attempt, user, done = _load_attempt(attempt_id)
    if done:
        if _is_ajax():
            return jsonify({"redirect": _after_finish_url(attempt)})
        return redirect(_after_finish_url(attempt))

    question = models.get_question_full(question_id)
    if not question:
        abort(404)

    section = models.get_section(question["section_id"])
    test = models.get_test(attempt["test_id"])
    if not section or section["test_id"] != test["id"]:
        abort(404)

    sitting = session.get(SITTING_KEY) or {}
    if sitting.get("attempt") != attempt_id:
        return _left_sitting(attempt_id, user, "no sitting in this session")
    fresh_sitting = bool(sitting.get("fresh"))
    if not fresh_sitting and not _is_ajax():
        return _left_sitting(attempt_id, user, "page refreshed")
    if fresh_sitting:
        session[SITTING_KEY] = {"attempt": attempt_id, "fresh": False}
        session.modified = True

    models.mark_resumed(attempt_id)
    remaining = _remaining_seconds(attempt, test)
    if remaining <= 0:
        finalize_attempt(attempt, user.get("email"))
        if _is_ajax():
            return jsonify({"redirect": _after_finish_url(attempt)})
        return redirect(_after_finish_url(attempt))

    questions = models.get_questions(section["id"])
    sections = models.get_sections(test["id"])
    index = next((i for i, q in enumerate(questions)
                  if q["id"] == question_id), 0)
    sec_index = next((i for i, s in enumerate(sections)
                      if s["id"] == section["id"]), 0)

    template = SECTION_TEMPLATE.get(section["section_type"])
    if not template:
        abort(500)

    answer = models.get_answer(attempt_id, question_id)
    attempted_map = models.get_attempted_map(attempt_id, section["id"])
    embedded = _is_embedded(attempt)
    embedded_nav = _embedded_nav(attempt_id, sections, section, questions) if embedded else None
    exam_config = {
        "attemptId": attempt_id,
        "questionId": question_id,
        "sectionType": section["section_type"],
        "freshSitting": fresh_sitting,
        "remainingSeconds": remaining,
        "pauseUrl": url_for("coding_test.pause", attempt_id=attempt_id),
        "resumeUrl": url_for("coding_test.resume_clock", attempt_id=attempt_id),
        "pingUrl": url_for("coding_test.ping", attempt_id=attempt_id),
        "summaryUrl": url_for("coding_test.finish_summary", attempt_id=attempt_id),
        "section": _section_config(section, question,
                                   {"answer": answer, "attempt_id": attempt_id}),
    }

    ajax = _is_ajax()
    html = render_template(
        template,
        user=user, test=test, attempt=attempt, section=section,
        question=question, questions=questions, sections=sections,
        question_index=index + 1, sec_index=sec_index,
        prev_question=questions[index - 1] if index > 0 else None,
        next_question=questions[index + 1] if index + 1 < len(questions) else None,
        prev_section=sections[sec_index - 1] if sec_index > 0 else None,
        next_section=sections[sec_index + 1] if sec_index + 1 < len(sections) else None,
        answer=answer,
        embedded=embedded,
        embedded_nav=embedded_nav,
        attempted_map=attempted_map,
        remaining_seconds=remaining,
        away_seconds=AWAY_GRACE_SECONDS,
        exam_config=exam_config,
        layout=("users/exam_platform/placement_exam_portal/coding_portal/test/fragment_base.html" if ajax else "users/exam_platform/placement_exam_portal/coding_portal/base.html"),
    )
    if not ajax:
        return html

    assets = SECTION_ASSETS.get(section["section_type"], {"css": [], "js": []})
    return jsonify({
        "html": html,
        "title": f'{question["title"]} — {test["title"]}',
        "url": url_for("coding_test.question_page", attempt_id=attempt_id,
                       question_id=question_id),
        "css": [url_for("static", filename=p) for p in assets["css"]],
        "js": [url_for("static", filename=p) for p in assets["js"]],
        **exam_config,
    })


@bp.route("/attempt/<int:attempt_id>/save", methods=["POST"])
@limiter.exempt
@login_required
@csrf_protect
def save_answer_api(attempt_id):
    attempt, user, done = _load_attempt(attempt_id)
    if done:
        return jsonify({"error": "This attempt is already submitted"}), 409

    data = request.get_json(silent=True) or {}
    question_id = data.get("question_id")
    if not question_id:
        return jsonify({"error": "question_id is required"}), 400

    if not _question_in_attempt(question_id, attempt):
        return jsonify({"error": "Question not part of this attempt"}), 403

    models.save_answer(
        attempt_id, question_id,
        language=data.get("language"),
        code=data.get("code"),
        code_html=data.get("code_html"),
        code_css=data.get("code_css"),
        code_js=data.get("code_js"),
        attempted=data.get("attempted"),
    )
    return jsonify({"saved": True})


def _question_in_attempt(question_id, attempt):
    question = models.get_question(question_id)
    if not question:
        return False
    section = models.get_section(question["section_id"])
    return bool(section and section["test_id"] == attempt["test_id"])


def _judge_unavailable(result):
    return bool(result.compiled and result.error and not result.cases)


GRADED, BUSY, SKIP, BROKEN = 'graded', 'busy', 'skip', 'broken'
GRADER_SKIP_SECONDS = 600
_grader_skip = {}


def _grade_sql_answer(attempt_id, ans, question, email):
    from ..services import sql_executor
    if not question.get("solution_query") or not question.get("sandbox_schema_sql"):
        return SKIP
    try:
        outcome = sql_executor.check_query(
            question["id"], question["sandbox_schema_sql"], ans["code"],
            question["solution_query"],
            ordered=bool(question.get("ordered_comparison")),
        )
    except sql_executor.SqlQuestionBroken as exc:
        logger.warning("CODING FINISH-GRADE LEFT UNGRADED: [%s] attempt %s q%s (%s)",
                       email, attempt_id, question["id"], exc)
        return BROKEN
    except sql_executor.SqlUnavailable as exc:
        logger.warning("CODING FINISH-GRADE DEFERRED: [%s] attempt %s q%s (%s)",
                       email, attempt_id, question["id"], exc)
        return BUSY
    except sql_executor.SqlError as exc:
        outcome = {"correct": False, "reason": str(exc)}
    correct = bool(outcome["correct"])
    models.store_submission(
        attempt_id, question["id"], language="sql", code=ans["code"],
        verdict="AC" if correct else "WA", passed=1 if correct else 0, total=1,
        score=question["marks"] if correct else 0, execution_time=0,
        error_message=outcome.get("reason") or None,
    )
    logger.info("CODING FINISH-GRADE: [%s] attempt %s q%s -> %s (sql)",
                email, attempt_id, question["id"], "AC" if correct else "WA")
    return GRADED


def _grade_answer(attempt_id, ans, email):
    from ..services import code_executor
    question = models.get_question(ans["question_id"])
    if not question:
        return SKIP
    if ans.get("section_type") == "sql":
        return _grade_sql_answer(attempt_id, ans, question, email)
    if ans["language"] not in code_executor.LANGUAGES:
        return SKIP
    testcases = models.get_testcases(question["id"], include_hidden=True)
    if not testcases:
        return SKIP
    result = code_executor.execute(
        ans["code"], ans["language"], testcases,
        time_limit=question["time_limit_sec"],
        memory_limit=question["memory_limit"],
        compare_mode=question.get("compare_mode") or "exact",
        float_tolerance=question.get("float_tolerance"),
    )
    if _judge_unavailable(result):
        logger.warning("CODING FINISH-GRADE DEFERRED: [%s] attempt %s q%s (%s)",
                       email, attempt_id, question["id"], result.error)
        return BUSY
    verdict = result.verdict()
    score = (question["marks"] if verdict == "AC"
             else int(question["marks"] * result.passed / max(1, result.total)))
    submission_id = models.store_submission(
        attempt_id, question["id"], language=ans["language"],
        code=ans["code"], verdict=verdict, passed=result.passed,
        total=result.total, score=score,
        execution_time=max((c.execution_time for c in result.cases), default=0),
        error_message=result.error or None,
    )
    models.store_submission_cases(submission_id, [
        {"testcase_id": tc["id"], "status": c.status,
         "execution_time": c.execution_time, "output": c.output,
         "error": c.error}
        for tc, c in zip(testcases, result.cases)
    ])
    logger.info("CODING FINISH-GRADE: [%s] attempt %s q%s -> %s (%s/%s)",
                email, attempt_id, question["id"], verdict,
                result.passed, result.total)
    return GRADED


def _grade_unsubmitted(attempt_id, email):
    deferred = 0
    for ans in models.unsubmitted_saved_answers(attempt_id):
        try:
            if _grade_answer(attempt_id, ans, email) in (BUSY, BROKEN):
                deferred += 1
        except Exception:
            deferred += 1
            logger.exception("CODING FINISH-GRADE FAILED: attempt %s q%s",
                             attempt_id, ans.get("question_id"))
    return deferred


PENDING_GRADER_LOCK = 'spp_pending_grader'


def run_pending_grader(batch=20):
    from routes.db_pool import get_connection
    conn = get_connection()
    cur = conn.cursor()
    graded = 0
    try:
        cur.execute("SELECT GET_LOCK(%s, 0)", (PENDING_GRADER_LOCK,))
        if not (cur.fetchone() or [0])[0]:
            return None
        try:
            now = time.monotonic()
            for key in [k for k, until in _grader_skip.items() if until <= now]:
                _grader_skip.pop(key, None)
            for ans in models.pending_auto_grades(batch + len(_grader_skip)):
                key = (ans["attempt_id"], ans["question_id"])
                if key in _grader_skip:
                    continue
                try:
                    outcome = _grade_answer(ans["attempt_id"], ans, ans.get("email"))
                except Exception:
                    logger.exception("PENDING GRADER: attempt %s q%s failed", ans.get("attempt_id"), ans.get("question_id"))
                    outcome = SKIP
                if outcome == GRADED:
                    graded += 1
                elif outcome == BUSY:
                    break
                else:
                    _grader_skip[key] = now + GRADER_SKIP_SECONDS
        finally:
            cur.execute("SELECT RELEASE_LOCK(%s)", (PENDING_GRADER_LOCK,))
            cur.fetchall()
    finally:
        cur.close()
        conn.close()
    if graded:
        logger.info("PENDING GRADER: graded %d deferred answer(s)", graded)
    return graded


def start_pending_grader(app):
    import os
    import threading
    if os.environ.get('PENDING_GRADER_JOB', '1') == '0':
        return None
    under_server = bool(os.environ.get('RENDER') or os.environ.get('GUNICORN_CMD_ARGS') or os.environ.get('SPP_ASYNC_MODE'))
    if not under_server and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return None
    try:
        seconds = max(5, int(os.environ.get('PENDING_GRADER_INTERVAL', '20')))
    except ValueError:
        seconds = 20
    try:
        workers = max(1, int(os.environ.get('WEB_CONCURRENCY', '1') or 1))
    except ValueError:
        workers = 1
    seconds = seconds * workers

    def loop():
        import random
        time.sleep(30 + random.uniform(0, seconds))
        while True:
            try:
                with app.app_context():
                    run_pending_grader()
            except Exception:
                logger.exception("PENDING GRADER: run failed")
            time.sleep(seconds)

    t = threading.Thread(target=loop, name='pending-grader', daemon=True)
    t.start()
    logger.info("PENDING GRADER: checking every %d second(s)", seconds)
    return t


def finalize_attempt(attempt, email):
    if attempt["status"] != "in_progress":
        return False
    _grade_unsubmitted(attempt["id"], email)
    models.submit_attempt(attempt["id"])
    sync_round_status(attempt["test_id"], email, "completed")
    logger.info("CODING FINISH: [%s] attempt %s submitted", email, attempt["id"])
    return True


def _embedded_nav(attempt_id, sections, current_section, questions):
    nav = []
    for sec in sections:
        qs = questions if sec["id"] == current_section["id"] else models.get_questions(sec["id"])
        flags = models.get_answer_flags(attempt_id, sec["id"])
        nav.append({
            "id": sec["id"],
            "title": sec["title"],
            "questions": [{
                "id": q["id"],
                "n": i + 1,
                "attempted": bool(flags.get(q["id"], {}).get("attempted")),
                "review": bool(flags.get(q["id"], {}).get("review")),
                "url": url_for("coding_test.question_page", attempt_id=attempt_id, question_id=q["id"]),
            } for i, q in enumerate(qs)],
        })
    return nav


@bp.route("/attempt/<int:attempt_id>/review", methods=["POST"])
@limiter.exempt
@login_required
@csrf_protect
def review_api(attempt_id):
    attempt, user, done = _load_attempt(attempt_id)
    if done:
        return jsonify({"error": "This attempt is already submitted"}), 409
    data = request.get_json(silent=True) or {}
    question_id = data.get("question_id")
    if not question_id or not _question_in_attempt(question_id, attempt):
        return jsonify({"error": "Question not part of this attempt"}), 403
    review = bool(data.get("review"))
    models.set_review(attempt_id, question_id, review)
    return jsonify({"review": review})


@bp.route("/attempt/<int:attempt_id>/finish", methods=["POST"])
@login_required
@csrf_protect
def finish(attempt_id):
    attempt, user, done = _load_attempt(attempt_id)
    if not done:
        finalize_attempt(attempt, user.get("email"))
    return redirect(_after_finish_url(attempt))


@bp.route("/attempt/<int:attempt_id>/pause", methods=["POST"])
@limiter.exempt
@login_required
@csrf_protect
def pause(attempt_id):
    user = current_user()
    attempt = models.get_attempt(attempt_id, user["id"])
    if not attempt:
        abort(404)
    models.pause_clock(attempt_id)
    return jsonify({"paused": True})


@bp.route("/attempt/<int:attempt_id>/resume-clock", methods=["POST"])
@limiter.exempt
@login_required
@csrf_protect
def resume_clock(attempt_id):
    user = current_user()
    attempt = models.get_attempt(attempt_id, user["id"])
    if not attempt:
        abort(404)
    models.mark_resumed(attempt_id)
    return jsonify({"resumed": True})


@bp.route("/attempt/<int:attempt_id>/ping", methods=["POST"])
@limiter.exempt
@login_required
@csrf_protect
def ping(attempt_id):
    user = current_user()
    models.touch_attempt(attempt_id, user["id"])
    return jsonify({"ok": True})


AWAY_GRACE_SECONDS = 20


@bp.route("/attempt/<int:attempt_id>/terminate", methods=["POST"])
@login_required
@csrf_protect
def terminate(attempt_id):
    user = current_user()
    attempt = models.get_attempt(attempt_id, user["id"])
    if not attempt:
        abort(404)

    reason = (request.get_json(silent=True) or {}).get("reason", "left_exam_window")
    models.pause_clock(attempt_id)
    session.pop(SITTING_KEY, None)
    session.modified = True
    logger.warning("CODING LEFT WINDOW: [%s] attempt %s (%s) - the next start is a new sitting",
                   user.get("email"), attempt_id, reason)

    return jsonify({
        "status": "terminated",
        "redirect": url_for("coding_test.terminated", attempt_id=attempt_id),
    })


@bp.route("/attempt/<int:attempt_id>/terminated")
@login_required
def terminated(attempt_id):
    user = current_user()
    attempt = models.get_attempt(attempt_id, user["id"])
    if not attempt:
        abort(404)
    test = models.get_test(attempt["test_id"])
    return render_template(
        "users/exam_platform/placement_exam_portal/coding_portal/test/code_termination.html",
        user=user, test=test, attempt=attempt,
        away_seconds=AWAY_GRACE_SECONDS,
        code_kwargs=_code_kwargs(),
        result_url=url_for("coding_test.result", attempt_id=attempt_id, **_code_kwargs()),
        restart_url=(None if attempt["status"] == "submitted" or not test or _is_embedded(attempt)
                     else url_for("coding_test.lobby", slug=test["slug"], **_code_kwargs())),
        dashboard_url=url_for("coding_test.dashboard", **_code_kwargs()),
    ), 403


@bp.route("/certificate/<code>")
def certificate(code):
    if not re.match(r"^[A-Za-z0-9_-]{8,32}$", code or ""):
        abort(404)
    cert = models.get_attempt_by_share_code(code)
    if not cert:
        abort(404)
    rows = result_stats.question_rows({"id": cert["id"]}, cert["test_id"])
    score = sum(r["score"] for r in rows)
    max_score = sum(r["marks"] or 0 for r in rows)
    pct = round(100 * score / max_score) if max_score else 0
    return render_template(
        "users/exam_platform/placement_exam_portal/coding_portal/test/certificate.html",
        cert=cert, score=score, max_score=max_score, pct=pct,
        verify_url=url_for("coding_test.certificate", code=code, _external=True),
    )


@bp.route("/attempt/<int:attempt_id>/result")
@bp.route("/attempt/<int:attempt_id>/result/<course_code>/<unique_code>")
@login_required
def result(attempt_id, course_code=None, unique_code=None):
    _capture_codes(course_code, unique_code)
    user = current_user()
    attempt = models.get_attempt(attempt_id, user["id"])
    if not attempt:
        abort(404)

    test = models.get_test(attempt["test_id"])

    if attempt["status"] in ("in_progress", "expired"):
        logger.info("CODING RESULT BLOCKED: [%s] attempt %s not submitted (%s)",
                    user.get("email"), attempt_id, attempt["status"])
        return redirect(url_for("coding_test.lobby", slug=test["slug"], **_code_kwargs()))

    allotted = test.get("total_duration_min")
    rows = result_stats.question_rows(attempt, test["id"], allotted_minutes=allotted)
    cohort = result_stats.cohort(test["id"], attempt_id)
    summary = result_stats.summary(attempt, rows, cohort, allotted_minutes=allotted)

    sections = {}
    for r in rows:
        s = sections.setdefault(r["section_title"] or r["section_type"], {
            "type": r["section_type"], "rows": [], "score": 0, "marks": 0})
        s["rows"].append(r)
        s["score"] += r["score"]
        s["marks"] += r["marks"] or 0

    logger.info("CODING RESULT: [%s] attempt %s scored %s/%s (rank %s of %s)",
                user.get("email"), attempt_id, summary["score"], summary["max_score"],
                cohort["rank"], cohort["participants"])

    share_code = models.ensure_share_code(attempt_id)
    return render_template(
        "users/exam_platform/placement_exam_portal/coding_portal/test/result.html",
        user=user, test=test, attempt=attempt, rows=rows,
        sections=sections, cohort=cohort, summary=summary,
        fmt_duration=result_stats.fmt_duration,
        certificate_url=(url_for("coding_test.certificate", code=share_code,
                                 _external=True) if share_code else None),
        dashboard_url=url_for("coding_test.dashboard", **_code_kwargs()),
        total_score=summary["score"], max_score=summary["max_score"],
        attempted=summary["attempted"], total_questions=summary["total_questions"],
    )
