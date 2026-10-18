import importlib.util
import multiprocessing
import os
import sys

_mode = (os.environ.get('SPP_ASYNC_MODE') or 'gevent').strip().lower()
if _mode not in ('gevent', 'threading'):
    _mode = 'gevent'
if _mode == 'gevent' and not (importlib.util.find_spec('gevent') and importlib.util.find_spec('geventwebsocket')):
    _mode = 'threading'
    sys.stderr.write("gunicorn.conf: gevent is not installed in this Python, so threaded workers are used. "
                     "Install requirements.txt in the app's virtual environment and start from it for full speed.\n")
os.environ['SPP_ASYNC_MODE'] = _mode

_cores = multiprocessing.cpu_count()
_workers = int(os.environ.get('WEB_CONCURRENCY') or 0) or max(2, min(_cores, 8))
os.environ['WEB_CONCURRENCY'] = str(_workers)

bind = os.environ.get('BIND') or ('0.0.0.0:' + os.environ.get('PORT', '5002'))
workers = _workers
if _mode == 'gevent':
    worker_class = 'geventwebsocket.gunicorn.workers.GeventWebSocketWorker'
    worker_connections = int(os.environ.get('WORKER_CONNECTIONS', '2000'))
else:
    worker_class = 'gthread'
    threads = int(os.environ.get('GUNICORN_THREADS', '32'))
timeout = int(os.environ.get('GUNICORN_TIMEOUT', '120'))
graceful_timeout = 30
keepalive = int(os.environ.get('GUNICORN_KEEPALIVE', '5'))
backlog = 2048
max_requests = int(os.environ.get('GUNICORN_MAX_REQUESTS', '20000'))
max_requests_jitter = 2000
accesslog = os.environ.get('GUNICORN_ACCESS_LOG', '-') or None
errorlog = '-'
forwarded_allow_ips = os.environ.get('FORWARDED_ALLOW_IPS', '127.0.0.1')
