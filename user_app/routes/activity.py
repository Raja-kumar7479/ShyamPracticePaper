import threading
import time

_INTERVAL = 120.0
_MAX_ENTRIES = 200000
_seen = {}
_lock = threading.Lock()


def should_touch(email, interval=_INTERVAL):
    if not email:
        return False
    now = time.monotonic()
    with _lock:
        last = _seen.get(email)
        if last is not None and now - last < interval:
            return False
        if len(_seen) >= _MAX_ENTRIES:
            cutoff = now - interval
            for key in [k for k, v in _seen.items() if v < cutoff]:
                _seen.pop(key, None)
            if len(_seen) >= _MAX_ENTRIES:
                _seen.clear()
        _seen[email] = now
        return True
