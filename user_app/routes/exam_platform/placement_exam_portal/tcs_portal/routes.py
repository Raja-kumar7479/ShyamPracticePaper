import logging

from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   session, url_for)

from extensions import user_login_required
from routes.exam_platform.competitive_exam_platform.databases.main_handler_db import UserOperation
from routes.exam_platform.competitive_exam_platform.databases.result_handler_db import ResultHandler
from routes.exam_platform.competitive_exam_platform.utils.utils_secure_code import secure_access_required
from routes.exam_platform.competitive_exam_platform.utils.utils_test_dashboard import get_user_session
from routes.exam_platform.placement_exam_portal.coding_portal import models as cp_models
from routes.exam_platform.placement_exam_portal.coding_portal import result_stats
from routes.exam_platform.placement_exam_portal.coding_portal.auth_bridge import current_user as coding_user
from . import models

logger = logging.getLogger(__name__)

bp = Blueprint("tcs", __name__, url_prefix="/tcs")

TEMPLATE_DIR = "users/exam_platform/placement_exam_portal/tcs_portal/"
FLOW_KEY = "tcs_flow"

mock_op = UserOperation()
result_op = ResultHandler()


def _tpl(name):
    return TEMPLATE_DIR + name


def _can_access(email, exam):
    if (exam.get("block_label") or "Free") != "Paid":
        return True
    if models.block_purchased(email, exam["section_id"]):
        return True
    from routes.exam_platform.subscription_access import has_platform_subscription
    return has_platform_subscription(email)


def _flow_for(exam, course_code, unique_code):
    return {
        "exam_id": exam["id"],
        "aptitude_test_key": exam["aptitude_test_key"],
        "aptitude_section_id": exam["aptitude_section_id"],
        "coding_test_id": exam["coding_test_id"],
        "course_code": course_code,
        "unique_code": unique_code,
        "section_id": exam["section_id"],
    }


def _load_exam_or_404(exam_id):
    exam = models.get_exam(exam_id)
    if not exam or not exam.get("is_published"):
        abort(404)
    return exam


def _dashboard_url(exam_or_flow):
    return url_for("tcs.dashboard", course_code=exam_or_flow["course_code"],
                   unique_code=exam_or_flow["unique_code"], section_id=exam_or_flow["section_id"])


@bp.route("/<course_code>/<unique_code>/<section_id>")
@user_login_required
@secure_access_required(("course_code", "unique_code"))
def dashboard(course_code, unique_code, section_id):
    email, username, _ = get_user_session()
    session["course_code"] = course_code
    session["unique_code"] = unique_code
    exams = models.list_exams(section_id, course_code.upper())
    attempts = models.attempts_for(email, [e["id"] for e in exams])
    for e in exams:
        a = attempts.get(e["id"])
        e["stage"] = a["stage"] if a else "not_started"
        e["can_access"] = _can_access(email, e)
        e["total_minutes"] = (e.get("aptitude_minutes") or 0) + (e.get("coding_minutes") or 0)
    logger.info("TCS: [%s] dashboard %s/%s (%d exam(s))", email, course_code, section_id, len(exams))
    return render_template(_tpl("dashboard.html"), exams=exams, email=email, username=username,
                           course_code=course_code, unique_code=unique_code, section_id=section_id,
                           premium_url=url_for("users.course_shop", course_code=course_code,
                                               unique_code=unique_code))


