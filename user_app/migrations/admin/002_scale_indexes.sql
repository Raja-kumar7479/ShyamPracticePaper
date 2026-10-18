SET @idx_exists = (SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'user_test_log'
    AND INDEX_NAME = 'idx_utl_test_id');
SET @sql = IF(@idx_exists = 0,
    'ALTER TABLE user_test_log ADD INDEX idx_utl_test_id (test_id)',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @idx_exists = (SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'course_content'
    AND INDEX_NAME = 'idx_cc_code_section_status');
SET @sql = IF(@idx_exists = 0,
    'ALTER TABLE course_content ADD INDEX idx_cc_code_section_status (code, section, status)',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @idx_exists = (SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'questions'
    AND INDEX_NAME = 'uq_q_paper_qid');
SET @sql = IF(@idx_exists = 0,
    'ALTER TABLE questions ADD UNIQUE INDEX uq_q_paper_qid (paper_code, question_id)',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @idx_exists = (SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'test_questions'
    AND INDEX_NAME = 'idx_tq_key_section');
SET @sql = IF(@idx_exists = 0,
    'ALTER TABLE test_questions ADD INDEX idx_tq_key_section (test_key, section_id, question_number)',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
