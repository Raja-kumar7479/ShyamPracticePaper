"""Practice Coding Platform - LeetCode-style problem bank with premium tier.

Fully separate from the exam coding portal: its own tables (pcp_*), its own
executor copy, its own routes and templates, so practice and proctored exams
can evolve independently.
"""


def register(app):
    from .routes_practice import bp
    from . import routes_billing  # noqa: F401 - attaches billing routes to bp
    from . import routes_quiz     # noqa: F401 - attaches quiz routes to bp
    app.register_blueprint(bp)

    # The starter question bank used to be written from here on every boot.
    # Questions are admin content, so seeding moved to the admin app:
    #   python admin_app/admin/manage_practice_coding/seed_practice_content.py
