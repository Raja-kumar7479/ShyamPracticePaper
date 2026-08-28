"""WSGI entry point.

Production runs `gunicorn --worker-class eventlet`. Eventlet's cooperative
concurrency only works if the standard library is monkey-patched *before*
anything else imports socket/ssl/threading, so it has to happen here, at the
very top of the process, ahead of `from app import ...`.

Without it a single eventlet worker serialises every request behind each
blocking database call, because the driver's socket never yields to the loop.
"""
import os

_USE_EVENTLET = bool(os.environ.get('RENDER') or os.environ.get('GUNICORN_CMD_ARGS') or os.environ.get('USE_EVENTLET'))

if _USE_EVENTLET:
    try:
        import eventlet
        eventlet.monkey_patch()
        # The driver's C extension does not yield even when patched, so the
        # pure-Python implementation is required for the patch to be effective.
        os.environ.setdefault('MYSQL_USE_PURE', '1')
    except ImportError:  # pragma: no cover - eventlet absent, gunicorn will fall back
        pass

from app import app, socketio  # noqa: E402  (must follow monkey_patch)

__all__ = ["app", "socketio"]

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5002, allow_unsafe_werkzeug=True)
