SET @db := DATABASE();

-- A one-line headline for the course's premium, and an optional end date for
-- the discount: after it the list price applies again by itself.
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='premium_catalog' AND COLUMN_NAME='headline') = 0,
  'ALTER TABLE premium_catalog ADD COLUMN headline VARCHAR(160) NULL AFTER code',
  'SELECT "premium_catalog headline exists" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='premium_catalog' AND COLUMN_NAME='offer_ends_at') = 0,
  'ALTER TABLE premium_catalog ADD COLUMN offer_ends_at DATETIME NULL AFTER yearly_discount',
  'SELECT "premium_catalog offer_ends_at exists" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