@bp.route("/exam/<int:exam_id>/start/<course_code>/<unique_code>")
@user_login_required
@secure_access_required(("course_code", "unique_code"))
def start(exam_id, course_code, unique_code):
    email, username, _ = get_user_session()
    exam = _load_exam_or_404(exam_id)
    if not _can_access(email, exam):
        flash("This is a premium exam. Unlock it from the store to continue.", "test_error")
        return redirect(url_for("users.course_shop", course_code=course_code, unique_code=unique_code))
    if not exam.get("aptitude_title") or not exam.get("coding_slug"):
        flash("This exam is not fully configured yet. Please try again later.", "test_error")
        return redirect(_dashboard_url({"course_code": course_code, "unique_code": unique_code,
                                        "section_id": exam["section_id"]}))

    attempt = models.start_attempt(exam_id, email)
    flow = _flow_for(exam, course_code, unique_code)
    session[FLOW_KEY] = flow
    session.modified = True

    if attempt["stage"] == "completed":
        return redirect(url_for("tcs.result", exam_id=exam_id, course_code=course_code,
                                unique_code=unique_code))

    if attempt["stage"] == "coding":
        return redirect(url_for("tcs.coding_part", exam_id=exam_id))

    from routes.exam_platform.active_test_lock import active_test_redirect, blocked_message
    running = active_test_redirect(email, ignore_test_key=exam["aptitude_test_key"])
    if running:
        flash(blocked_message(), "test_error")
        return redirect(running)

    status_info = mock_op.get_test_status_for_user(email, exam["aptitude_test_key"]) or {}
    if status_info.get("status") in ("in_progress", "unperformed") and status_info.get("attempt_number"):
        attempt_number = status_info["attempt_number"]
    else:
        attempt_number = mock_op.store_user_test_start(email, exam["aptitude_test_key"], username)
    session["test_popup_initiated"] = True
    session["current_test_attempt_number"] = attempt_number
    instruction_url = url_for("users.test_instruction", section_id=exam["aptitude_section_id"],
                              test_key=exam["aptitude_test_key"], course_code=course_code,
                              unique_code=unique_code)
    logger.info("TCS: [%s] launching aptitude %s for exam %s", email, exam["aptitude_test_key"], exam_id)
    return render_template(_tpl("launch.html"), exam=exam, instruction_url=instruction_url,
                           dashboard_url=_dashboard_url(flow), username=username)


@bp.route("/exam/<int:exam_id>/after-aptitude")
@user_login_required
def after_aptitude(exam_id):
    email, username, _ = get_user_session()
    flow = session.get(FLOW_KEY) or {}
    exam = _load_exam_or_404(exam_id)
    if flow.get("exam_id") != exam_id:
        flow = _flow_for(exam, session.get("course_code"), session.get("unique_code"))
        session[FLOW_KEY] = flow
        session.modified = True
    attempt_number = models.latest_aptitude_attempt_number(email, exam["aptitude_test_key"])
    if attempt_number is None:
        flash("Finish the aptitude part before moving to coding.", "test_error")
        return redirect(_dashboard_url(flow))
    models.mark_aptitude_done(exam_id, email, attempt_number)
    logger.info("TCS: [%s] aptitude done for exam %s (attempt %s)", email, exam_id, attempt_number)
    return render_template(_tpl("transition.html"), exam=exam,
                           continue_url=url_for("tcs.coding_part", exam_id=exam_id),
                           dashboard_url=_dashboard_url(flow))


@bp.route("/exam/<int:exam_id>/coding")
@user_login_required
def coding_part(exam_id):
    email, username, _ = get_user_session()
    exam = _load_exam_or_404(exam_id)
    attempt = models.get_attempt(exam_id, email)
    if not attempt or attempt["stage"] == "aptitude":
        flash("Finish the aptitude part first.", "test_error")
        return redirect(url_for("tcs.start", exam_id=exam_id, course_code=session.get("course_code"),
                                unique_code=session.get("unique_code")))
    if attempt["stage"] == "completed":
        return redirect(url_for("tcs.result", exam_id=exam_id, course_code=session.get("course_code"),
                                unique_code=session.get("unique_code")))
    flow = session.get(FLOW_KEY) or _flow_for(exam, session.get("course_code"), session.get("unique_code"))
    session[FLOW_KEY] = flow
    session["coding_course_code"] = flow.get("course_code")
    session["coding_unique_code"] = flow.get("unique_code")
    session.modified = True
    logger.info("TCS: [%s] entering coding part of exam %s", email, exam_id)
    return redirect(url_for("coding_test.start", slug=exam["coding_slug"]))


