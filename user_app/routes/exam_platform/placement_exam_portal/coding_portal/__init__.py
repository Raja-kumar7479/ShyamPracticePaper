"""Coding portal - the placement Coding round.

Ported from the standalone CodeJudge compiler. It keeps its own blueprints
(so its internal url_for names stay intact) but runs inside this application:
same database pool, same session auth, same templates/static tree.

register(app) is called once from user_app/app.py.
"""
import logging

logger = logging.getLogger(__name__)


def register(app):
    from .routes import BLUEPRINTS
    for bp in BLUEPRINTS:
        if bp.name in app.blueprints:
            continue
        app.register_blueprint(bp)
    logger.info("CODING PORTAL: registered %d blueprint(s)", len(BLUEPRINTS))
