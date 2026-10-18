SET @db := DATABASE();
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='pcp_subscriptions' AND COLUMN_NAME='reminder_sent_at') = 0,
  'ALTER TABLE pcp_subscriptions ADD COLUMN reminder_sent_at DATETIME NULL AFTER expires_at',
  'SELECT "reminder column exists" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
