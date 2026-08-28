import base64
import os
import uuid
import logging
import sys
import json
import time
import datetime
from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify, abort, make_response, flash
from flask_socketio import emit, join_room

try:
    from extensions import socketio
except ImportError:
    from flask_socketio import SocketIO
    socketio = SocketIO()

from routes.exam_platform.placement_exam_portal.communication_portal.databases.proctor_db import ProctorDB
from routes.exam_platform.placement_exam_portal.communication_portal.utils.utils_token import get_user_session, comm_login_required
from routes.exam_platform.placement_exam_portal.communication_portal.utils.utils_secure_code  import secure_access_required
from routes import users_bp 

logger = logging.getLogger(__name__)
db_ops = ProctorDB()

from config import Config
UPLOAD_FOLDER_AUDIO = os.path.join(Config.UPLOAD_BASE, 'user_responses')
UPLOAD_FOLDER_VERIFY = os.path.join(Config.UPLOAD_BASE, 'verification')

# Proctor snapshots: a per-file ceiling, since the only other limit was the
# global 32 MB request cap.
MAX_SNAPSHOT_BYTES = 3 * 1024 * 1024
MAX_AUDIO_BYTES = 15 * 1024 * 1024


def _safe_path_part(value):
    """Reduce a value to characters that cannot steer a filesystem path."""
    import re as _re
    cleaned = _re.sub(r'[^A-Za-z0-9._-]', '_', str(value or 'unknown'))
    # Leading dots are stripped as well: "../../x" survives sanitising as
    # "..__x", which is harmless as a path but makes a hidden file that a
    # plain listing of the upload folder skips over.
    cleaned = cleaned.lstrip('.')
    return cleaned[:60] or 'unknown'
os.makedirs(UPLOAD_FOLDER_AUDIO, exist_ok=True)
os.makedirs(UPLOAD_FOLDER_VERIFY, exist_ok=True)


def user_folder_token(email):
    import hashlib
    digest = hashlib.sha1(str(email or 'unknown').encode('utf-8')).hexdigest()[:8]
    return f"{_safe_path_part(email)[:40]}_{digest}"


_ROUND_CACHE = {}
_ROUND_CACHE_TTL = 300


def _cached_round(test_key):
    now = time.time()
    hit = _ROUND_CACHE.get(test_key)
    if hit and now - hit[1] < _ROUND_CACHE_TTL:
        return hit[0]
    try:
        value = db_ops.get_round_for_test_key(test_key)
    except Exception:
        value = None
    _ROUND_CACHE[test_key] = (value, now)
    if len(_ROUND_CACHE) > 2048:
        _ROUND_CACHE.clear()
    return value


def user_upload_dir(kind, test_key, email, portal=None):
    if not portal:
        portal = _cached_round(test_key)
    safe_portal = _safe_path_part(portal or 'general').lower()
    safe_test = _safe_path_part(test_key)
    safe_user = user_folder_token(email)
    rel = f"{kind}/{safe_portal}/{safe_test}/{safe_user}"
    folder = os.path.join(Config.UPLOAD_BASE, kind, safe_portal, safe_test, safe_user)
    os.makedirs(folder, exist_ok=True)
    return folder, rel

from contextlib import contextmanager


@contextmanager
def _db(dictionary=False):
    conn = db_ops.get_conn()
    cursor = None
    try:
        cursor = conn.cursor(dictionary=dictionary)
        yield conn, cursor
    finally:
        if cursor:
            try: cursor.close()
            except Exception: pass
        try: conn.close()
        except Exception: pass


def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = uuid.uuid4().hex
    return session['_csrf_token']


import hmac as _hmac
from functools import wraps as _wraps


def comm_csrf_protect(f):
    @_wraps(f)
    def wrapper(*args, **kwargs):
        sess_token = session.get('_csrf_token')
        token = (request.headers.get('X-CSRFToken')
                 or request.form.get('_csrf_token')
                 or request.form.get('csrf_token')
                 or request.args.get('csrf'))
        if not token and request.is_json:
            body = request.get_json(silent=True)
            if isinstance(body, dict):
                token = body.get('csrf_token')
        if not sess_token or not token or not _hmac.compare_digest(str(sess_token), str(token)):
            logger.warning("COMM CSRF BLOCKED: %s %s from %s",
                           request.method, request.path, request.remote_addr)
            return jsonify({"status": "error", "message": "Session expired. Refresh and try again."}), 403
        return f(*args, **kwargs)
    return wrapper

