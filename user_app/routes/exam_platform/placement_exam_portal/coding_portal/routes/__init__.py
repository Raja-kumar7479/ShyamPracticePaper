"""Blueprint registry for the coding portal.

The compiler's own auth blueprint is intentionally absent: this app already
provides login and registration, and the portal authenticates through
auth_bridge.py against the existing session.

Its admin blueprint is gone for the same reason. Coding tests, sections and
questions are authored in the admin app (admin/manage_coding +
admin/manage_mock_test/coding_question_panel.py), which writes the same cp_*
tables this portal reads at exam time.
"""
from . import test, coding, sql, web

BLUEPRINTS = (test.bp, coding.bp, sql.bp, web.bp)
