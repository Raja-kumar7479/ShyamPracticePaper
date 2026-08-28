-- Coding-question authoring support.
--
-- The ported schema kept the whole problem in one `statement_html` blob. Admin
-- authoring needs the parts separately (problem text, input format, example)
-- and each part may be supplied either as typed text or as an uploaded image
-- of a printed question - the same manual/image choice the mock-test and
-- practice papers already offer.
--
-- Idempotent: safe to re-run.

SET @db := DATABASE();

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='cp_questions' AND COLUMN_NAME='input_spec') = 0,
  'ALTER TABLE cp_questions
     ADD COLUMN input_spec TEXT NULL,
     ADD COLUMN example_html TEXT NULL,
     ADD COLUMN statement_image VARCHAR(255) NULL,
     ADD COLUMN input_image VARCHAR(255) NULL,
     ADD COLUMN example_image VARCHAR(255) NULL,
     ADD COLUMN difficulty VARCHAR(20) DEFAULT ''Medium''',
  'SELECT "cp_questions authoring columns exist" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
