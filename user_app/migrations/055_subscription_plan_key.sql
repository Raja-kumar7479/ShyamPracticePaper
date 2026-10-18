SET @db := DATABASE();
SET @sql := IF((SELECT DATA_TYPE FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='pcp_subscriptions' AND COLUMN_NAME='plan') = 'enum',
  'ALTER TABLE pcp_subscriptions MODIFY COLUMN plan VARCHAR(40) NOT NULL',
  'SELECT "plan column already widened" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
