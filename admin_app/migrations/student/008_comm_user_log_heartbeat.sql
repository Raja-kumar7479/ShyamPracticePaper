SET @col_exists = (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'comm_user_log'
    AND COLUMN_NAME = 'last_heartbeat');
SET @sql = IF(@col_exists = 0,
    'ALTER TABLE comm_user_log ADD COLUMN last_heartbeat DATETIME NULL AFTER status',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @idx_exists = (SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'comm_user_log'
    AND INDEX_NAME = 'idx_cul_email_status');
SET @sql = IF(@idx_exists = 0,
    'ALTER TABLE comm_user_log ADD INDEX idx_cul_email_status (email, status)',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @idx_exists = (SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'user_test_log'
    AND INDEX_NAME = 'idx_utl_email_status');
SET @sql = IF(@idx_exists = 0,
    'ALTER TABLE user_test_log ADD INDEX idx_utl_email_status (email, status)',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
