SET @has_status := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'premium_plans' AND COLUMN_NAME = 'status');
SET @sql := IF(@has_status > 0, 'ALTER TABLE premium_plans DROP COLUMN status', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
