from flask import flash, redirect, render_template, session, url_for
from routes.courses_platform.databases.profile_db import ProfileOperation
from extensions import user_login_required
import logging
from routes import users_bp
from collections import defaultdict
profile_op = ProfileOperation()
logger = logging.getLogger(__name__)
@users_bp.route('/profile', methods=['GET'])
@user_login_required
def profile_view():
    user_email = session.get('user_email')

    try:
        profile_op.update_last_active(user_email)

        user_details = profile_op.get_user_details(user_email)
        
        if not user_details:
            flash("Could not retrieve user details.", "error")
            return redirect(url_for('users.index'))

        enrollment_count = profile_op.get_enrollment_count(user_email)
        recent_course = profile_op.get_recently_enrolled_course(user_email)
        has_password = bool(user_details.get('password'))

        enrolled_courses_data = profile_op.get_enrolled_courses(user_email)
        enrolled_courses = []
        for item in enrolled_courses_data:
            if item.get('payment_status') in ('Paid', 'FREE'):
                course_details = profile_op.get_course_details(item['code'])
                if course_details:
                    course_details['unique_code'] = item['unique_code']
                    course_details['status_label'] = 'Purchased' if item.get('payment_status') == 'Paid' else 'Free Enrollment'
                    enrolled_courses.append(course_details)
        
        all_purchases = profile_op.get_all_purchases(user_email)
        grouped_purchases = defaultdict(list)
        for p in all_purchases:
            grouped_purchases[p['section']].append(p)

        purchase_count = len(all_purchases)
        total_spent = sum(float(p.get('final_price') or 0) for p in all_purchases)

        recent_purchase = all_purchases[0] if all_purchases else None
        first_enrolled_course = enrolled_courses[0] if enrolled_courses else None

        course_unique_codes = {c['code']: c['unique_code'] for c in enrolled_courses}
        
        username = user_details.get('username')
        email = user_email if user_email else user_details.get('email')
        initials = "".join([name[0] for name in username.split()]).upper() if username else ""

        return render_template(
            'users/courses_platform/profile/profile.html',
            user_details=user_details,
            enrollment_count=enrollment_count,
            recent_course=recent_course,
            enrolled_courses=enrolled_courses,
            user_is_authenticated=True,
            username=username,
            email=email,
            initials=initials,
            logged_in=True,
            has_password=has_password,
            grouped_purchases=grouped_purchases,
            recent_purchase=recent_purchase,
            first_enrolled_course=first_enrolled_course,
            course_unique_codes=course_unique_codes,
            total_spent=total_spent,
            purchase_count=purchase_count
        )
    except Exception as e:
        logger.error(f"Error in profile_view for {user_email}: {e}")
        flash("An unexpected error occurred while loading your profile.", "error")
        return redirect(url_for('users.index'))