@users_bp.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf_token)

def validate_active_session_or_abort(test_key, email):
    token = session.get('active_test_token')
    if not token:
        return False
    return db_ops.validate_token(email, test_key, token)


def _comm_premium_block(email, test_key):
    from routes.exam_platform.subscription_access import has_platform_subscription
    conn = db_ops.get_conn(); cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT COALESCE(access_label,'inherit') AS a FROM comm_description WHERE test_key=%s", (test_key,))
        row = cursor.fetchone()
    finally:
        cursor.close(); conn.close()
    if row and row['a'] == 'paid' and not has_platform_subscription(email):
        logger.warning(f"COMM PREMIUM BLOCKED: [{email}] test {test_key} without subscription")
        return True
    return False

@users_bp.route('/<round_name>/assessment_system_info/<test_key>/<course_code>/<unique_code>')
@comm_login_required
@secure_access_required(('course_code', 'unique_code'))
def assessment_system_info(test_key, round_name, course_code, unique_code):
    email, username, _ = get_user_session()

    if _comm_premium_block(email, test_key):
        from routes.exam_platform.subscription_access import PREMIUM_ENDPOINT
        flash('This is a premium assessment. Subscribe to unlock all tests.', 'test_error')
        return redirect(url_for(PREMIUM_ENDPOINT))

    from routes.exam_platform.active_test_lock import active_test_redirect, blocked_message
    running = active_test_redirect(email, ignore_test_key=test_key)
    if running:
        logger.warning(f"COMM SYSINFO BLOCKED: [{email}] another test is running")
        flash(blocked_message(), 'test_error')
        return redirect(running)

    actual_round = db_ops.get_round_for_test_key(test_key)
    if actual_round and actual_round != round_name:
        return redirect(url_for('users.assessment_system_info', test_key=test_key, round_name=actual_round,
                                course_code=course_code, unique_code=unique_code))
    with _db(dictionary=True) as (conn, cursor):
        cursor.execute("SELECT status FROM comm_user_log WHERE email=%s AND test_key=%s", (email, test_key))
        status_row = cursor.fetchone()

    if status_row and status_row['status'] == 'completed':
        return render_template('users/exam_platform/placement_exam_portal/communication_portal/test_completed.html', 
                               message="This test has already been submitted. You cannot restart it.")

    meta = db_ops.get_assessment_meta(test_key)
    target_url = url_for('users.assessment_intro', test_key=test_key, round_name=round_name, 
                         course_code=course_code, unique_code=unique_code, _external=True)

    return render_template('users/exam_platform/placement_exam_portal/communication_portal/system_info.html', 
                           data=meta, seb_launch_link=target_url, 
                           username=username, test_key=test_key, round_name=round_name, 
                           course_code=course_code, unique_code=unique_code, 
                           section_count=meta['total_sections'])

@users_bp.route('/<round_name>/assessment_intro/<test_key>/<course_code>/<unique_code>')
@comm_login_required
def assessment_intro(test_key, round_name, course_code, unique_code):
    try:
        email, username, _ = get_user_session()

        if _comm_premium_block(email, test_key):
            from routes.exam_platform.subscription_access import PREMIUM_ENDPOINT
            flash('This is a premium assessment. Subscribe to unlock all tests.', 'test_error')
            return redirect(url_for(PREMIUM_ENDPOINT))

        meta = db_ops.get_assessment_meta(test_key)
        session['course_code'] = course_code
        session['unique_code'] = unique_code
        
        with _db(dictionary=True) as (conn, cursor):
            cursor.execute("SELECT status FROM comm_user_log WHERE email=%s AND test_key=%s", (email, test_key))
            row = cursor.fetchone()

        if row and row['status'] == 'completed':
             return render_template('users/exam_platform/placement_exam_portal/communication_portal/test_completed.html', 
                                   message="Test Terminated: This assessment is already completed.")

        from routes.exam_platform.active_test_lock import active_test_redirect, blocked_message
        running = active_test_redirect(email, ignore_test_key=test_key)
        if running:
            logger.warning(f"COMM INTRO BLOCKED: [{email}] another test is running")
            flash(blocked_message(), 'test_error')
            return redirect(running)

        token = db_ops.generate_session_token(email, test_key, course_code, unique_code)
        if not token:
             return render_template('users/exam_platform/placement_exam_portal/communication_portal/test_completed.html', 
                                   message="Test Terminated: Unable to generate secure session.")

        wiped = db_ops.clear_attempt_details(email, test_key)
        if wiped:
            logger.info(f"COMM FRESH SITTING: [{email}] {test_key} cleared {wiped} previous answer(s)")

        session['active_test_token'] = token
        
        # The camera / microphone / screen-share permission step was removed:
        # the assessment needs none of them up front (the microphone is asked
        # for by the browser itself when a speaking question starts recording),
        # so the flow goes straight to candidate verification.
        return redirect(url_for('users.assessment_verification', test_key=test_key,
                                round_name=round_name, course_code=course_code,
                                unique_code=unique_code))
    except Exception as e:
        logger.error(f"Error in assessment_intro: {e}")
        return render_template('error_500.html'), 500

