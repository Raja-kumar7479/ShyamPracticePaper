-- Server-side holding area for an in-progress signup.
--
-- The signup OTP and the bcrypt password hash used to live in the Flask
-- session. That cookie is signed but not encrypted, so when the app runs
-- without Redis (the documented fallback) the client could read both: decode
-- the cookie, read the OTP, post it back, and register an address they do not
-- own. The hash was readable for offline cracking too.
--
-- Now the cookie carries only a random token; everything sensitive lives here,
-- and the OTP is stored as a salted hash so even this row cannot be replayed.
--
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS pending_signups (
    token CHAR(64) NOT NULL PRIMARY KEY,
    username VARCHAR(100) DEFAULT NULL,
    email VARCHAR(255) DEFAULT NULL,
    password_hash VARCHAR(255) DEFAULT NULL,
    otp_hash CHAR(64) DEFAULT NULL,
    otp_expires_at DATETIME DEFAULT NULL,
    otp_attempts INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_pending_signup_email (email),
    INDEX idx_pending_signup_created (created_at)
) ENGINE=InnoDB;
