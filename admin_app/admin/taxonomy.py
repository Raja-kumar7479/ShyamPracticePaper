import logging
import threading
import time

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60

_lock = threading.Lock()
_cache = {'at': 0.0, 'data': None}

_EMPTY = {'groups': [], 'group_codes': {}, 'platforms': {}, 'sections': {}, 'group_sections': {}}
PLACEMENT_ONLY_PORTALS = ('coding', 'communication', 'tcs', 'coding_practice')


def _load():
    from admin.db_pool import get_connection
    conn = cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)

        cur.execute("SELECT group_name, label, platform FROM course_groups "
                    "WHERE is_active = 1 ORDER BY position, group_name")
        group_rows = cur.fetchall()
        groups = [r['group_name'] for r in group_rows]
        platforms = {r['group_name']: (r.get('platform') or 'competitive') for r in group_rows}

        cur.execute("SELECT group_name, code FROM course_group_codes ORDER BY position, code")
        group_codes = {}
        for row in cur.fetchall():
            group_codes.setdefault(row['group_name'], []).append(row['code'])

        cur.execute("SELECT section_key, label, help_text, portal, editor, is_available "
                    "FROM content_sections ORDER BY position, section_key")
        sections = {}
        for row in cur.fetchall():
            sections[row['section_key']] = {
                'value': row['section_key'],
                'label': row['label'],
                'help': row['help_text'] or '',
                'portal': row['portal'],
                'editor': row['editor'],
                'available': bool(row['is_available']),
            }

        cur.execute("SELECT group_name, section_key FROM course_group_sections "
                    "ORDER BY position, section_key")
        group_sections = {}
        for row in cur.fetchall():
            group_sections.setdefault(row['group_name'], []).append(row['section_key'])

        return {'groups': groups, 'group_codes': group_codes, 'platforms': platforms,
                'sections': sections, 'group_sections': group_sections}
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
        logger.exception('TAXONOMY: could not read the catalog')
        with _lock:
            return _cache['data'] or _EMPTY
    with _lock:
        _cache['data'] = data
        _cache['at'] = now
    return data


def refresh():
    return catalog(force=True)


def _norm_group(group):
    return (group or '').strip().upper()


def groups():
    return catalog()['groups']


def codes_for_group(group):
    return catalog()['group_codes'].get(_norm_group(group), [])


def group_codes_map():
    return catalog()['group_codes']


def is_valid_group(group):
    return _norm_group(group) in catalog()['groups']


def is_valid_pair(group, code):
    return (code or '').strip().upper() in codes_for_group(group)


def platform_for(group):
    return catalog()['platforms'].get(_norm_group(group), 'competitive')


def section_allowed_for_group(group, section):
    meta = section_meta(section)
    if meta and meta['portal'] in PLACEMENT_ONLY_PORTALS and platform_for(group) != 'placement':
        return False
    return True


def sections_for_group(group):
    return [k for k in catalog()['group_sections'].get(_norm_group(group), []) if section_allowed_for_group(group, k)]


def section_meta(section):
    return catalog()['sections'].get((section or '').strip())


def is_valid_section(group, section):
    return (section or '').strip() in sections_for_group(group)


def label_for(section):
    meta = section_meta(section)
    return meta['label'] if meta else (section or '')


def editor_for(section):
    meta = section_meta(section)
    return meta['editor'] if meta else None


def portal_for(section):
    meta = section_meta(section)
    return meta['portal'] if meta else None


def is_available(section):
    meta = section_meta(section)
    return bool(meta and meta['available'])


def section_options(group):
    sections = catalog()['sections']
    return [sections[key] for key in sections_for_group(group) if key in sections]


def test_sections():
    return [key for key, meta in catalog()['sections'].items() if meta['editor']]
