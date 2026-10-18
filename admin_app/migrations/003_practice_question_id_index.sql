SET @idx_exists = (SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'questions'
    AND INDEX_NAME = 'idx_q_question_id');
SET @sql = IF(@idx_exists = 0,
    'ALTER TABLE questions ADD INDEX idx_q_question_id (question_id)',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
