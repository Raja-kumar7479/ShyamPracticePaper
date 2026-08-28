"""Which portal a content section opens.

Placement routing used to guess the portal from the test title ("does the title
contain the word coding?"), so a badly named test opened the wrong portal or
none at all. The section value on the content row decides it instead.

The mapping is read from the content_sections catalog - the same rows the admin
app writes - so the two apps cannot disagree about where a section leads. The
old approach kept a copy of the rules in each app, which would drift the first
time someone added an exam type on one side only.
"""
import logging
import threading
import time

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60

_lock = threading.Lock()
_cache = {'at': 0.0, 'data': None}

# Spellings written before the catalog existed, so old rows still route.
LEGACY_ALIASES = {
    'mock test': 'mock_test', 'mocktest': 'mock_test', 'mock tests': 'mock_test',
    'hnotes': 'notes', 'handwritten notes': 'notes',
    'vlecture': 'lecture', 'lectures': 'lecture',
    'jcommunity': 'community',
}

# Used only if the catalog cannot be read, so a database blip degrades to
# "no link shown" rather than a crashed dashboard.
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
    """Maps any historical spelling onto a current section value."""
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


# Which dashboard tab a content row belongs under. The dashboard used to file
# every content row under Study Materials and treat "Practice" as nothing but
# the legacy practice_questions browse modes, so a course whose only resources
# were a coding practice bank and two rounds showed an empty Practice tab.
MATERIAL_PORTALS = {'notes', 'lecture', 'blog', 'community'}
PRACTICE_PORTALS = {'competitive', 'coding', 'coding_practice', 'communication', 'tcs'}
# Catalogued but with no portal built yet; they are still practice, not reading.
PRACTICE_SECTIONS = {'aptitude_test', 'question_practice'}


def group_for(section):
    """'practice' for anything a student attempts, 'materials' for anything they read."""
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
    """True only for the proctored exams, which want a window of their own.

    A test is sat in one dedicated window: the coding round ends the attempt if
    the candidate leaves it, and the assessment list reloads when that window
    closes. Everything else - practice, notes, lectures - is ordinary browsing
    and belongs in the tab the student already has open, so a new tab is not
    opened for every card on the dashboard.
    """
    return portal_for(section) in ('competitive', 'coding', 'communication', 'tcs')


def open_url(section, section_id, course_code, unique_code, title=None):
    """The link that opens one content item, or None when nothing can open it.

    Both the free-courses dashboard and the purchased dashboard call this, so
    the two can never drift apart on where a section sends a student.
    """
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
        # section_id scopes the coding dashboard to this content block, so the
        # student sees only the assessments they opened.
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

    # A known section whose portal is not built yet gets a page explaining
    # that, rather than a dead '#' link.
    if normalize(section) in catalog():
        return url_for('users.round_coming_soon', round_name=label_for(section),
                       course_code=course_code, unique_code=unique_code)
    return None
