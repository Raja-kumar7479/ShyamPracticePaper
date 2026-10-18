import logging

logger = logging.getLogger(__name__)


def register(app):
    from .routes import BLUEPRINTS
    for bp in BLUEPRINTS:
        if bp.name in app.blueprints:
            continue
        app.register_blueprint(bp)
    logger.info("CODING PORTAL: registered %d blueprint(s)", len(BLUEPRINTS))
