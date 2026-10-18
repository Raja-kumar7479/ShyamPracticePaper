SET @db := DATABASE();

UPDATE premium_plans
   SET valid_until = DATE_ADD(NOW(), INTERVAL COALESCE(duration_days, 30) DAY)
 WHERE valid_until IS NULL;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='premium_plans' AND COLUMN_NAME='duration_days') > 0,
  'ALTER TABLE premium_plans DROP COLUMN duration_days, DROP COLUMN position',
  'SELECT "plans already dated" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

ALTER TABLE premium_plans MODIFY COLUMN valid_until DATETIME NOT NULL;
