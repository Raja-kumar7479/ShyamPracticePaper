import logging
import time
from flask import jsonify, request, session
from routes import users_bp

logger = logging.getLogger(__name__)

CLAIM_KEY = 'exam_window_claims'
CLAIM_STALE_SECONDS = 20


@users_bp.route('/api/exam-window/claim', methods=['POST'])
def exam_window_claim():
    data = request.get_json(silent=True) or {}
    test_key = (data.get('test_key') or '')[:120]
    tab_id = (data.get('tab_id') or '')[:64]
    if not test_key or not tab_id:
        return jsonify({'ok': True, 'reason': 'incomplete'})

    now = time.time()
    claims = session.get(CLAIM_KEY) or {}
    claims = {k: v for k, v in claims.items()
              if isinstance(v, dict) and (now - v.get('ts', 0)) < CLAIM_STALE_SECONDS}

    holder = claims.get(test_key)
    if holder and holder.get('tab') != tab_id:
        who = session.get('user_email', 'anonymous')
        # A newly opened window takes the claim over rather than being turned
        # away: the release beacon of a closed window is not reliable (it can
        # be lost, or overwritten by a racing request under cookie sessions),
        # and a dead holder must never lock the candidate out of their own
        # test. If the old window is genuinely still open, its next heartbeat
        # loses the claim and it closes itself - the newest window wins, so
        # only one window ever stays alive.
        if data.get('fresh'):
            logger.info(f"EXAM WINDOW TAKEOVER: [{who}] test {test_key} claimed by a new window "
                        f"(old holder={str(holder.get('tab'))[:8]})")
        else:
            session[CLAIM_KEY] = claims
            session.modified = True
            logger.warning(f"EXAM WINDOW BLOCKED: [{who}] test {test_key} already open in another window "
                           f"(holder={str(holder.get('tab'))[:8]})")
            return jsonify({'ok': False,
                            'message': 'This test is already open in another window. Continue there.'})

    claims[test_key] = {'tab': tab_id, 'ts': now}
    session[CLAIM_KEY] = claims
    session.modified = True
    return jsonify({'ok': True})


@users_bp.route('/api/exam-window/release', methods=['POST'])
def exam_window_release():
    data = request.get_json(silent=True) or {}
    test_key = (data.get('test_key') or '')[:120]
    tab_id = (data.get('tab_id') or '')[:64]
    claims = session.get(CLAIM_KEY) or {}
    holder = claims.get(test_key)
    if holder and holder.get('tab') == tab_id:
        claims.pop(test_key, None)
        session[CLAIM_KEY] = claims
        session.modified = True
    return jsonify({'ok': True})
