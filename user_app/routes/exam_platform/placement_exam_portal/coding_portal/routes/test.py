"""Test taking: dashboard, section/question navigation, autosave, finish."""
import logging
import re

from flask import (Blueprint, render_template, request, redirect, url_for,
                   jsonify, abort, flash, session)

from .. import models
from ..auth_bridge import login_required, current_user, csrf_protect
from ..db import query_all, execute
from ..round_sync import sync_round_status
from .. import result_stats
from routes.exam_platform.active_test_lock import active_test_redirect, blocked_message

logger = logging.getLogger(__name__)
bp = Blueprint("coding_test", __name__, url_prefix="/coding")

# section_type -> template. The only place this mapping lives, so a section
# can never render another type's editor.
SECTION_TEMPLATE = {
    "coding": "users/exam_platform/placement_exam_portal/coding_portal/test/coding.html",
    "sql": "users/exam_platform/placement_exam_portal/coding_portal/test/sql.html",
    "web": "users/exam_platform/placement_exam_portal/coding_portal/test/web.html",
}

# section_type -> the static assets its template's {% block styles/section_lib
# %} pull in. Duplicated here (rather than parsed out of the rendered HTML)
# so an AJAX navigation (examnav.js) knows what to load into <head> without
# needing the full page: the editor styles are common; the rest are
# per-section, matching {% block styles %} and {% block section_lib %} in
# coding.html/sql.html/web.html exactly -- update both places together.
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
    """Remember the enrollment identity (course_code + the unique code minted
    at enrollment) whenever a URL carries it, so every later page and link in
    the portal can keep it attached."""
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
    """url_for kwargs that thread course_code/unique_code into portal links.
    Empty when the portal was opened without an enrollment context, in which
    case url_for falls back to the plain rule."""
    course = session.get("coding_course_code")
    code = session.get("coding_unique_code")
    if course and code:
        return {"course_code": course, "unique_code": code}
    return {}


@bp.route("/")
@bp.route("/<course_code>/<unique_code>")
@login_required
def dashboard(course_code=None, unique_code=None):
    """Coding round dashboard. Course context is optional so the portal also
    works when opened directly, and is kept in session for the back links."""
    user = current_user()
    from flask import session as _session
    _capture_codes(course_code, unique_code)

    # Scope to what the student actually opened. section_id points at one
    # content block; course_code is the fallback when it was not supplied.
    section_id = request.args.get("section_id") or _session.get("coding_section_id")
    if section_id:
        _session["coding_section_id"] = section_id
    course_code = course_code or _session.get("coding_course_code")
    tests = models.list_published_tests(course_code=course_code, test_id=section_id)
    for t in tests:
        t["sections"] = models.get_sections(t["id"])
        # Newest attempt wins. Without the ordering a student with more than one
        # attempt row got whichever the engine happened to return first, so a
        # submitted test could still advertise itself as startable.
        attempt = query_all(
            "SELECT id, status FROM cp_attempts WHERE test_id = %s AND user_id = %s "
            "ORDER BY id DESC LIMIT 1",
            (t["id"], user["id"]),
        )
        t["attempt_status"] = attempt[0]["status"] if attempt else None
        t["attempt_id"] = attempt[0]["id"] if attempt else None
    return render_template("users/exam_platform/placement_exam_portal/coding_portal/test/dashboard.html", user=user, tests=tests, code_kwargs=_code_kwargs())


def _intro_context(slug):
    """Shared context for the two pre-exam screens.

    Both need the same thing: the test, its sections and the total question
    count, so the candidate sees what they are about to sit before it starts.
    """
    test = models.get_test_by_slug(slug)
    if not test or not test["is_published"]:
        abort(404)

    # The premium gate lives in the callers: this helper only builds context,
    # and its result is splatted into render_template, so returning a redirect
    # from here could never have worked.
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
    """Step 1: what the assessment is, and whether this browser can run it."""
    _capture_codes(course_code, unique_code)
    user = current_user()
    test = models.get_test_by_slug(slug)
    if test:
        running = active_test_redirect(user.get("email"), ignore_test_key=test.get("test_key"))
        if running:
            flash(blocked_message(), "coding_error")
            return redirect(running)
        blocked = _completed_block(test, user)
        if blocked:
            return blocked
        if _premium_block(test, user.get("email")):
            flash("This is a premium assessment. Subscribe to unlock all tests.", "coding_error")
            return redirect(url_for("practice_coding.premium"))
    return render_template(
        "users/exam_platform/placement_exam_portal/coding_portal/system_info.html",
        **_intro_context(slug))



