import json
import logging
import os
import socket
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import redis

from config import Config
from routes.exam_platform.placement_exam_portal.coding_portal.services import code_executor as exam_executor
from routes.exam_platform.placement_exam_portal.coding_portal.services import docker_runner, judge_queue
from routes.exam_platform.placement_exam_portal.practice_coding.services import code_executor as practice_executor

logger = logging.getLogger('judge_worker')
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
PARALLEL = max(1, int(os.environ.get('JUDGE_MAX_PARALLEL', max(2, (os.cpu_count() or 2) // 2))))
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
WAIT_SECONDS = 5
_stop = threading.Event()


def _client():
    return redis.from_url(REDIS_URL, socket_timeout=WAIT_SECONDS + 10, socket_connect_timeout=5)


def _run(job):
    payload = job.get('payload') or {}
    executor = practice_executor if job.get('kind') == 'practice' else exam_executor
    result = executor._execute_now(
        payload.get('code') or '', payload.get('language'), payload.get('testcases') or [],
        payload.get('time_limit'), payload.get('memory_limit'),
        payload.get('compare_mode') or 'exact', payload.get('float_tolerance'))
    return judge_queue.result_to_dict(result)


def _loop(index):
    r = _client()
    while not _stop.is_set():
        try:
            item = r.blpop(judge_queue.JOBS, timeout=WAIT_SECONDS)
        except redis.exceptions.TimeoutError:
            continue
        except Exception:
            logger.exception("worker %s-%d lost redis; retrying", WORKER_ID, index)
            time.sleep(2)
            continue
        if not item:
            continue
        try:
            job = json.loads(item[1])
        except ValueError:
            continue
        if time.time() - float(job.get('queued_at') or 0) > float(job.get('max_wait') or 25):
            logger.warning("dropping job %s: waited past its deadline", job.get('id'))
            continue
        started = time.time()
        try:
            data = _run(job)
        except Exception:
            logger.exception("job %s failed", job.get('id'))
            data = {'compiled': True, 'error': 'The code execution service hit an internal error. Your code was not graded - please try again.', 'cases': []}
        key = judge_queue.RESULT + str(job.get('id'))
        try:
            pipe = r.pipeline()
            pipe.rpush(key, json.dumps(data))
            pipe.expire(key, 180)
            pipe.execute()
        except Exception:
            logger.exception("could not store the result of job %s", job.get('id'))
        logger.info("job %s (%s) done in %.2fs", job.get('id'), job.get('kind'), time.time() - started)


def _heartbeat():
    r = _client()
    while not _stop.is_set():
        try:
            r.zadd(judge_queue.WORKERS, {WORKER_ID: time.time()})
        except Exception:
            pass
        _stop.wait(10)
    try:
        r.zrem(judge_queue.WORKERS, WORKER_ID)
    except Exception:
        pass


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    status = docker_runner.docker_status(max_age=0)
    if not (status['docker'] and status['image']):
        logger.error("Docker or the judge image '%s' is not available on this host: %s", Config.JUDGE_IMAGE, status)
        return 1
    docker_runner.warmup()
    threads = [threading.Thread(target=_loop, args=(i,), daemon=True) for i in range(PARALLEL)]
    threads.append(threading.Thread(target=_heartbeat, daemon=True))
    for t in threads:
        t.start()
    logger.info("judge worker %s running %d programs at a time", WORKER_ID, PARALLEL)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _stop.set()
        time.sleep(1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
