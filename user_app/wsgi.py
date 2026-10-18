import os

if (os.environ.get('SPP_ASYNC_MODE') or '').strip().lower() == 'gevent':
    from gevent import monkey
    monkey.patch_all()
    os.environ.setdefault('MYSQL_USE_PURE', '1')

from app import app, socketio

__all__ = ["app", "socketio"]

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5002, allow_unsafe_werkzeug=True)
