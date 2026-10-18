SET @db := DATABASE();

-- Premium is always on sale. What the admin controls per plan is the price,
-- the discount (and when it ends), and how many extra days a purchase gets on
-- top of the plan's 30 / 365. The sale-end dates and the on/off switch go.
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='premium_catalog' AND COLUMN_NAME='monthly_extra_days') = 0,
  'ALTER TABLE premium_catalog ADD COLUMN monthly_extra_days INT NOT NULL DEFAULT 0 AFTER monthly_offer_ends_at, ADD COLUMN yearly_extra_days INT NOT NULL DEFAULT 0 AFTER yearly_offer_ends_at',
  'SELECT "extra days exist" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='premium_catalog' AND COLUMN_NAME='monthly_expires_at') > 0,
  'ALTER TABLE premium_catalog DROP COLUMN monthly_expires_at, DROP COLUMN yearly_expires_at',
  'SELECT "sale-end columns already gone" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='premium_catalog' AND COLUMN_NAME='status') > 0,
  'ALTER TABLE premium_catalog DROP COLUMN status',
  'SELECT "status already gone" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
