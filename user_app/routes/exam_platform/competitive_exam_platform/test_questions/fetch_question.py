from flask import current_app, jsonify, render_template, request, session, redirect, url_for
from routes.exam_platform.competitive_exam_platform.databases.main_handler_db import UserOperation
from routes.exam_platform.competitive_exam_platform.utils.utils_test_dashboard import get_user_session
from routes.exam_platform.competitive_exam_platform.utils.utils_secure_code import secure_access_required
from routes.exam_platform.competitive_exam_platform.utils.utils_test_access import test_access_required
from routes import users_bp
import json
import logging
import time

user_op = UserOperation()
logger = logging.getLogger(__name__)
_PAPER_TTL = 30.0
_paper_cache = {}


def _parse_regions(raw):
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    clean = {}
    for key in ('a', 'b', 'c', 'd'):
        box = data.get(key)
        if not isinstance(box, dict):
            continue
        try:
            clean[key] = {k: float(box[k]) for k in ('x', 'y', 'w', 'h')}
        except (KeyError, TypeError, ValueError):
            continue
    return clean or None

def clean_html(html_content):
    if not html_content:
        return html_content
    html_content = html_content.strip()
    if html_content.startswith('<p>') and html_content.endswith('</p>'):
        inner_content = html_content[3:-4].strip()
        if '<p>' not in inner_content:
            return inner_content
    return html_content

@users_bp.route('/fetch-questions/<section_id>/<test_key>/<course_code>/<unique_code>', methods=['GET'])
@secure_access_required(('course_code', 'unique_code'))
@test_access_required
def fetch_questions(section_id, test_key, course_code, unique_code):
    user_email, user_username, user_is_authenticated = get_user_session()
    
    now = time.monotonic()
    cached = _paper_cache.get(test_key)
    if cached and now - cached[0] < _PAPER_TTL:
        return current_app.response_class(cached[1], mimetype='application/json')

    all_questions = user_op.get_all_test_questions(test_key)
    if not all_questions:
        return jsonify({"error": "No questions available for this test."}), 404

    processed_questions = []
    for q_idx, q in enumerate(all_questions):
        processed_questions.append({
            "id": q.get('id'),
            "test_id": q.get('test_id'),
            "section_id": q.get('section_id'),
            "section_name": q.get('section_name'),
            "question_number_in_section": q.get('question_number'),
            "overall_question_index": q_idx,
            "question_type": q.get('question_type'),
            "question_text": q.get('question_text'),
            "question_image": q.get('question_image'),
            "option_regions": _parse_regions(q.get('option_regions')),
            "options": {
                "a": clean_html(q.get('option_a')),
                "b": clean_html(q.get('option_b')),
                "c": clean_html(q.get('option_c')),
                "d": clean_html(q.get('option_d')),
            },
            "correct_marks": q.get('correct_marks'),
            "negative_marks": q.get('negative_marks'),
        })
    body = current_app.json.dumps(processed_questions)
    if len(_paper_cache) > 200:
        _paper_cache.clear()
    _paper_cache[test_key] = (now, body)
    return current_app.response_class(body, mimetype='application/json')


@users_bp.route('/api/test-flag/<test_key>', methods=['POST'])
def toggle_question_flag(test_key):
    email, _, authenticated = get_user_session()
    if not authenticated or not email:
        return jsonify({"success": False, "message": "Session expired."}), 401

    data = request.get_json(silent=True) or {}
    try:
        question_id = int(data.get('question_id'))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Invalid question."}), 400
    flagged = 1 if data.get('flagged') else 0
    note = (data.get('note') or '')[:255]

    try:
        attempt_number = session.get('current_test_attempt_number') or 1
        saved = user_op.set_question_flag(email, test_key, question_id, flagged, note, attempt_number)
        if not saved:
            return jsonify({"success": False, "message": "Could not save the flag."}), 500
        logger.info(f"FLAG: [{email}] test={test_key} q={question_id} flagged={flagged}")
        return jsonify({"success": True, "flagged": bool(flagged)})
    except Exception:
        logger.exception(f"FLAG FAILED: [{email}] test={test_key} q={data.get('question_id')}")
        return jsonify({"success": False, "message": "Could not save the flag."}), 500


@users_bp.route('/api/question-paper/<test_key>', methods=['GET'])
@test_access_required
def question_paper_data(test_key):
    email, username, authenticated = get_user_session()
    if not authenticated or not email:
        return jsonify({'error': 'Session expired.'}), 401

    status = (user_op.get_test_status_for_user(email, test_key) or {}).get('status')
    if status != 'in_progress':
        logger.warning(f"QUESTION PAPER BLOCKED: [{email}] status={status!r} for {test_key}")
        return jsonify({'error': 'This test is not running.'}), 403

    questions = user_op.get_all_test_questions(test_key) or []
    out = []
    for i, q in enumerate(questions, start=1):
        out.append({
            'serial': i,
            'section_name': q.get('section_name'),
            'question_type': q.get('question_type'),
            'question_text': q.get('question_text'),
            'question_image': q.get('question_image'),
            'option_a': clean_html(q.get('option_a')),
            'option_b': clean_html(q.get('option_b')),
            'option_c': clean_html(q.get('option_c')),
            'option_d': clean_html(q.get('option_d')),
            'correct_marks': q.get('correct_marks'),
            'negative_marks': q.get('negative_marks'),
        })
    logger.info(f"QUESTION PAPER: [{email}] loaded paper for {test_key} ({len(out)} question(s))")
    return jsonify({'questions': out})


@users_bp.route('/question-paper/<section_id>/<test_key>/<course_code>/<unique_code>', methods=['GET'])
@secure_access_required(('course_code', 'unique_code'))
@test_access_required
def question_paper(section_id, test_key, course_code, unique_code):
    email, username, authenticated = get_user_session()
    if not authenticated or not email:
        return redirect(url_for('users.user_login'))

    status = (user_op.get_test_status_for_user(email, test_key) or {}).get('status')
    if status != 'in_progress':
        logger.warning(f"QUESTION PAPER BLOCKED: [{email}] status={status!r} for {test_key}")
        return redirect(url_for('users.open_mock_test_section', section_id=section_id,
                                course_code=course_code, unique_code=unique_code))

    questions = user_op.get_all_test_questions(test_key) or []
    safe = []
    for i, q in enumerate(questions, start=1):
        safe.append({
            'serial': i,
            'section_name': q.get('section_name'),
            'question_number': q.get('question_number'),
            'question_type': q.get('question_type'),
            'question_text': q.get('question_text'),
            'question_image': q.get('question_image'),
            'option_a': clean_html(q.get('option_a')),
            'option_b': clean_html(q.get('option_b')),
            'option_c': clean_html(q.get('option_c')),
            'option_d': clean_html(q.get('option_d')),
            'correct_marks': q.get('correct_marks'),
            'negative_marks': q.get('negative_marks'),
        })
    test = user_op.get_test_details(test_key) or {}
    logger.info(f"QUESTION PAPER: [{email}] opened paper for {test_key} ({len(safe)} question(s))")
    return render_template(
        'users/exam_platform/competitive_exam_platform/test_window/question_paper.html',
        questions=safe, test=test, test_key=test_key, section_id=section_id,
        course_code=course_code, unique_code=unique_code)