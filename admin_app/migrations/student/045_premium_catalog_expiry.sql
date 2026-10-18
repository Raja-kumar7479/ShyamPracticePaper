SET @db := DATABASE();

-- Until when a course's premium is on sale. Past it the reader treats the
-- course as off sale at once, and the expiry job flips the status so the
-- admin list says so too. Subscriptions already bought keep their own dates.
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='premium_catalog' AND COLUMN_NAME='expires_at') = 0,
  'ALTER TABLE premium_catalog ADD COLUMN expires_at DATETIME NULL AFTER offer_ends_at',
  'SELECT "premium_catalog expires_at exists" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
