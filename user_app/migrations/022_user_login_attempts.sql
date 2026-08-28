-- Server-side login throttling for the user app.
--
-- Failed attempts were counted in the visitor's own session, so discarding
-- the cookie between tries reset the counter and the 5-attempt lockout never
-- actually bit. Counting them here, keyed on client IP and on the account
-- being targeted, is not resettable by the client.
--
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS user_login_attempts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    identifier VARCHAR(190) NOT NULL,
    attempts INT NOT NULL DEFAULT 0,
    last_attempt_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_until DATETIME DEFAULT NULL,
    UNIQUE KEY uq_user_login_identifier (identifier),
    INDEX idx_user_login_locked_until (locked_until)
) ENGINE=InnoDB;
