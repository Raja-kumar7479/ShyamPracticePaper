-- Fixes: the premium checkout opened Razorpay with only name and email
-- prefilled, so the contact field showed whatever number Razorpay had
-- remembered in that browser rather than the buyer's own. The subscription
-- receipt PDF was built with phone="" for the same reason - nothing on the
-- subscription row held a contact number.
--
-- The phone is now collected before the gateway opens and stored here, so
-- prefill.contact is the student's number and the receipt prints it. The
-- column is NULL-able: subscriptions bought before this migration have no
-- number to backfill.
-- Idempotent: safe to re-run.

SET @db := DATABASE();

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'pcp_subscriptions'
     AND COLUMN_NAME = 'phone') = 0,
  'ALTER TABLE pcp_subscriptions ADD COLUMN phone VARCHAR(20) NULL AFTER email',
  'SELECT "phone already exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