@users_bp.route('/<round_name>/assessment_verification/<test_key>/<course_code>/<unique_code>')
@comm_login_required
@secure_access_required(('course_code', 'unique_code'))
def assessment_verification(test_key, round_name, course_code, unique_code):
    email, username, _ = get_user_session()

    if not validate_active_session_or_abort(test_key, email):
        return render_template('users/exam_platform/placement_exam_portal/communication_portal/test_completed.html',
                               message="Invalid Access: Session token invalid or test open in another window.")

    meta = db_ops.get_assessment_meta(test_key)
    current_token = session.get('active_test_token')

    return render_template('users/exam_platform/placement_exam_portal/communication_portal/candidate_verify.html', 
                           data=meta, email=email, username=username, test_key=test_key, 
                           round_name=round_name, course_code=course_code, unique_code=unique_code, 
                           section_count=meta['total_sections'],
                           active_token=current_token)

@users_bp.route('/<round_name>/assessment_lobby/<test_key>/<course_code>/<unique_code>')
@comm_login_required
@secure_access_required(('course_code', 'unique_code'))
def assessment_lobby(test_key, round_name, course_code, unique_code):
    try:
        email, username, _ = get_user_session()
        if not validate_active_session_or_abort(test_key, email):
            return render_template('users/exam_platform/placement_exam_portal/communication_portal/test_completed.html',
                                   message="Warning: Test session invalid. You may have the test open in another window.")

        meta = db_ops.get_assessment_meta(test_key)
        sections = db_ops.get_assessment_sections(test_key)
        return render_template('users/exam_platform/placement_exam_portal/communication_portal/exam_lobby.html', 
                               data=meta, sections=sections, section_count=len(sections),
                               username=username, test_key=test_key, round_name=round_name, 
                               course_code=course_code, unique_code=unique_code)
    except Exception as e:
        logger.error(f"Lobby Error: {e}")
        return render_template('error_500.html'), 500

@users_bp.route('/start_test/<test_key>/<course_code>/<unique_code>')
@comm_login_required
@secure_access_required(('course_code', 'unique_code'))
def start_proctored_test(test_key, course_code, unique_code):
    round_name = db_ops.get_round_for_test_key(test_key) or 'Communication'
    return redirect(url_for('users.start_test_window', test_key=test_key, round_name=round_name, course_code=course_code, unique_code=unique_code))

@users_bp.route('/<round_name>/start_test_window/<test_key>/<course_code>/<unique_code>')
@comm_login_required
def start_test_window(test_key, round_name, course_code, unique_code):
    email, username, _ = get_user_session()
    
    token = session.get('active_test_token')

    if not token or not db_ops.validate_token(email, test_key, token):
        session.pop('active_test_token', None)
        other = db_ops.check_concurrent_session(email, test_key)
        if other:
            return render_template('users/exam_platform/placement_exam_portal/communication_portal/test_completed.html',
                                   message="Warning: Test is going on in another window or your session has expired.")
        logger.info(f"COMM WINDOW: [{email}] stale/missing token for {test_key} — restarting flow from intro")
        flash('Your previous session ended. Starting a fresh session for this assessment.', 'test_info')
        return redirect(url_for('users.assessment_intro', test_key=test_key, round_name=round_name,
                                course_code=course_code, unique_code=unique_code))

    meta = db_ops.get_assessment_meta(test_key)
    return render_template('users/exam_platform/placement_exam_portal/communication_portal/test_window.html', 
                           test_key=test_key, email=email, username=username,
                           round_name=round_name, course_code=course_code, unique_code=unique_code,
                           overall_time=meta['total_duration'] if meta else 3600,
                           active_token=token)

