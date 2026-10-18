from flask import Blueprint

users_bp = Blueprint('users', __name__)

from .auth.login.manual_login import login
from .auth.login.google_signup_login import google

from .auth.signup import signup
from .auth.forgot_password import forgot
from .auth.set_password import google_set_password
from .auth.legal import legal

from .index import index

from .courses_platform.dashboard.main_profile import main_profile, update_profile, delete_account
from .courses_platform.dashboard.other_courses import courses_dashboard
from .courses_platform.dashboard.purchased_courses import purchased_dashboard
from .courses_platform.dashboard.shopping_courses import shopping

from .courses_platform.enrollment import enrolled_courses

from .courses_platform.payment.enrolled_payment import courses_enrolled
from .courses_platform.payment.purchased_payment import (
    add_cart,
    coupon_code_apply,
    create_payment_order,
    payment_success,
    payment_orders

)

from .exam_platform.study_materials_platform import study_materials_dashboard

from .practice_question_platform.databases import question_handler_db

from .practice_question_platform.practice_question import practice_question

from .exam_platform import exam_window_guard
from .exam_platform import premium_portal
from .exam_platform.placement_exam_portal import rounds
from .exam_platform.placement_exam_portal.communication_portal import routes_proctor
from .exam_platform.placement_exam_portal.communication_portal import start_test
from .exam_platform.placement_exam_portal.communication_portal import platform_info
from .exam_platform.competitive_exam_platform.databases import (
    main_handler_db,
    question_handler_db as comp_question_db,
    result_handler_db,
    test_handler_db
)

from .exam_platform.competitive_exam_platform.test_dashboard import (
    system_login,
    test_dashboard
)

from .exam_platform.competitive_exam_platform.test_instructions import (
    instruction,
    readiness,
    violation
)

from .exam_platform.competitive_exam_platform.test_questions import fetch_question

from .exam_platform.competitive_exam_platform.test_window import start_submit_test

from .exam_platform.competitive_exam_platform.test_results import (
    test_result,
    test_feedback
)

from .exam_platform.competitive_exam_platform.utils import (
    utils_test_dashboard,
    utils_test_token
)
