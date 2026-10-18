ALTER TABLE cp_attempts ADD INDEX idx_cp_attempts_submitted (status, submitted_at);