@users_bp.route('/api/submit-answer', methods=['POST'])
@comm_login_required
@comm_csrf_protect
def get_submit_answer():
    try:
        email, _, _ = get_user_session()
        test_key = request.form.get('test_key')
        
        req_token = request.form.get('session_token')
        
        if not req_token or not db_ops.validate_token(email, test_key, req_token):
             return jsonify({"status": "error", "message": "Multiple windows detected. Session invalidated."}), 403

        q_id = request.form.get('question_id')
        ans_type = request.form.get('type')
        db_path, sel_opt, txt_res = None, None, None
        
        if ans_type == 'audio':
            if 'file' in request.files:
                file = request.files['file']
                file.seek(0, os.SEEK_END)
                blob_size = file.tell()
                file.seek(0)
                if blob_size > MAX_AUDIO_BYTES:
                    logger.warning(f"COMM AUDIO REJECTED: [{email}] {blob_size} bytes for q{q_id}")
                    return jsonify({"status": "error",
                                    "message": "Recording too large. Please re-record a shorter answer."}), 413
                folder, rel_folder = user_upload_dir('user_responses', test_key, email)
                filename = f"q{_safe_path_part(q_id)}_{uuid.uuid4().hex[:8]}.webm"
                file.save(os.path.join(folder, filename))
                db_path = f"static/uploads/{rel_folder}/{filename}"
                
        elif ans_type == 'mcq':
            sel_opt = request.form.get('value')
        elif ans_type in ['text', 'writing', 'fill_blank']:
            txt_res = request.form.get('value')

        user_answer = sel_opt if sel_opt else txt_res
        score = 0
        if ans_type == 'mcq':
            score = db_ops.calculate_score(q_id, user_answer, test_key)
        elif ans_type == 'audio' and request.form.get('transcription'):
            from routes.exam_platform.placement_exam_portal.communication_portal.utils.speech_analysis import analyse_speech
            target = db_ops.get_question_text(q_id, test_key)
            analysis = analyse_speech(target, request.form.get('transcription'),
                                      float(request.form.get('rec_time', 0)))
            score = analysis['accuracy_pct'] or 0
            logger.info(f"SPEECH SCORE: [{email}] q={q_id} accuracy={score}% wpm={analysis['wpm']}")

        data = {
            'email': email, 'test_key': test_key, 'question_id': q_id,
            'section_name': request.form.get('section_name'),
            'selected_option': sel_opt, 
            'text_response': txt_res,
            'audio_path': db_path, 'transcription': request.form.get('transcription', ''),
            'score': score,
            'rec_time': float(request.form.get('rec_time', 0))
        }
        
        success = db_ops.submit_attempt(data)
        if success: return jsonify({"status": "success"})
        else: return jsonify({"status": "error"}), 500

    except Exception as e:
        logger.exception(f"Submit Error: {e}")
        return jsonify({"status": "error", "message": "Could not save your answer. Please retry."}), 500

@users_bp.route('/finish-test', methods=['POST'])
@comm_login_required
@comm_csrf_protect
def finish_test():
    try:
        data = request.json
        test_key = data.get('test_key')
        email, _, _ = get_user_session()
        if not validate_active_session_or_abort(test_key, email):
             return jsonify({'status': 'error', 'message': 'Invalid session'}), 403
        db_ops.finish_test_session(email, test_key)
        session.pop('active_test_token', None)
        return jsonify({'redirect': url_for('users.get_test_feedback', 
                                            test_key=test_key, 
                                            round_name=data.get('round_name'), 
                                            course_code=data.get('course_code'), 
                                            unique_code=data.get('unique_code'))})
    except Exception as e:
        logger.error(f"Finish Error: {e}")
        return jsonify({'status': 'error'}), 500

