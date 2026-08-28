
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_CONFIGURED_FLAG = "_app_logging_configured"


def configure_logging(level=None):
    root = logging.getLogger()

    if getattr(root, _CONFIGURED_FLAG, False):
        return

    if level is None:
        level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)

    root.setLevel(level)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as exc:
        root.warning("File logging disabled (%s); using console only.", exc)

    for noisy in ("werkzeug", "engineio", "socketio", "urllib3", "mysql.connector"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    setattr(root, _CONFIGURED_FLAG, True)
    root.info("Logging configured (level=%s, file=%s)", logging.getLevelName(level), LOG_FILE)
