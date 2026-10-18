CREATE TABLE IF NOT EXISTS admin_login_attempts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    identifier VARCHAR(190) NOT NULL,
    attempts INT NOT NULL DEFAULT 0,
    last_attempt_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_until DATETIME DEFAULT NULL,
    UNIQUE KEY uq_admin_login_identifier (identifier),
    INDEX idx_admin_login_locked_until (locked_until)
) ENGINE=InnoDB;