@users_bp.route('/api/get-test-data/<test_key>')
@comm_login_required
def get_test_data(test_key):
    try:
        email, _, _ = get_user_session()
        token = session.get('active_test_token')
        if not token or not db_ops.validate_token(email, test_key, token):
             return jsonify({"error": "Unauthorized"}), 401
        sections = db_ops.get_assessment_sections(test_key)
        raw_questions = db_ops.get_all_questions(test_key)
        final_qs = []
        def strip_answers(question):
            safe = dict(question)
            safe.pop('correct_option', None)
            safe.pop('sub_questions', None)
            return safe

        for q in raw_questions:
            if q.get('sub_questions'):
                try:
                    subs = json.loads(q['sub_questions'])
                    for idx, sub in enumerate(subs):
                        new_q = strip_answers(q)
                        new_q['id'] = f"{q['id']}_{idx}"
                        new_q['question_text'] = sub.get('text')
                        final_qs.append(new_q)
                except (ValueError, TypeError, KeyError):
                    final_qs.append(strip_answers(q))
            else:
                final_qs.append(strip_answers(q))
        with _db(dictionary=True) as (conn, cursor):
            cursor.execute("SELECT question_id, selected_option, text_response FROM comm_attempt_details WHERE email=%s AND test_key=%s", (email, test_key))
            saved_attempts = cursor.fetchall()
        answers_map = {}
        for a in saved_attempts:
            if a['selected_option']: answers_map[str(a['question_id'])] = a['selected_option']
            elif a['text_response']: answers_map[str(a['question_id'])] = a['text_response']
        return jsonify({"sections": sections, "questions": final_qs, "answers": answers_map}) 
    except Exception:
        logger.exception("GET TEST DATA FAILED")
        return jsonify({"error": "Could not load the test. Please refresh."}), 500

@users_bp.route('/<round_name>/test-feedback/<test_key>/<course_code>/<unique_code>')
@comm_login_required
def get_test_feedback(test_key, round_name, course_code, unique_code):
    return render_template('users/exam_platform/placement_exam_portal/communication_portal/test_feedback.html', test_key=test_key, round_name=round_name, course_code=course_code, unique_code=unique_code)

@users_bp.route('/submit-feedback', methods=['POST'])
@comm_login_required
def get_submit_feedback():
    try:
        test_key = request.form.get('test_key'); email, _, _ = get_user_session()
        db_ops.save_feedback(email, test_key, request.form.get('rating'), request.form.get('comments'))
        # After feedback the student goes back to the round dashboard; the
        # result is opened from there (View Result) when they choose to look.
        round_name = request.form.get('round_name') or db_ops.get_round_for_test_key(test_key) or 'Communication'
        course_code = request.form.get('course_code') or session.get('course_code')
        unique_code = request.form.get('unique_code') or session.get('unique_code')
        target = url_for('users.round_assessments', round_name=round_name,
                         course_code=course_code, unique_code=unique_code)
        logger.info(f"FEEDBACK SAVED: [{email}] {test_key} -> dashboard")
        return jsonify({'redirect': target})
    except Exception:
        logger.exception("SUBMIT FEEDBACK FAILED")
        return jsonify({'status': 'error'}), 500

def build_skill_guide(report):
    pct = report.get('overall_pct')
    speaking = report.get('speaking_accuracy')
    skipped = report.get('skipped') or 0

    if pct is None and speaking is not None:
        pct = speaking
    if pct is None:
        verdict, headline = 'Reviewed', 'Your responses are recorded. Review each section below.'
    elif pct >= 80:
        verdict, headline = 'Excellent', 'You are performing at an interview-ready level. Keep this consistency.'
    elif pct >= 60:
        verdict, headline = 'Good', 'A solid attempt — a focused revision of your weak sections will push you above 80%.'
    elif pct >= 40:
        verdict, headline = 'Needs Practice', 'You have the basics; daily practice on the weak areas below will lift your score quickly.'
    else:
        verdict, headline = 'Focus Required', 'Start with fundamentals in the sections below, then re-attempt a practice set.'

    tips = []
    for sec in report.get('sections', []):
        title = sec.get('title') or sec.get('name')
        if sec.get('score_pct') is not None and sec['score_pct'] < 60:
            tips.append(f"{title}: only {sec['score_pct']}% correct — review the mistakes in this section below and re-practise similar questions.")
        if sec.get('speech_accuracy') is not None and sec['speech_accuracy'] < 70:
            tips.append(f"{title}: your speech matched {sec['speech_accuracy']}% of the text — read aloud daily and record yourself to improve clarity and pace.")
        if sec.get('total') and sec.get('attempted', 0) < sec['total']:
            missed = sec['total'] - sec['attempted']
            tips.append(f"{title}: {missed} question(s) left unattempted — in the real exam, attempt everything; unanswered questions can never score.")
    if skipped and not any('unattempted' in t for t in tips):
        tips.append(f"You skipped {skipped} question(s) overall — manage your section time so nothing is left blank.")
    if not tips:
        tips.append('No major gaps found. Maintain momentum with one timed practice set per week.')

    return {'verdict': verdict, 'headline': headline, 'tips': tips, 'pct': pct}


