import json
import logging
import os
import time
import uuid

from extensions import redis_pool

logger = logging.getLogger(__name__)

JOBS = 'spp:judge:jobs'
RESULT = 'spp:judge:res:'
USER = 'spp:judge:user:'
WORKERS = 'spp:judge:workers'
MODE = (os.environ.get('JUDGE_MODE') or 'local').strip().lower()


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


MAX_QUEUE = max(1, _env_int('JUDGE_QUEUE_MAX', 500))
QUEUE_WAIT = max(1, _env_int('JUDGE_QUEUE_WAIT', 25))
WORKER_ALIVE_SECONDS = 30


def enabled():
    return MODE == 'queue' and redis_pool is not None


def client():
    import redis
    return redis.Redis(connection_pool=redis_pool)


def live_workers(r=None):
    r = r or client()
    now = time.time()
    try:
        r.zremrangebyscore(WORKERS, 0, now - WORKER_ALIVE_SECONDS)
        return int(r.zcard(WORKERS))
    except Exception:
        return 0


def stats():
    r = client()
    return {
        'mode': 'queue',
        'waiting': int(r.llen(JOBS)),
        'max_waiting': MAX_QUEUE,
        'queue_wait_seconds': QUEUE_WAIT,
        'judge_workers': live_workers(r),
    }


def run_remote(kind, payload, run_budget, user_key=None):
    r = client()
    lock_key = USER + str(user_key) if user_key else None
    if lock_key and not r.set(lock_key, '1', nx=True, ex=int(QUEUE_WAIT + run_budget + 15)):
        return {'busy': 'Your previous run is still being judged. Wait for its result before running again.'}
    try:
        waiting = int(r.llen(JOBS))
        if waiting >= MAX_QUEUE:
            return {'busy': f'The judge is busy right now ({waiting} runs ahead of you). Please try again in a few seconds.'}
        if live_workers(r) == 0:
            logger.error("JUDGE QUEUE: no judge worker is running")
            return {'busy': 'The code judge is not available right now. Your code was not run - please try again shortly.'}
        job_id = uuid.uuid4().hex
        job = json.dumps({'id': job_id, 'kind': kind, 'payload': payload,
                          'queued_at': time.time(), 'max_wait': QUEUE_WAIT})
        r.rpush(JOBS, job)
        queued = time.monotonic()
        deadline = queued + QUEUE_WAIT + run_budget + 5
        picked = False
        delay = 0.05
        key = RESULT + job_id
        while time.monotonic() < deadline:
            raw = r.lpop(key)
            if raw:
                return json.loads(raw)
            if not picked and time.monotonic() - queued > QUEUE_WAIT:
                if r.lrem(JOBS, 1, job):
                    return {'busy': 'The judge is busy right now. Your code was not run - please try again in a few seconds.'}
                picked = True
            time.sleep(delay)
            delay = min(delay * 1.3, 0.25)
        logger.warning("JUDGE QUEUE: no result for job %s within the deadline", job_id)
        return {'busy': 'The judge did not answer in time. Your code was not run - please try again in a few seconds.'}
    finally:
        if lock_key:
            try:
                r.delete(lock_key)
            except Exception:
                pass


def result_to_dict(result):
    return {
        'compiled': bool(result.compiled),
        'error': result.error or '',
        'cases': [{'status': c.status, 'output': c.output, 'error': c.error, 'execution_time': c.execution_time}
                  for c in (result.cases or [])],
    }


def dict_to_result(data, run_result_cls, case_result_cls):
    if 'busy' in data:
        return run_result_cls(compiled=True, error=data['busy'])
    cases = [case_result_cls(c.get('status', 'FAIL'), c.get('output', ''), c.get('error', ''), c.get('execution_time', 0.0))
             for c in data.get('cases') or []]
    return run_result_cls(compiled=bool(data.get('compiled', True)), error=data.get('error') or '', cases=cases)
