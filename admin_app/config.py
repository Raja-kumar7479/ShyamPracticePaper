import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
   
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
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', ('Shyam Practice Paper Admin', os.environ.get('MAIL_USERNAME')))
    BRAND_NAME = os.environ.get('BRAND_NAME', 'Shyam Practice Paper')
    ADMIN_URL = os.environ.get('ADMIN_URL', 'http://127.0.0.1:5001')
    
 
    RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID')
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_SECRET')

    EMAIL_RATE_LIMIT = '5/hour'
    RECEIPT_TOKEN_EXPIRY_SECONDS = 300
    
    
    SESSION_COOKIE_NAME = 'admin_session'
    SESSION_TYPE = 'filesystem'
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = bool(os.environ.get('RENDER') or os.environ.get('GUNICORN_CMD_ARGS'))
    SESSION_COOKIE_SAMESITE = 'Lax'

    UPLOAD_BASE = os.environ.get('UPLOAD_BASE') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')