@users_bp.route('/<round_name>/test-result/<test_key>/<course_code>/<unique_code>')
@comm_login_required
def get_test_result(test_key, round_name, course_code, unique_code):
    try:
        email, _, authenticated = get_user_session()
        if not authenticated or not email:
            return redirect(url_for('users.user_login'))
        # A score is shown only after the assessment is genuinely completed, so
        # a candidate cannot open the result page mid-test to peek at answers.
        if db_ops.get_user_test_status(email, test_key) != 'completed':
            logger.warning(f"COMM RESULT BLOCKED: [{email}] {test_key} not completed")
            return redirect(url_for('users.round_assessments', round_name=round_name,
                                    course_code=course_code, unique_code=unique_code))
        report = db_ops.get_full_analysis(email, test_key)
        completed_at = db_ops.get_completion_time(email, test_key)
        guide = build_skill_guide(report)
        history = db_ops.get_result_history(email, test_key)
        percentile = db_ops.get_test_percentile(email, test_key)
        logger.info(f"RESULT VIEW: [{email}] {test_key} ({len(history)} attempt(s), "
                    f"percentile={'n/a' if not percentile else percentile['percentile']})")
        share_code = db_ops.ensure_comm_share_code(email, test_key)
        certificate_url = (url_for('users.comm_certificate', code=share_code, _external=True)
                           if share_code else None)
        return render_template('users/exam_platform/placement_exam_portal/communication_portal/test_result.html',
                               report=report, guide=guide, completed_at=completed_at,
                               certificate_url=certificate_url,
                               history=history, percentile=percentile,
                               email=email, username=session.get('user_username', ''),
                               test_key=test_key, round_name=round_name,
                               course_code=course_code, unique_code=unique_code)
    except Exception:
        logger.exception(f"RESULT VIEW FAILED: {test_key}")
        return render_template('error_500.html'), 500

@users_bp.route('/<round_name>/result-section/<test_key>/<int:index>/<course_code>/<unique_code>')
@comm_login_required
def result_section(test_key, round_name, index, course_code, unique_code):
    try:
        email, _, authenticated = get_user_session()
        if not authenticated or not email:
            return redirect(url_for('users.user_login'))
        if db_ops.get_user_test_status(email, test_key) != 'completed':
            logger.warning(f"COMM RESULT SECTION BLOCKED: [{email}] {test_key} not completed")
            return redirect(url_for('users.round_assessments', round_name=round_name,
                                    course_code=course_code, unique_code=unique_code))
        detail = db_ops.get_section_detail(email, test_key, index)
        if not detail:
            return redirect(url_for('users.get_test_result', test_key=test_key, round_name=round_name,
                                    course_code=course_code, unique_code=unique_code))
        return render_template('users/exam_platform/placement_exam_portal/communication_portal/result_section.html',
                               detail=detail, email=email, username=session.get('user_username', ''),
                               test_key=test_key, round_name=round_name,
                               course_code=course_code, unique_code=unique_code)
    except Exception:
        logger.exception(f"RESULT SECTION FAILED: {test_key} idx={index}")
        return render_template('error_500.html'), 500


@users_bp.route('/api/expire-result', methods=['POST'])
@comm_login_required
def expire_result():
    try:
        data = request.json; email = data.get('email'); test_key = data.get('test_key'); session_email, _, _ = get_user_session()
        if session_email != email: return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
        db_ops.cleanup_user_data(email, test_key); return jsonify({"status": "deleted"})
    except Exception:
        logger.exception("EXPIRE RESULT FAILED")
        return jsonify({"status": "error", "message": "Could not clear the result."}), 500

TAB_STALE_SECONDS = 25


@users_bp.route('/api/comm-claim/<test_key>', methods=['POST'])
def comm_claim(test_key):
    try:
        email, _, _ = get_user_session()
        data = request.get_json(silent=True) or {}
        tab_id = (data.get('tab_id') or '')[:64]
        if not email or not tab_id:
            return jsonify({'ok': True, 'reason': 'no_session'})

        with _db(dictionary=True) as (conn, cursor):
            cursor.execute("""
                SELECT tab_id, status,
                       TIMESTAMPDIFF(SECOND, COALESCE(last_heartbeat, start_time), NOW()) AS age
                FROM comm_user_log
                WHERE email = %s AND test_key = %s
            """, (email, test_key))
            row = cursor.fetchone()

            if row and row['status'] == 'started' and row['tab_id'] and row['tab_id'] != tab_id \
                    and row['age'] is not None and row['age'] < TAB_STALE_SECONDS:
                logger.warning(f"COMM TAB BLOCKED: [{email}] test {test_key} already open in another tab "
                               f"(holder={row['tab_id'][:8]}, age={row['age']}s)")
                return jsonify({'ok': False,
                                'message': 'This assessment is already open in another tab or window. '
                                           'Continue there, or close it and wait a few seconds.'})

            cursor2 = conn.cursor()
            try:
                cursor2.execute("""
                    UPDATE comm_user_log SET tab_id = %s, last_heartbeat = NOW()
                    WHERE email = %s AND test_key = %s AND status = 'started'
                """, (tab_id, email, test_key))
                conn.commit()
            finally:
                cursor2.close()
        return jsonify({'ok': True})
    except Exception:
        logger.exception(f"COMM CLAIM FAILED for {test_key}")
        return jsonify({'ok': True, 'reason': 'error'})


