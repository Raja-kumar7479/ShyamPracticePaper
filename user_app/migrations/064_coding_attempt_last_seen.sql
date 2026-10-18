ALTER TABLE cp_attempts ADD COLUMN last_seen TIMESTAMP NULL DEFAULT NULL;
UPDATE cp_attempts SET last_seen = NOW() WHERE status = 'in_progress' AND resumed_at IS NOT NULL;
