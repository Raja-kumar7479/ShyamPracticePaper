-- The admin Purchases screen finds one customer among many by typing a name,
-- phone number or email prefix. Email and payment_id were already indexed;
-- these cover the other two ways a support request identifies someone, so the
-- search stays a range scan rather than a full read of the purchase table.
-- Idempotent: safe to re-run.

SET @db := DATABASE();

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.STATISTICS
   WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'purchase' AND INDEX_NAME = 'idx_purchase_username') = 0,
  'ALTER TABLE purchase ADD INDEX idx_purchase_username (username)',
  'SELECT "idx_purchase_username already exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.STATISTICS
   WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'purchase' AND INDEX_NAME = 'idx_purchase_phone') = 0,
  'ALTER TABLE purchase ADD INDEX idx_purchase_phone (phone)',
  'SELECT "idx_purchase_phone already exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.STATISTICS
   WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'enrollment_payment' AND INDEX_NAME = 'idx_ep_user_username') = 0,
  'ALTER TABLE enrollment_payment ADD INDEX idx_ep_user_username (user_username)',
  'SELECT "idx_ep_user_username already exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
