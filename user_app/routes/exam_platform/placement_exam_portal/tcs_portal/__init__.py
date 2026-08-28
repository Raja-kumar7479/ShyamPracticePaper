import logging

logger = logging.getLogger(__name__)


def register(app):
    from .routes import bp
    if bp.name in app.blueprints:
        return
    app.register_blueprint(bp)
    logger.info("TCS PORTAL: registered")