@users_bp.route('/<round_name>/assessment_busy/<test_key>/<course_code>/<unique_code>')
@comm_login_required
def assessment_busy(test_key, round_name, course_code, unique_code):
    email, _, _ = get_user_session()
    logger.warning(f"COMM TAB BUSY: [{email}] test {test_key} opened in a second tab")
    flash("This test is already open in another tab. Close it, then proceed.", 'test_error')
    return redirect(url_for('users.round_assessments', round_name=round_name,
                            course_code=course_code, unique_code=unique_code))


@users_bp.route('/api/comm-tab-release/<test_key>', methods=['POST'])
def comm_tab_release(test_key):
    try:
        email, _, _ = get_user_session()
        data = request.get_json(silent=True, force=True) or {}
        tab_id = (data.get('tab_id') or '')[:64]
        if not email or not tab_id:
            return jsonify({'status': 'ignored'})
        with _db() as (conn, cursor):
            cursor.execute("""
                UPDATE comm_user_log
                SET tab_id = NULL, last_heartbeat = NOW() - INTERVAL 120 SECOND
                WHERE email = %s AND test_key = %s AND tab_id = %s AND status = 'started'
            """, (email, test_key, tab_id))
            released = cursor.rowcount
            conn.commit()
        if released:
            logger.info(f"COMM TAB RELEASE: [{email}] window closed for test {test_key} — session aged for instant handover")
        return jsonify({'status': 'released' if released else 'noop'})
    except Exception:
        logger.exception(f"COMM TAB RELEASE FAILED for {test_key}")
        return jsonify({'status': 'error'}), 200


@users_bp.route('/api/comm-window-closed/<test_key>', methods=['POST'])
def comm_window_closed(test_key):
    """The exam window was genuinely closed (not internal navigation).

    The attempt stays 'started' so the dashboard still offers Resume, but the
    heartbeat is aged so any other test can be opened immediately and the tab
    claim is dropped.
    """
    try:
        email, _, _ = get_user_session()
        if not email:
            return jsonify({'status': 'ignored'})
        with _db() as (conn, cursor):
            cursor.execute("""
                UPDATE comm_user_log
                SET tab_id = NULL, last_heartbeat = NOW() - INTERVAL 120 SECOND
                WHERE email = %s AND test_key = %s AND status = 'started'
            """, (email, test_key))
            released = cursor.rowcount
            conn.commit()
        if released:
            logger.info(f"COMM WINDOW CLOSED: [{email}] released {test_key} — resumable, other tests unblocked")
        return jsonify({'status': 'released' if released else 'noop'})
    except Exception:
        logger.exception(f"COMM WINDOW CLOSED FAILED for {test_key}")
        return jsonify({'status': 'error'}), 200


@users_bp.route('/api/comm-terminate/<test_key>', methods=['POST'])
@comm_csrf_protect
def comm_terminate(test_key):
    try:
        email, _, _ = get_user_session()
        if not email:
            return jsonify({'status': 'ignored'}), 200
        data = request.get_json(silent=True) or {}
        reason = (data.get('reason') or 'left_exam_window')[:60]
        course_code = session.get('course_code') or ''
        unique_code = session.get('unique_code') or ''
        with _db() as (conn, cursor):
            cursor.execute("""
                UPDATE comm_user_log
                SET session_token = NULL, tab_id = NULL, end_time = NOW()
                WHERE email = %s AND test_key = %s AND status = 'started'
            """, (email, test_key))
            conn.commit()
        session.pop('active_test_token', None)
        round_name = db_ops.get_round_for_test_key(test_key) or 'Communication'
        logger.warning(f"COMM LEFT WINDOW: [{email}] test {test_key} ({reason}) - resumable")
        return jsonify({
            'status': 'terminated',
            'redirect': url_for('users.assessment_terminated', test_key=test_key, round_name=round_name,
                                course_code=course_code, unique_code=unique_code, violation_type=reason)
        })
    except Exception:
        logger.exception(f"COMM TERMINATE FAILED for {test_key}")
        return jsonify({'status': 'error'}), 200


