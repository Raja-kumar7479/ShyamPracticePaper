-- Speeds up the Manage Tests page. Every question fetch, count, max-number and
-- structure query filters test_questions by test_description_id and often by
-- section_id, and test descriptions are always fetched by test_id. Without these
-- indexes each of those is a full table scan that gets slower as questions grow.
-- Idempotent: safe to re-run.

SET @db := DATABASE();

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.STATISTICS
   WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'test_questions'
     AND INDEX_NAME = 'idx_tq_desc_section') = 0,
  'ALTER TABLE test_questions ADD INDEX idx_tq_desc_section (test_description_id, section_id, question_number)',
  'SELECT "idx_tq_desc_section already exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.STATISTICS
   WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'test_description'
     AND COLUMN_NAME = 'test_id' AND SEQ_IN_INDEX = 1) = 0,
  'ALTER TABLE test_description ADD INDEX idx_td_test_id (test_id)',
  'SELECT "an index on test_id already exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
