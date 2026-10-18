import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_APP = os.path.join(ROOT, 'user_app')
ADMIN_APP = os.path.join(ROOT, 'admin_app')

REQUIRED = {
    'test_description': ['code', 'show_calculator'],
    'test_questions': ['question_image', 'option_regions', 'test_description_id', 'section_id'],
    'test_attempt_details': ['attempt_number', 'is_flagged', 'flag_note'],
    'test_result': ['attempt_number'],
    'user_test_log': ['attempt_number', 'last_heartbeat'],
    'questions': ['question_image', 'option_regions'],
    'assessment_rounds': ['round_type'],
    'comm_description': ['round_id', 'requires_seb', 'difficulty_level', 'show_calculator'],
    'comm_sections': ['section_name', 'section_title', 'section_duration_seconds', 'section_order'],
    'comm_questions': ['question_type', 'instruction_text', 'media_url', 'options_title',
                       'recording_time_seconds', 'thinking_time_seconds', 'word_limit', 'sub_questions',
                       'test_description_id', 'question_number'],
    'comm_user_log': ['session_token', 'token_expiry', 'audio_check_passed'],
    'comm_attempt_details': ['audio_response_path', 'transcription_text', 'accuracy_score'],
    'comm_proctoring_logs': ['snapshot_path', 'log_type'],
    'comm_result': ['net_score', 'accuracy'],
    'comm_feedback': ['feedback_content', 'suggestions'],
}

FIX_HINTS = {
    'test_attempt_details.attempt_number': 'user_app/migrations/003_test_attempt_details_attempt_number.sql',
    'comm_user_log.session_token': 'user_app/migrations/006_comm_user_log_session_token.sql',
    'comm_description.round_id': 'user_app/migrations/008_comm_rounds_sections.sql',
    'comm_sections': 'user_app/migrations/008_comm_rounds_sections.sql',
    'assessment_rounds': 'user_app/migrations/008_comm_rounds_sections.sql',
    'comm_description': 'user_app/migrations/007_comm_mirror_tables.sql',
    'comm_questions': 'user_app/migrations/007_comm_mirror_tables.sql',
    'comm_result': 'user_app/migrations/007_comm_mirror_tables.sql',
    'comm_feedback': 'user_app/migrations/007_comm_mirror_tables.sql',
}

problems = []


def check_db():
    sys.path.insert(0, USER_APP)
    os.chdir(USER_APP)
    from config import Config
    import mysql.connector
    cnx = mysql.connector.connect(host=Config.DATABASE_HOST, user=Config.DATABASE_USER,
                                  password=Config.DATABASE_PASSWORD, database=Config.DATABASE_NAME)
    cur = cnx.cursor()
    db = Config.DATABASE_NAME
    print(f"Database: {db} @ {Config.DATABASE_HOST}")

    cur.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s", (db,))
    tables = {r[0] for r in cur.fetchall()}

    for table, cols in REQUIRED.items():
        if table not in tables:
            hint = FIX_HINTS.get(table, '')
            problems.append(f"TABLE MISSING: {table}" + (f"  -> run {hint}" if hint else ''))
            continue
        cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s", (db, table))
        have = {r[0] for r in cur.fetchall()}
        for col in cols:
            if col not in have:
                key = f'{table}.{col}'
                hint = FIX_HINTS.get(key) or FIX_HINTS.get(table, '')
                problems.append(f"COLUMN MISSING: {key}" + (f"  -> run {hint}" if hint else ''))
    cur.close()
    cnx.close()


def check_apps():
    from flask import Flask
    from routes import users_bp
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config['SECRET_KEY'] = 'smoke'
    app.register_blueprint(users_bp)
    print(f"user_app blueprint OK ({len(list(app.url_map.iter_rules()))} routes)")

    for mod in list(sys.modules):
        if mod == 'routes' or mod.startswith('routes.') or mod in ('config', 'extensions', 'db_pool'):
            del sys.modules[mod]
    sys.path.remove(USER_APP)
    sys.path.insert(0, ADMIN_APP)
    os.chdir(ADMIN_APP)
    from admin import admin_bp
    app2 = Flask('admin_smoke', template_folder='templates', static_folder='static')
    app2.config['SECRET_KEY'] = 'smoke'
    app2.register_blueprint(admin_bp)
    print(f"admin_app blueprint OK ({len(list(app2.url_map.iter_rules()))} routes)")


def main():
    try:
        check_db()
    except Exception as e:
        problems.append(f"DB CHECK FAILED: {e}")
    try:
        check_apps()
    except Exception as e:
        problems.append(f"APP IMPORT FAILED: {e}")

    print()
    if problems:
        print(f"FAILED — {len(problems)} problem(s):")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("ALL CHECKS PASSED — schema and apps are in sync.")


if __name__ == '__main__':
    main()
