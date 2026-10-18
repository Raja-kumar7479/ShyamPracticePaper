SET @db := DATABASE();

-- Each plan has its own "on sale until": a monthly plan and a yearly plan are
-- rarely sold for the same period. The old single date seeds both.
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='premium_catalog' AND COLUMN_NAME='monthly_expires_at') = 0,
  'ALTER TABLE premium_catalog ADD COLUMN monthly_expires_at DATETIME NULL AFTER monthly_discount, ADD COLUMN yearly_expires_at DATETIME NULL AFTER yearly_discount',
  'SELECT "premium_catalog plan expiry exists" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @has_old := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='premium_catalog' AND COLUMN_NAME='expires_at');
SET @sql := IF(@has_old > 0,
  'UPDATE premium_catalog SET monthly_expires_at = COALESCE(monthly_expires_at, expires_at), yearly_expires_at = COALESCE(yearly_expires_at, expires_at)',
  'SELECT "nothing to seed" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql := IF(@has_old > 0, 'ALTER TABLE premium_catalog DROP COLUMN expires_at', 'SELECT "expires_at already dropped" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