@users_bp.route('/comm/certificate/<code>')
def comm_certificate(code):
    import re as _re
    if not _re.match(r'^[A-Za-z0-9_-]{8,32}$', code or ''):
        abort(404)
    cert = db_ops.get_comm_certificate(code)
    if not cert:
        abort(404)
    pct = int(round(cert['percentage'] or 0))
    return render_template(
        'users/exam_platform/placement_exam_portal/communication_portal/comm_certificate.html',
        cert=cert, pct=pct)


@users_bp.route('/<round_name>/assessment_terminated/<test_key>/<course_code>/<unique_code>')
@comm_login_required
def assessment_terminated(test_key, round_name, course_code, unique_code):
    email, _, _ = get_user_session()
    violation_type = request.args.get('violation_type', 'left_exam_window')
    session.pop('active_test_token', None)
    session.modified = True
    logger.warning(f"COMM TERMINATED PAGE: [{email}] {test_key} ({violation_type})")
    return render_template(
        'users/exam_platform/placement_exam_portal/communication_portal/comm_termination.html',
        test_key=test_key, course_code=course_code, unique_code=unique_code,
        violation_type=violation_type,
        resume_url=url_for('users.assessment_system_info', test_key=test_key,
                           round_name=round_name, course_code=course_code,
                           unique_code=unique_code),
        dashboard_url=url_for('users.round_assessments', round_name=round_name,
                              course_code=course_code, unique_code=unique_code))


@users_bp.route('/api/comm-release/<test_key>', methods=['POST'])
def comm_release(test_key):
    try:
        email, _, _ = get_user_session()
        token = session.get('active_test_token')
        if not email or not token or not db_ops.validate_token(email, test_key, token):
            return jsonify({"status": "ignored"}), 200
        with _db() as (conn, cursor):
            cursor.execute("""
                UPDATE comm_user_log SET session_token = NULL
                WHERE email = %s AND test_key = %s AND status = 'started'
            """, (email, test_key))
            released = cursor.rowcount
            conn.commit()
        if released:
            session.pop('active_test_token', None)
            logger.info(f"COMM RELEASE: [{email}] window closed, released test {test_key}")
        return jsonify({"status": "released" if released else "noop"})
    except Exception:
        logger.exception(f"COMM RELEASE FAILED for {test_key}")
        return jsonify({"status": "error"}), 500


@users_bp.route('/api/comm-heartbeat/<test_key>', methods=['POST'])
def comm_heartbeat(test_key):
    try:
        email, _, _ = get_user_session()
        token = session.get('active_test_token')
        if not token or not db_ops.validate_token(email, test_key, token):
            return jsonify({"status": "invalid"}), 403
        with _db() as (conn, cursor):
            cursor.execute("""
                UPDATE comm_user_log SET last_heartbeat = NOW()
                WHERE email = %s AND test_key = %s AND status = 'started'
            """, (email, test_key))
            conn.commit()
        return jsonify({"status": "ok"})
    except Exception:
        logger.exception(f"COMM HEARTBEAT FAILED for {test_key}")
        return jsonify({"status": "error"}), 500


@users_bp.route('/api/network-check', methods=['GET'])
def network_check():
    resp = make_response(jsonify({"status": "ok", "timestamp": time.time()}))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'; resp.headers['Pragma'] = 'no-cache'; return resp

@socketio.on('join_exam')
def on_join(data):
    try:
        email = session.get('user_email')
        if not email or str(email).startswith('guest_'):
            return
        if not isinstance(data, dict):
            return
        room = str(data.get('session_id') or '')[:80]
        if not room:
            return
        token = session.get('active_test_token')
        if not token or not db_ops.validate_token(email, room, token):
            logger.warning("SOCKET JOIN REFUSED: [%s] no active session for %s", email, room)
            return
        join_room(room)
        emit('status', {'msg': 'Connected'}, room=room)
    except Exception:
        logger.exception("SOCKET JOIN FAILED")


@socketio.on_error_default
def _socket_error(e):
    logger.exception("SOCKETIO ERROR: %s", e)