@bp.route("/exam/<int:exam_id>/after-coding")
@user_login_required
def after_coding(exam_id):
    email, username, _ = get_user_session()
    exam = _load_exam_or_404(exam_id)
    user = coding_user()
    coding_attempt = models.coding_attempt_for(exam["coding_test_id"], user["id"]) if user else None
    if not coding_attempt or coding_attempt["status"] == "in_progress":
        flash("Finish the coding part before viewing the result.", "test_error")
        return redirect(url_for("tcs.coding_part", exam_id=exam_id))
    models.mark_completed(exam_id, email, coding_attempt["id"])
    flow = session.pop(FLOW_KEY, None) or {}
    session.modified = True
    logger.info("TCS: [%s] exam %s completed", email, exam_id)
    return redirect(url_for("tcs.result", exam_id=exam_id,
                            course_code=flow.get("course_code") or session.get("course_code"),
                            unique_code=flow.get("unique_code") or session.get("unique_code")))


def _aptitude_breakdown(summary):
    sections = {}
    for row in summary.get("details") or []:
        name = row.get("section_name") or "General"
        sec = sections.setdefault(name, {"name": name, "questions": 0, "correct": 0,
                                         "incorrect": 0, "skipped": 0, "marks": 0.0})
        sec["questions"] += 1
        status = (row.get("status_of_attempt") or "").lower()
        if row.get("is_correct"):
            sec["correct"] += 1
        elif status in ("answered", "attempted") or row.get("user_selected_option"):
            sec["incorrect"] += 1
        else:
            sec["skipped"] += 1
        sec["marks"] += float(row.get("marks_awarded") or 0)
    return list(sections.values())


@bp.route("/exam/<int:exam_id>/result/<course_code>/<unique_code>")
@user_login_required
@secure_access_required(("course_code", "unique_code"))
def result(exam_id, course_code, unique_code):
    email, username, _ = get_user_session()
    exam = _load_exam_or_404(exam_id)
    attempt = models.get_attempt(exam_id, email)
    if not attempt or attempt["stage"] != "completed":
        flash("Complete both parts of the exam to see the result.", "test_error")
        return redirect(url_for("tcs.start", exam_id=exam_id, course_code=course_code,
                                unique_code=unique_code))

    aptitude = result_op.get_test_summary_details(exam["aptitude_test_key"], email)
    apt_overall = (aptitude or {}).get("overall") or {}
    apt_sections = _aptitude_breakdown(aptitude or {})
    apt_score = float(apt_overall.get("net_score") or 0)
    apt_max = float(apt_overall.get("total_marks") or exam.get("aptitude_marks") or 0)

    coding_summary = None
    coding_rows = []
    cp_attempt = None
    user = coding_user()
    if user:
        cp_attempt = models.coding_attempt_for(exam["coding_test_id"], user["id"])
    if cp_attempt and cp_attempt["status"] != "in_progress":
        allotted = exam.get("coding_minutes")
        coding_rows = result_stats.question_rows(cp_attempt, exam["coding_test_id"], allotted_minutes=allotted)
        cohort = result_stats.cohort(exam["coding_test_id"], cp_attempt["id"])
        coding_summary = result_stats.summary(cp_attempt, coding_rows, cohort, allotted_minutes=allotted)
    code_score = float((coding_summary or {}).get("score") or 0)
    code_max = float((coding_summary or {}).get("max_score") or 0)

    total = apt_score + code_score
    total_max = apt_max + code_max
    overall_pct = round(total * 100.0 / total_max, 1) if total_max else 0.0

    return render_template(_tpl("result.html"), exam=exam, attempt=attempt,
                           apt_overall=apt_overall, apt_sections=apt_sections,
                           apt_score=apt_score, apt_max=apt_max,
                           coding_summary=coding_summary, coding_rows=coding_rows,
                           code_score=code_score, code_max=code_max,
                           total=total, total_max=total_max, overall_pct=overall_pct,
                           username=username, email=email,
                           course_code=course_code, unique_code=unique_code,
                           dashboard_url=url_for("tcs.dashboard", course_code=course_code,
                                                 unique_code=unique_code, section_id=exam["section_id"]),
                           coding_result_url=(url_for("coding_test.result", attempt_id=cp_attempt["id"],
                                                      course_code=course_code, unique_code=unique_code)
                                              if cp_attempt else None),
                           aptitude_result_url=url_for("users.test_result", section_id=exam["aptitude_section_id"],
                                                       test_key=exam["aptitude_test_key"],
                                                       course_code=course_code, unique_code=unique_code))
