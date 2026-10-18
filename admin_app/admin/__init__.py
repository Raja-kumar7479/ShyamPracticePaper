import logging
import time
from flask import Blueprint, g, request, session

admin_bp = Blueprint('admin', __name__)

_audit_logger = logging.getLogger('admin.audit')

SLOW_REQUEST_MS = 1000


@admin_bp.before_request
def _audit_start():
    g._audit_start = time.perf_counter()


@admin_bp.after_request
def _audit_end(response):
    started = getattr(g, '_audit_start', None)
    if started is None:
        return response
    duration_ms = (time.perf_counter() - started) * 1000
    who = session.get('admin_email', 'anonymous')
    line = f"AUDIT: [{who}] {request.method} {request.path} -> {response.status_code} in {duration_ms:.0f}ms"
    if duration_ms >= SLOW_REQUEST_MS:
        _audit_logger.warning(f"{line} (SLOW)")
    elif response.status_code >= 500:
        _audit_logger.error(line)
    elif response.status_code >= 400:
        _audit_logger.warning(line)
    else:
        _audit_logger.info(line)
    return response

from . import security
from .auth import admin_login
from .auth import password_reset
from .manage_qpractice import practice_paper
from .manage_course import  enroll_course
from .manage_mock_test import test_details_insert,test_feedback,user_test_log
from .manage_mock_test import comm_question_insert
from .manage_mock_test import coding_question_panel
from .manage_catalog import catalog_admin
from .manage_premium import premium_catalog
from .manage_practice_coding import practice_admin
from .manage_practice_coding import quiz_admin
from .manage_modules import course_content,notes_content,practice_questions
from .manage_purchase import purchase_handle