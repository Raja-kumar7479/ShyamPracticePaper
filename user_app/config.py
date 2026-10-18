import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

IS_PRODUCTION = bool(
    os.environ.get('APP_ENV', '').lower() == 'production'
    or os.environ.get('RENDER')
    or os.environ.get('PYTHONANYWHERE_DOMAIN')
    or os.environ.get('PYTHONANYWHERE_SITE')
    or os.environ.get('GUNICORN_CMD_ARGS')
)


class Config:

    IS_PRODUCTION = IS_PRODUCTION
    RATELIMIT_ENABLED = os.environ.get('RATELIMIT_ENABLED', '1').strip().lower() not in ('0', 'false', 'no', 'off')
    SECRET_KEY = os.environ.get('SECRET_KEY')
    CSRF_SESSION_KEY = os.environ.get('CSRF_SESSION_KEY')
    TEST_TOKEN_SECRET = os.environ.get('TEST_TOKEN_SECRET')
    
  
    DATABASE_HOST = os.environ.get('DATABASE_HOST', 'localhost')
    DATABASE_USER = os.environ.get('DATABASE_USER', 'root')
    DATABASE_PASSWORD = os.environ.get('DATABASE_PASSWORD')
    DATABASE_NAME = os.environ.get('DATABASE_NAME')
    
   
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'false').lower() == 'true'
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', ('ShyamPracticePaper', os.environ.get('MAIL_USERNAME')))
    BRAND_NAME = os.environ.get('BRAND_NAME', 'ShyamPracticePaper')
    
 
    RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID')
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_SECRET')
    RAZORPAY_WEBHOOK_SECRET = os.environ.get('RAZORPAY_WEBHOOK_SECRET') 
    GOOGLE_CLIENT_ID = os.environ.get("CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
    
   
    REDIRECT_URI = os.environ.get('REDIRECT_URI') or "http://127.0.0.1:5002/callback"
    
   
    EMAIL_RATE_LIMIT = '5/hour'
    RECEIPT_TOKEN_EXPIRY_SECONDS = 300
    
    
    SESSION_TYPE = 'filesystem'
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_SAMESITE = 'Lax'

    UPLOAD_BASE = os.environ.get('UPLOAD_BASE') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')

    DB_HOST = DATABASE_HOST
    DB_PORT = int(os.environ.get('DB_PORT', 3306))
    DB_USER = DATABASE_USER
    DB_PASS = DATABASE_PASSWORD
    DB_NAME = DATABASE_NAME

    JUDGE_IMAGE = os.environ.get('JUDGE_IMAGE', 'codejudge-runner:latest')
    RUN_TIMEOUT = int(os.environ.get('RUN_TIMEOUT', 10))
    COMPILE_TIMEOUT = int(os.environ.get('COMPILE_TIMEOUT', 20))
    MEMORY_LIMIT = os.environ.get('MEMORY_LIMIT', '512m')
    CPU_QUOTA = float(os.environ.get('CPU_QUOTA', 1))
    DOCKER_NETWORK_DISABLED = os.environ.get('DOCKER_NETWORK_DISABLED', 'true').lower() in ('1', 'true', 'yes', 'on')
    DOCKER_READONLY_ROOTFS = os.environ.get('DOCKER_READONLY_ROOTFS', 'true').lower() in ('1', 'true', 'yes', 'on')
    DOCKER_RUN_AS_NONROOT = os.environ.get('DOCKER_RUN_AS_NONROOT', 'true').lower() in ('1', 'true', 'yes', 'on')
    JUDGE_FILE_LIMIT_MB = int(os.environ.get('JUDGE_FILE_LIMIT_MB', 32))
    JUDGE_STDOUT_LIMIT_BYTES = int(os.environ.get('JUDGE_STDOUT_LIMIT_BYTES', 4 * 1024 * 1024))
    JUDGE_CASE_OUTPUT_LIMIT_BYTES = int(os.environ.get('JUDGE_CASE_OUTPUT_LIMIT_BYTES', 2 * 1024 * 1024))
    DOCKER_STARTUP_GRACE = int(os.environ.get('DOCKER_STARTUP_GRACE', 5))

    SQL_SANDBOX_USER = os.environ.get('SQL_SANDBOX_USER', 'cj_sandbox')
    SQL_SANDBOX_PASS = os.environ.get('SQL_SANDBOX_PASS', 'cj_sandbox_pw')
    SQL_SANDBOX_PREFIX = os.environ.get('SQL_SANDBOX_PREFIX', 'sbx_q')
    SQL_QUERY_TIMEOUT_MS = int(os.environ.get('SQL_QUERY_TIMEOUT_MS', 5000))
    SQL_SANDBOX_PARALLEL = int(os.environ.get('SQL_SANDBOX_PARALLEL', 8))
    SQL_SANDBOX_WAIT = int(os.environ.get('SQL_SANDBOX_WAIT', 10))
    SQL_MAX_ROWS = int(os.environ.get('SQL_MAX_ROWS', 500))

    UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              'static', 'images', 'coding_schemas')