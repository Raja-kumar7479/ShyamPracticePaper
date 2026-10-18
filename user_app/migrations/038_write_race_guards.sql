-- Two requests landing at the same instant (two tabs, a timer auto-submit
-- racing a click, a browser callback racing a gateway webhook) could each pass
-- the application's "does it exist yet" check and both write. These unique
-- keys make the second write fail at the database, and the code treats that
-- failure as "already done" rather than an error.

SET @sql := IF((SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='user_test_log' AND INDEX_NAME='uq_utl_attempt') = 0,
  'ALTER TABLE user_test_log ADD UNIQUE KEY uq_utl_attempt (email, test_key, attempt_number)',
  'SELECT "uq_utl_attempt exists" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='test_result' AND INDEX_NAME='uq_tr_attempt') = 0,
  'ALTER TABLE test_result ADD UNIQUE KEY uq_tr_attempt (email, test_key, attempt_number)',
  'SELECT "uq_tr_attempt exists" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='purchase' AND INDEX_NAME='uq_purchase_item') = 0,
  'ALTER TABLE purchase ADD UNIQUE KEY uq_purchase_item (payment_id, title)',
  'SELECT "uq_purchase_item exists" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- purchase.email and test_result.email stay NULLable on purpose: their foreign
-- keys to auth are ON DELETE SET NULL, so a purchase or a result outlives the
-- account that made it (the record is kept, the person is unlinked).

-- Looked up by course when an admin checks who is enrolled before a delete.
SET @sql := IF((SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='enrollment' AND INDEX_NAME='idx_enrollment_code') = 0,
  'ALTER TABLE enrollment ADD INDEX idx_enrollment_code (code)',
  'SELECT "idx_enrollment_code exists" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
