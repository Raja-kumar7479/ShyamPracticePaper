SET @db := DATABASE();

-- A discount ends per plan, and never after that plan's own sale does: a
-- single date for both let the monthly discount "run" past the monthly sale.
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='premium_catalog' AND COLUMN_NAME='monthly_offer_ends_at') = 0,
  'ALTER TABLE premium_catalog ADD COLUMN monthly_offer_ends_at DATETIME NULL AFTER monthly_discount, ADD COLUMN yearly_offer_ends_at DATETIME NULL AFTER yearly_discount',
  'SELECT "premium_catalog plan offer end exists" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @has_old := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='premium_catalog' AND COLUMN_NAME='offer_ends_at');
SET @sql := IF(@has_old > 0,
  'UPDATE premium_catalog SET
     monthly_offer_ends_at = COALESCE(monthly_offer_ends_at, LEAST(COALESCE(offer_ends_at, monthly_expires_at), COALESCE(monthly_expires_at, offer_ends_at))),
     yearly_offer_ends_at  = COALESCE(yearly_offer_ends_at,  LEAST(COALESCE(offer_ends_at, yearly_expires_at),  COALESCE(yearly_expires_at,  offer_ends_at)))
   WHERE offer_ends_at IS NOT NULL',
  'SELECT "nothing to seed" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql := IF(@has_old > 0, 'ALTER TABLE premium_catalog DROP COLUMN offer_ends_at', 'SELECT "offer_ends_at already dropped" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
