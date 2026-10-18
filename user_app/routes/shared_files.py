import logging
import os
import tempfile
import time

from config import Config
from routes.db_pool import get_connection

logger = logging.getLogger(__name__)

MISS_SECONDS = 60
_missing = {}


def _clean(relative):
    text = str(relative or '').replace('\\', '/').lstrip('/')
    parts = [p for p in text.split('/') if p not in ('', '.')]
    if not parts or any(p == '..' for p in parts):
        return None
    return '/'.join(parts)


def local_path(relative):
    clean = _clean(relative)
    if not clean:
        return None
    root = os.path.realpath(Config.UPLOAD_BASE)
    full = os.path.realpath(os.path.join(root, *clean.split('/')))
    if full != root and not full.startswith(root + os.sep):
        return None
    return full


def ensure_local(relative):
    clean = _clean(relative)
    full = local_path(relative)
    if not clean or not full:
        return None
    if os.path.isfile(full):
        return full
    now = time.monotonic()
    if _missing.get(clean, 0) > now:
        return None
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT size, chunks FROM shared_files WHERE path = %s", (clean,))
        head = cur.fetchone()
        if not head:
            if len(_missing) > 5000:
                _missing.clear()
            _missing[clean] = now + MISS_SECONDS
            return None
        os.makedirs(os.path.dirname(full), exist_ok=True)
        handle, temp = tempfile.mkstemp(dir=os.path.dirname(full), prefix='.incoming_')
        written = 0
        try:
            with os.fdopen(handle, 'wb') as out:
                for seq in range(int(head[1] or 0)):
                    cur.execute("SELECT data FROM shared_file_chunks WHERE path = %s AND seq = %s", (clean, seq))
                    row = cur.fetchone()
                    if not row:
                        raise IOError('part %d of %s is missing' % (seq, clean))
                    out.write(row[0])
                    written += len(row[0])
            if written != int(head[0] or 0):
                raise IOError('%s is incomplete (%d of %d bytes)' % (clean, written, int(head[0] or 0)))
            os.replace(temp, full)
        except Exception:
            try:
                os.remove(temp)
            except OSError:
                pass
            raise
        logger.info("SHARED FILES: copied %s from the database (%d bytes)", clean, written)
        return full
    except Exception:
        logger.exception("SHARED FILES: could not load %s from the database", clean)
        return None
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass
