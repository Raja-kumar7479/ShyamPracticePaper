import hashlib
import logging
import os
import tempfile
import threading

from admin.db_pool import get_connection
from config import Config

logger = logging.getLogger(__name__)

CHUNK_BYTES = 1024 * 1024


def _root():
    return os.path.realpath(Config.UPLOAD_BASE)


def _relative(full_path):
    root = _root()
    real = os.path.realpath(full_path)
    if real == root or not real.startswith(root + os.sep):
        return None
    return os.path.relpath(real, root).replace(os.sep, '/')


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
    root = _root()
    full = os.path.realpath(os.path.join(root, *clean.split('/')))
    if full != root and not full.startswith(root + os.sep):
        return None
    return full


def publish(full_path):
    relative = _relative(full_path)
    if not relative or not os.path.isfile(full_path):
        return False
    conn = None
    cur = None
    try:
        with open(full_path, 'rb') as fh:
            data = fh.read()
        digest = hashlib.sha256(data).hexdigest()
        parts = [data[i:i + CHUNK_BYTES] for i in range(0, len(data), CHUNK_BYTES)]
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM shared_file_chunks WHERE path = %s", (relative,))
        for seq, part in enumerate(parts):
            cur.execute("INSERT INTO shared_file_chunks (path, seq, data) VALUES (%s, %s, %s)", (relative, seq, part))
        cur.execute(
            "INSERT INTO shared_files (path, size, sha256, chunks) VALUES (%s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE size = VALUES(size), sha256 = VALUES(sha256), chunks = VALUES(chunks), updated_at = NOW()",
            (relative, len(data), digest, len(parts)))
        conn.commit()
        logger.info("SHARED FILES: published %s (%d bytes)", relative, len(data))
        return True
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.exception("SHARED FILES: could not publish %s", relative)
        return False
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


def remove(full_path):
    relative = _relative(full_path)
    if not relative:
        return False
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM shared_file_chunks WHERE path = %s", (relative,))
        cur.execute("DELETE FROM shared_files WHERE path = %s", (relative,))
        conn.commit()
        return True
    except Exception:
        logger.exception("SHARED FILES: could not remove %s", relative)
        return False
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


def ensure_local(relative):
    clean = _clean(relative)
    full = local_path(relative)
    if not clean or not full:
        return None
    if os.path.isfile(full):
        return full
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT size, chunks FROM shared_files WHERE path = %s", (clean,))
        head = cur.fetchone()
        if not head:
            return None
        os.makedirs(os.path.dirname(full), exist_ok=True)
        handle, temp = tempfile.mkstemp(dir=os.path.dirname(full), prefix='.incoming_')
        try:
            with os.fdopen(handle, 'wb') as out:
                for seq in range(int(head[1] or 0)):
                    cur.execute("SELECT data FROM shared_file_chunks WHERE path = %s AND seq = %s", (clean, seq))
                    row = cur.fetchone()
                    if not row:
                        raise IOError('part %d of %s is missing' % (seq, clean))
                    out.write(row[0])
            os.replace(temp, full)
        except Exception:
            try:
                os.remove(temp)
            except OSError:
                pass
            raise
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


def publish_missing():
    root = _root()
    if not os.path.isdir(root):
        return 0
    known = {}
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT path, size FROM shared_files")
        known = {row[0]: int(row[1]) for row in cur.fetchall()}
    except Exception:
        logger.exception("SHARED FILES: could not read the list of published files")
        return 0
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
    sent = 0
    for folder, _, names in os.walk(root):
        for name in names:
            if name.startswith('.'):
                continue
            full = os.path.join(folder, name)
            relative = _relative(full)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            if relative and known.get(relative) != size and publish(full):
                sent += 1
    if sent:
        logger.info("SHARED FILES: published %d file(s) that were only on this server", sent)
    return sent


def start_publisher():
    thread = threading.Thread(target=publish_missing, name='shared-files-publisher', daemon=True)
    thread.start()
    return thread
