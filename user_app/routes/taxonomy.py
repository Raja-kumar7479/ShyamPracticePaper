import logging
import threading
import time

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60

_lock = threading.Lock()
_cache = {'at': 0.0, 'data': None}

LEGACY_ALIASES = {
    'mock test': 'mock_test', 'mocktest': 'mock_test', 'mock tests': 'mock_test',
    'hnotes': 'notes', 'handwritten notes': 'notes',
    'vlecture': 'lecture', 'lectures': 'lecture',
    'jcommunity': 'community',
}

_EMPTY = {}


def _load():
    from routes.db_pool import get_connection
    conn = cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT section_key, label, portal, is_available FROM content_sections")
        return {r['section_key']: {'label': r['label'], 'portal': r['portal'],
                                   'available': bool(r['is_available'])}
                for r in cur.fetchall()}
    finally:
        if cur: cur.close()
        if conn: conn.close()


def catalog(force=False):
    now = time.time()
    with _lock:
        fresh = _cache['data'] is not None and (now - _cache['at']) < CACHE_TTL_SECONDS
        if fresh and not force:
            return _cache['data']
    try:
        data = _load()
    except Exception:
        logger.exception('TAXONOMY: could not read the section catalog')
        with _lock:
            return _cache['data'] or _EMPTY
    with _lock:
        _cache['data'] = data
        _cache['at'] = now
    return data


def refresh():
    return catalog(force=True)


def normalize(section):
    raw = (section or '').strip()
    if raw in catalog():
        return raw
    return LEGACY_ALIASES.get(raw.lower().replace('_', ' ').replace('-', ' '), raw.lower())


def portal_for(section):
    meta = catalog().get(normalize(section))
    return meta['portal'] if meta else None


def label_for(section):
    key = normalize(section)
    meta = catalog().get(key)
    return meta['label'] if meta else key.replace('_', ' ').title()


def is_available(section):
    meta = catalog().get(normalize(section))
    return bool(meta and meta['available'])


def is_test_section(section):
    return portal_for(section) in ('competitive', 'coding', 'communication', 'tcs')


MATERIAL_PORTALS = {'notes', 'lecture', 'blog', 'community'}
PRACTICE_PORTALS = {'competitive', 'coding', 'coding_practice', 'communication', 'tcs'}
PRACTICE_SECTIONS = {'aptitude_test', 'question_practice'}


def group_for(section):
    key = normalize(section)
    portal = portal_for(key)
    if portal in MATERIAL_PORTALS:
        return 'materials'
    if portal in PRACTICE_PORTALS or key in PRACTICE_SECTIONS:
        return 'practice'
    return 'materials'


def is_practice_section(section):
    return group_for(section) == 'practice'


def opens_in_new_window(section):
    return portal_for(section) in ('competitive', 'coding', 'communication', 'tcs')


def open_url(section, section_id, course_code, unique_code, title=None):
    from flask import url_for

    portal = portal_for(section)

    if portal == 'competitive':
        if not section_id:
            return None
        return url_for('users.open_mock_test_section', section_id=section_id,
                       course_code=course_code, unique_code=unique_code)

    if portal == 'communication':
        return url_for('users.round_assessments', round_name='Communication',
                       course_code=course_code, unique_code=unique_code)

    if portal == 'coding':
        return url_for('coding_test.dashboard', course_code=course_code,
                       unique_code=unique_code, section_id=section_id)

    if portal == 'tcs':
        if not section_id:
            return None
        return url_for('tcs.dashboard', course_code=course_code,
                       unique_code=unique_code, section_id=section_id)

    if portal == 'coding_practice':
        return url_for('practice_coding.home', course_code=course_code,
                       unique_code=unique_code)

    if portal == 'notes':
        if not section_id:
            return None
        return url_for('users.open_hnotes_section', section_id=section_id,
                       course_code=course_code, unique_code=unique_code)

    if normalize(section) in catalog():
        return url_for('users.round_coming_soon', round_name=label_for(section),
                       course_code=course_code, unique_code=unique_code)
    return None
