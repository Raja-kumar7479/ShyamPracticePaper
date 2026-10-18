-- Fixes: enrollment_payment INSERT failed with "Unknown column 'user_username'",
-- so no payment row was ever written. get_enrolled_courses() requires
-- ep.payment_status IN ('Paid','FREE'), so every user appeared un-enrolled and
-- was asked to enroll again. Adds the columns the application already reads.
-- Idempotent: safe to re-run.

SET @db := DATABASE();

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'enrollment_payment'
     AND COLUMN_NAME = 'user_username') = 0,
  'ALTER TABLE enrollment_payment ADD COLUMN user_username VARCHAR(100) NULL AFTER user_email',
  'SELECT "user_username already exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'enrollment_payment'
     AND COLUMN_NAME = 'razorpay_payment_id') = 0,
  'ALTER TABLE enrollment_payment ADD COLUMN razorpay_payment_id VARCHAR(100) NULL AFTER payment_id',
  'SELECT "razorpay_payment_id already exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'enrollment_payment'
     AND COLUMN_NAME = 'completion_date') = 0,
  'ALTER TABLE enrollment_payment ADD COLUMN completion_date DATETIME NULL',
  'SELECT "completion_date already exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- payment_id is the join key used by every enrollment query; duplicates would
-- silently fan out the LEFT JOIN and double-count enrollments.
SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.STATISTICS
   WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'enrollment_payment'
     AND INDEX_NAME = 'uq_enrollment_payment_payment_id') = 0,
  'ALTER TABLE enrollment_payment ADD UNIQUE KEY uq_enrollment_payment_payment_id (payment_id)',
  'SELECT "unique index already exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- enrollment already carries UNIQUE KEY unique_enrollment (email, code); no index needed here.

-- Backfill enrollments whose payment row was lost to the failing INSERT.
INSERT INTO enrollment_payment
    (payment_id, razorpay_payment_id, enrollment_id, user_email, user_username,
     course_code, amount_paid, currency, payment_method, payment_status, completion_date)
SELECT
    e.payment_id,
    NULL,
    e.id,
    e.email,
    COALESCE(a.username, SUBSTRING_INDEX(e.email, '@', 1)),
    e.code,
    0.00,
    'INR',
    'FREE',
    'FREE',
    e.enrollment_date
FROM enrollment e
LEFT JOIN enrollment_payment ep ON ep.payment_id = e.payment_id
LEFT JOIN auth a ON a.email = e.email
WHERE ep.id IS NULL
  AND e.payment_id IS NOT NULL
  AND e.payment_id LIKE 'FREE\_%';
