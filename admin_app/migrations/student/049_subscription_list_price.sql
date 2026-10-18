SET @db := DATABASE();
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='pcp_subscriptions' AND COLUMN_NAME='list_paise') = 0,
  'ALTER TABLE pcp_subscriptions ADD COLUMN list_paise INT NULL AFTER amount_paise, ADD COLUMN discount_pct DECIMAL(5,2) NULL AFTER list_paise',
  'SELECT "list price columns exist" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