def _latest_attempt(test_id, user_id):
    rows = query_all(
        "SELECT id, status FROM cp_attempts WHERE test_id = %s AND user_id = %s "
        "ORDER BY id DESC LIMIT 1",
        (test_id, user_id),
    )
    return rows[0] if rows else None


def _render_already_submitted(test, attempt_id):
    """One page for every 'you already sat this' path, with a way to the result."""
    return render_template(
        "users/exam_platform/placement_exam_portal/coding_portal/test/already_submitted.html",
        user=current_user(),
        test=test,
        result_url=url_for("coding_test.result", attempt_id=attempt_id, **_code_kwargs()),
        dashboard_url=url_for("coding_test.dashboard", **_code_kwargs()),
    ), 403


def _completed_block(test, user):
    """Refuse a second sitting of a closed coding test.

    Only a submitted attempt (Finish clicked or timer expired) closes a test.
    Leaving the exam window does not: such an attempt stays resumable, so if an
    older attempt is still marked 'expired' it is reopened here and the
    candidate is allowed straight back in.
    """
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
        logger.info("CODING RESUME: [%s] test %s reopened after leaving window",
                    user.get("email"), test.get("slug"))

    return None


def _premium_block(test, email):
    from routes.exam_platform.subscription_access import has_platform_subscription
    if (test.get("access_label") or "inherit") != "paid":
        return False
    if has_platform_subscription(email):
        return False
    logger.warning("CODING PREMIUM BLOCKED: [%s] test %s without subscription", email, test.get("slug"))
    return True

@bp.route("/test/<slug>/lobby")
@bp.route("/test/<slug>/lobby/<course_code>/<unique_code>")
@login_required
def lobby(slug, course_code=None, unique_code=None):
    """Step 2: the section list and a short countdown before the clock starts."""
    _capture_codes(course_code, unique_code)
    user = current_user()
    _t = models.get_test_by_slug(slug)
    if _t:
        blocked = _completed_block(_t, user)
        if blocked:
            return blocked
        if _premium_block(_t, user.get("email")):
            flash("This is a premium assessment. Subscribe to unlock all tests.", "coding_error")
            return redirect(url_for("practice_coding.premium"))
    context = _intro_context(slug)
    if not context["sections"]:
        # Nothing to sit; say so on the dashboard rather than opening an
        # empty lobby the Start button could not leave.
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
    user = current_user()
    test = models.get_test_by_slug(slug)
    if not test or not test["is_published"]:
        abort(404)

    running = active_test_redirect(user.get("email"), ignore_test_key=test.get("test_key"))
    if running:
        flash(blocked_message(), "coding_error")
        return redirect(running)

    blocked = _completed_block(test, user)
    if blocked:
        return blocked

    attempt = models.get_or_create_attempt(test["id"], user["id"])
    if attempt["status"] == "submitted":
        return _render_already_submitted(test, attempt["id"])

    sync_round_status(test["id"], user.get("email"), "started")

    sections = models.get_sections(test["id"])
    if not sections:
        # Re-rendering the dashboard here made it look like the assessment list
        # opened a second time. Send the student back to the one dashboard with
        # a message instead.
        flash("This assessment has no sections yet. Please try again later.", "coding_error")
        logger.warning("CODING: test %s has no sections; start blocked", test["id"])
        return redirect(url_for("coding_test.dashboard"))
    return redirect(url_for("coding_test.section_page", attempt_id=attempt["id"],
                            section_id=sections[0]["id"]))


def _load_attempt(attempt_id):
    """Fetch the attempt, enforcing ownership and open status."""
    user = current_user()
    attempt = models.get_attempt(attempt_id, user["id"])
    if not attempt:
        abort(404)
    if attempt["status"] != "in_progress":
        return attempt, user, True
    return attempt, user, False


