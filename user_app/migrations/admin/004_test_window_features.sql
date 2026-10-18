SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'test_description'
    AND COLUMN_NAME = 'show_calculator');
SET @sql = IF(@c = 0,
    'ALTER TABLE test_description ADD COLUMN show_calculator TINYINT(1) NOT NULL DEFAULT 1 AFTER total_duration_minutes',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'test_questions'
    AND COLUMN_NAME = 'question_image');
SET @sql = IF(@c = 0,
    'ALTER TABLE test_questions ADD COLUMN question_image VARCHAR(255) NULL AFTER question_text',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'test_questions'
    AND COLUMN_NAME = 'option_regions');
SET @sql = IF(@c = 0,
    'ALTER TABLE test_questions ADD COLUMN option_regions TEXT NULL AFTER question_image',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'test_attempt_details'
    AND COLUMN_NAME = 'is_flagged');
SET @sql = IF(@c = 0,
    'ALTER TABLE test_attempt_details ADD COLUMN is_flagged TINYINT(1) NOT NULL DEFAULT 0 AFTER status_of_attempt',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'test_attempt_details'
    AND COLUMN_NAME = 'flag_note');
SET @sql = IF(@c = 0,
    'ALTER TABLE test_attempt_details ADD COLUMN flag_note VARCHAR(255) NULL AFTER is_flagged',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @c = (SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'test_attempt_details'
    AND INDEX_NAME = 'idx_tad_flagged');
SET @sql = IF(@c = 0,
    'ALTER TABLE test_attempt_details ADD INDEX idx_tad_flagged (test_key, is_flagged)',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
