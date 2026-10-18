-- Coding-question grading modes.
--
-- The judge only did a trimmed exact-match on stdout, so a problem whose answer
-- is a floating-point number, or whose lines may come back in any order, could
-- not be graded. Each coding question now carries how its output should be
-- compared, on both the practice bank (pcp_questions) and the exam editor
-- (cp_questions):
--   exact      - trimmed exact match (the previous, and default, behaviour)
--   float      - token-wise numeric compare within float_tolerance
--   unordered  - the set of output lines, order ignored
--
-- Idempotent: safe to re-run.

SET @db := DATABASE();

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='pcp_questions' AND COLUMN_NAME='compare_mode') = 0,
  'ALTER TABLE pcp_questions
     ADD COLUMN compare_mode ENUM(''exact'',''float'',''unordered'') NOT NULL DEFAULT ''exact'',
     ADD COLUMN float_tolerance DOUBLE NULL',
  'SELECT "pcp_questions compare_mode exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='cp_questions' AND COLUMN_NAME='compare_mode') = 0,
  'ALTER TABLE cp_questions
     ADD COLUMN compare_mode ENUM(''exact'',''float'',''unordered'') NOT NULL DEFAULT ''exact'',
     ADD COLUMN float_tolerance DOUBLE NULL',
  'SELECT "cp_questions compare_mode exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
