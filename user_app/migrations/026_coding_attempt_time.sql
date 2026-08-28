-- Active-time tracking for coding attempts. The attempt row is reused across
-- resumes, so wall-clock started_at -> submitted_at is wrong whenever the
-- candidate leaves and returns: it counted absent time and clock skew.
-- elapsed_seconds accumulates only time actually spent in the exam;
-- resumed_at marks the start of the currently running segment (NULL = paused).

SET @col := (SELECT COUNT(*) FROM information_schema.COLUMNS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cp_attempts'
               AND COLUMN_NAME = 'elapsed_seconds');
SET @sql := IF(@col = 0,
  'ALTER TABLE cp_attempts ADD COLUMN elapsed_seconds INT NOT NULL DEFAULT 0',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @col := (SELECT COUNT(*) FROM information_schema.COLUMNS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cp_attempts'
               AND COLUMN_NAME = 'resumed_at');
SET @sql := IF(@col = 0,
  'ALTER TABLE cp_attempts ADD COLUMN resumed_at DATETIME NULL',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
