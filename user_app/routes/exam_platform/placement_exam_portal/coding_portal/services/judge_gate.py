import os
import threading
import time
import logging

logger = logging.getLogger(__name__)


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


WORKERS = max(1, _env_int('WEB_CONCURRENCY', 1))
TOTAL_PARALLEL = max(1, _env_int('JUDGE_MAX_PARALLEL', max(2, (os.cpu_count() or 2) // 2)))
MAX_PARALLEL = max(1, TOTAL_PARALLEL // WORKERS)
MAX_WAITING = max(0, _env_int('JUDGE_MAX_WAITING', MAX_PARALLEL * 4))
QUEUE_WAIT_SECONDS = max(1, _env_int('JUDGE_QUEUE_WAIT', 25))


class JudgeBusy(Exception):
    def __init__(self, message, waiting):
        super().__init__(message)
        self.waiting = waiting


class JudgeGate:
    def __init__(self, max_parallel, max_waiting, queue_wait):
        self.max_parallel = max_parallel
        self.max_waiting = max_waiting
        self.queue_wait = queue_wait
        self._slots = threading.BoundedSemaphore(max_parallel)
        self._lock = threading.Lock()
        self._active_users = set()
        self.running = 0
        self.waiting = 0
        self.peak_running = 0
        self.peak_waiting = 0
        self.completed = 0
        self.rejected_busy = 0
        self.rejected_duplicate = 0
        self.total_wait_seconds = 0.0

    def acquire(self, user_key=None):
        with self._lock:
            if user_key and user_key in self._active_users:
                self.rejected_duplicate += 1
                raise JudgeBusy('Your previous run is still being judged. Wait for its result before running again.', self.waiting)
            if self.waiting >= self.max_waiting:
                self.rejected_busy += 1
                raise JudgeBusy(f'The judge is busy right now ({self.waiting} runs ahead of you). Please try again in a few seconds.', self.waiting)
            self.waiting += 1
            self.peak_waiting = max(self.peak_waiting, self.waiting)
            if user_key:
                self._active_users.add(user_key)
        started = time.monotonic()
        got = self._slots.acquire(timeout=self.queue_wait)
        waited = time.monotonic() - started
        with self._lock:
            self.waiting -= 1
            if not got:
                self.rejected_busy += 1
                if user_key:
                    self._active_users.discard(user_key)
                raise JudgeBusy('The judge is busy right now. Your code was not run - please try again in a few seconds.', self.waiting)
            self.running += 1
            self.peak_running = max(self.peak_running, self.running)
            self.total_wait_seconds += waited
        if waited > 1:
            logger.info("JUDGE GATE: waited %.1fs for a slot (running=%d waiting=%d)", waited, self.running, self.waiting)
        return user_key

    def release(self, user_key=None):
        with self._lock:
            self.running = max(0, self.running - 1)
            self.completed += 1
            if user_key:
                self._active_users.discard(user_key)
        self._slots.release()

    def stats(self):
        with self._lock:
            done = max(1, self.completed)
            return {
                'workers': WORKERS,
                'max_parallel_all_workers': TOTAL_PARALLEL,
                'max_parallel': self.max_parallel,
                'max_waiting': self.max_waiting,
                'queue_wait_seconds': self.queue_wait,
                'running': self.running,
                'waiting': self.waiting,
                'peak_running': self.peak_running,
                'peak_waiting': self.peak_waiting,
                'completed': self.completed,
                'rejected_busy': self.rejected_busy,
                'rejected_duplicate': self.rejected_duplicate,
                'avg_wait_seconds': round(self.total_wait_seconds / done, 3),
            }


gate = JudgeGate(MAX_PARALLEL, MAX_WAITING, QUEUE_WAIT_SECONDS)


def current_user_key():
    try:
        from flask import has_request_context, session
        if has_request_context():
            return session.get('user_email') or session.get('pcp_user_id') or None
    except Exception:
        return None
    return None
