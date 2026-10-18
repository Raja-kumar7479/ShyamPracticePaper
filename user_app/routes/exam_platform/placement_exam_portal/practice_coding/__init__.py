

def register(app):
    from .routes_practice import bp
    from . import routes_billing
    from . import routes_quiz
    app.register_blueprint(bp)

