-- Fixes: "1054 (42S22): Unknown column 'attempt_number' in 'field list'" raised by
-- _save_test_attempt_details() in test_handler_db.py. Every mock-test submission
-- rolled back and the student saw "500 - An error occurred while saving the test
-- results", so no result or answer row was ever stored.
--
-- schema.sql already declares this column (test_attempt_details.attempt_number);
-- databases created before that line was added are missing it. test_result and
-- user_test_log already carry attempt_number, and result_handler_db.py filters
-- on tad.attempt_number to build the result and analysis pages, so the column is
-- required rather than optional.
--
-- Existing rows predate attempt tracking and are all first attempts, so the
-- DEFAULT 1 backfill is correct.
-- Idempotent: safe to re-run.

SET @db := DATABASE();

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'test_attempt_details'
     AND COLUMN_NAME = 'attempt_number') = 0,
  'ALTER TABLE test_attempt_details ADD COLUMN attempt_number INT DEFAULT 1 AFTER time_spent_on_question_seconds',
  'SELECT "attempt_number already exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- Any rows written before the column existed have no attempt recorded.
UPDATE test_attempt_details SET attempt_number = 1 WHERE attempt_number IS NULL;

-- The result and analysis pages look up answers by (test_key, email, attempt_number).
SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.STATISTICS
   WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'test_attempt_details'
     AND INDEX_NAME = 'idx_tad_lookup') = 0,
  'ALTER TABLE test_attempt_details ADD INDEX idx_tad_lookup (test_key, email, attempt_number)',
  'SELECT "idx_tad_lookup already exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