def _remaining_seconds(attempt, test):
    """Server-authoritative time left; the client clock is never trusted.

    Counts only time actually spent in the exam (elapsed_seconds plus the
    running segment), all measured on the database clock. Wall-clock deadlines
    from started_at broke in two ways: any skew between the app and DB clocks
    shifted the timer, and a resumed attempt had its absent hours counted,
    so it auto-submitted the moment the candidate returned.
    """
    used = models.active_seconds(attempt["id"])
    return max(0, test["total_duration_min"] * 60 - used)


@bp.route("/attempt/<int:attempt_id>/summary")
@login_required
def finish_summary(attempt_id):
    """What the Finish overlay shows before final submit: attempted counts
    per section and overall, plus the live remaining time."""
    attempt, user, done = _load_attempt(attempt_id)
    if done:
        return jsonify({"redirect": _after_finish_url(attempt)})
    test = models.get_test(attempt["test_id"])
    rows = query_all(
        """
        SELECT s.id, s.title, s.section_type,
               COUNT(q.id) AS total,
               COALESCE(SUM(CASE WHEN a.is_attempted = 1 THEN 1 ELSE 0 END), 0)
                   AS attempted
          FROM cp_sections s
          LEFT JOIN cp_questions q ON q.section_id = s.id
          LEFT JOIN cp_answers a ON a.question_id = q.id AND a.attempt_id = %s
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
    # examnav.js marks its fetches so the same route can return either a full
    # page (first load, refresh, direct link) or just the exam_root fragment
    # for its own in-place navigation.
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _section_config(section, question, cfg_extra):
    """Everything a section's JS (initCoding/initSql/initWeb) needs, built
    once here so the full page render and the AJAX fragment stay identical."""
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
        abort(404)   # question does not belong to this attempt's test

    models.mark_resumed(attempt_id)
    remaining = _remaining_seconds(attempt, test)
    if remaining <= 0:
        _grade_unsubmitted(attempt_id, user.get("email"))
        models.submit_attempt(attempt_id)
        # Time-up is a completion too, so the round page must learn about it.
        sync_round_status(attempt["test_id"], user.get("email"), "completed")
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
    exam_config = {
        "attemptId": attempt_id,
        "questionId": question_id,
        "sectionType": section["section_type"],
        "remainingSeconds": remaining,
        "pauseUrl": url_for("coding_test.pause", attempt_id=attempt_id),
        "resumeUrl": url_for("coding_test.resume_clock", attempt_id=attempt_id),
        "summaryUrl": url_for("coding_test.finish_summary", attempt_id=attempt_id),
        "section": _section_config(section, question,
                                   {"answer": answer, "attempt_id": attempt_id}),
    }

    # Navigation is free in both directions. The answer row always holds the
    # latest saved/submitted code, so revisiting a question restores exactly
    # where the candidate left off.
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
        attempted_map=models.get_attempted_map(attempt_id, section["id"]),
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
    """Guard against writing an answer to a question from a different test."""
    question = models.get_question(question_id)
    if not question:
        return False
    section = models.get_section(question["section_id"])
    return bool(section and section["test_id"] == attempt["test_id"])


def _grade_unsubmitted(attempt_id, email):
    """Judge coding answers that were written (autosaved) but never put
    through Submit Code, so finished work is scored instead of appearing on
    the result page as 'not attempted'. Best effort per question: a judge
    failure on one answer must not block the finish."""
    from ..services import code_executor
    for ans in models.unsubmitted_saved_answers(attempt_id):
        try:
            question = models.get_question(ans["question_id"])
            if not question or ans["language"] not in code_executor.LANGUAGES:
                continue
            testcases = models.get_testcases(question["id"], include_hidden=True)
            if not testcases:
                continue
            result = code_executor.execute(
                ans["code"], ans["language"], testcases,
                time_limit=question["time_limit_sec"],
                memory_limit=question["memory_limit"],
                compare_mode=question.get("compare_mode") or "exact",
                float_tolerance=question.get("float_tolerance"),
            )
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
        except Exception:
            logger.exception("CODING FINISH-GRADE FAILED: attempt %s q%s",
                             attempt_id, ans.get("question_id"))


@bp.route("/attempt/<int:attempt_id>/finish", methods=["POST"])
@login_required
@csrf_protect
def finish(attempt_id):
    attempt, user, done = _load_attempt(attempt_id)
    if not done:
        _grade_unsubmitted(attempt_id, user.get("email"))
        models.submit_attempt(attempt_id)
        # Record it where the round page and the completed-test guards read
        # from, so the assessment card flips to Completed straight away.
        sync_round_status(attempt["test_id"], user.get("email"), "completed")
        logger.info("CODING FINISH: [%s] attempt %s submitted", user.get("email"), attempt_id)
    return redirect(_after_finish_url(attempt))


@bp.route("/attempt/<int:attempt_id>/pause", methods=["POST"])
@login_required
@csrf_protect
def pause(attempt_id):
    """Beacon target: the exam page reports it is going off screen (tab
    hidden, tab closed) so the active-time clock stops. Idempotent."""
    user = current_user()
    attempt = models.get_attempt(attempt_id, user["id"])
    if not attempt:
        abort(404)
    models.pause_clock(attempt_id)
    return jsonify({"paused": True})


@bp.route("/attempt/<int:attempt_id>/resume-clock", methods=["POST"])
@login_required
@csrf_protect
def resume_clock(attempt_id):
    """The exam page is back on screen; restart the active-time segment."""
    user = current_user()
    attempt = models.get_attempt(attempt_id, user["id"])
    if not attempt:
        abort(404)
    models.mark_resumed(attempt_id)
    return jsonify({"resumed": True})


AWAY_GRACE_SECONDS = 20


@bp.route("/attempt/<int:attempt_id>/terminate", methods=["POST"])
@login_required
@csrf_protect
def terminate(attempt_id):
    """Show the leave-warning page for a candidate who left the exam window.

    The window guard calls this once the candidate has been away from the exam
    for AWAY_GRACE_SECONDS. The attempt is NOT closed: leaving the window is a
    warning, not the end of the test. The attempt stays in_progress so the
    candidate can resume any number of times. Only clicking Finish or the timer
    running out (both set 'submitted') ends a test and reveals the result.
    """
    user = current_user()
    attempt = models.get_attempt(attempt_id, user["id"])
    if not attempt:
        abort(404)

    reason = (request.get_json(silent=True) or {}).get("reason", "left_exam_window")
    models.pause_clock(attempt_id)
    logger.warning("CODING LEFT WINDOW: [%s] attempt %s (%s) - resumable, clock paused",
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
        dashboard_url=url_for("coding_test.dashboard", **_code_kwargs()),
    ), 403


@bp.route("/certificate/<code>")
def certificate(code):
    """Public, login-free certificate for a submitted attempt. The code is an
    unguessable random token, and the page shows only the display name, test,
    score and date - never the email or any internal id."""
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

    # Results are shown only after the attempt is genuinely finished - the
    # candidate clicked Finish or the timer ran out (both set 'submitted').
    # A still-running attempt must never reveal its score, so send the
    # candidate back into their test; a terminated one shows the closed page.
    if attempt["status"] in ("in_progress", "expired"):
        logger.info("CODING RESULT BLOCKED: [%s] attempt %s not submitted (%s) - resuming",
                    user.get("email"), attempt_id, attempt["status"])
        return redirect(url_for("coding_test.start", slug=test["slug"], **_code_kwargs()))

    allotted = test.get("total_duration_min")
    rows = result_stats.question_rows(attempt, test["id"], allotted_minutes=allotted)
    cohort = result_stats.cohort(test["id"], attempt_id)
    summary = result_stats.summary(attempt, rows, cohort, allotted_minutes=allotted)

    # Grouped so the page can show a per-section breakdown as well as the list.
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
        # Kept so anything still reading the old names keeps working.
        total_score=summary["score"], max_score=summary["max_score"],
        attempted=summary["attempted"], total_questions=summary["total_questions"],
    )
