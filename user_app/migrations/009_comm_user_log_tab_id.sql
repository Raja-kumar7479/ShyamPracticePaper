SET @col_exists = (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'comm_user_log'
    AND COLUMN_NAME = 'tab_id');
SET @sql = IF(@col_exists = 0,
    'ALTER TABLE comm_user_log ADD COLUMN tab_id VARCHAR(64) NULL AFTER session_token',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
