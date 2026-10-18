from functools import wraps
from flask import session, redirect, url_for, flash, request, current_app
import logging
import time
from routes.exam_platform.competitive_exam_platform.databases.main_handler_db import UserOperation
import hmac
import hashlib
import secrets

logger = logging.getLogger(__name__)

user_op = UserOperation()
TOKEN_EXPIRY_BUFFER_SECONDS = 30
SUBMIT_GRACE_SECONDS = 300


def generate_test_token(email, test_id, duration_seconds):
    secret_key = current_app.config.get('TEST_TOKEN_SECRET')
    if not secret_key:
        logger.error("TEST_TOKEN_SECRET is not configured.")
        return None
    timestamp = int(time.time())
    nonce = secrets.token_hex(16)
    data = f"{email}:{test_id}:{timestamp}:{nonce}:{duration_seconds}"
    signature = hmac.new(secret_key.encode(), data.encode(), hashlib.sha256).hexdigest()
    return f"{data}:{signature}"

def validate_test_token(token, email, test_id, grace_seconds=TOKEN_EXPIRY_BUFFER_SECONDS):
    if not token:
        logger.warning("Token validation failed: No token provided.")
        return False
    try:
        parts = token.split(':')
        if len(parts) != 6:
            logger.warning(f"Token validation failed: Invalid token format. Parts: {len(parts)}")
            return False
        email_from_token, test_id_from_token, timestamp_str, nonce, duration_str, received_signature = parts
        timestamp = int(timestamp_str)
        duration = int(duration_str)
        if email != email_from_token or test_id != test_id_from_token:
            logger.warning(f"Token validation failed: Email or test ID mismatch. Email: {email}, Test ID: {test_id}")
            return False
        data = f"{email}:{test_id}:{timestamp}:{nonce}:{duration}"
        secret_key = current_app.config.get('TEST_TOKEN_SECRET')
        if not secret_key:
            logger.error("TEST_TOKEN_SECRET is not configured for validation.")
            return False
        expected_signature = hmac.new(secret_key.encode(), data.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_signature, received_signature):
            logger.warning("Token validation failed: Signature mismatch.")
            return False
        current_time = int(time.time())
        expiry_time = timestamp + duration + grace_seconds
        if current_time > expiry_time:
            logger.warning(f"Token validation failed: Token has expired. Current time: {current_time}, Expiry time: {expiry_time}")
            return False
        logger.info(f"Token validated successfully for user {email} and test {test_id}.")
        return True
    except Exception as e:
        logger.exception(f"[TOKEN VALIDATION ERROR] {e}")
        return False
