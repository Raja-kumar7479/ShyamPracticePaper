-- Course taxonomy: constrain the group / code pair and make the content section
-- the single key that decides which exam portal a student is sent to.
--
-- Before this migration:
--   courses.name           free text ('GATE', 'PLACEMENT')
--   courses.code           free text ('CS', 'PLM')
--   course_content.section enum('Mock Test','hnotes','vlecture','jcommunity')
--
-- Placement routing guessed the portal from the test TITLE
-- (classify_round: "does the title contain the word coding?"). That is replaced
-- by an explicit section value, so a title can never route a student wrongly.
--
-- The section widen -> backfill -> narrow order matters: MySQL blanks any value
-- that is not part of the target enum, so old values must still be legal while
-- the UPDATE runs.
--
-- Idempotent: safe to re-run. Each column change is skipped when the column is
-- already an enum, because 013 adds foreign keys from these columns into the
-- taxonomy catalog and MySQL then rejects a repeat MODIFY with
-- "Referencing column and referenced column are incompatible".

SET @db := DATABASE();

-- Already enum (this migration ran), or 013 has since turned these columns back
-- into VARCHAR and put fk_course_group_code on them — either way, leave them be.
SET @done := (SELECT COUNT(*) FROM information_schema.COLUMNS
               WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'courses'
                 AND COLUMN_NAME = 'name' AND DATA_TYPE = 'enum')
           + (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
               WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'courses'
                 AND CONSTRAINT_NAME = 'fk_course_group_code');

-- ---------------------------------------------------------------- courses
SET @sql := IF(@done = 0,
  'ALTER TABLE courses
     MODIFY COLUMN name ENUM(''GATE'',''PLACEMENT'',''JEE MAIN + ADVANCE'') NOT NULL',
  'DO 0');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF(@done = 0,
  'ALTER TABLE courses
     MODIFY COLUMN code ENUM(''CS'',''DS'',''EC'',''EE'',''ME'',''PLA'',''PLM'',''JEE'') NOT NULL',
  'DO 0');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ---------------------------------------------------------- course_content
-- Step 1: widen so old and new values are both legal.
SET @widen := (SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'course_content'
                  AND COLUMN_NAME = 'section' AND COLUMN_TYPE LIKE '%Mock Test%');

SET @sql := IF(@widen > 0,
  'ALTER TABLE course_content
     MODIFY COLUMN section ENUM(
       ''Mock Test'',''hnotes'',''vlecture'',''jcommunity'',
       ''mock_test'',''notes'',''lecture'',''community'',''blog'',
       ''coding_test'',''communication_test'',''aptitude_test'',
       ''coding_practice'',''question_practice''
     ) NOT NULL',
  'DO 0');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- Step 2: carry existing rows over to the new vocabulary.
UPDATE course_content SET section = 'mock_test'  WHERE section = 'Mock Test';
UPDATE course_content SET section = 'notes'      WHERE section = 'hnotes';
UPDATE course_content SET section = 'lecture'    WHERE section = 'vlecture';
UPDATE course_content SET section = 'community'  WHERE section = 'jcommunity';

-- Step 3: placement rows were all tagged 'Mock Test' regardless of what they
-- really were, because no better value existed. Re-tag them from the round the
-- description already points at, falling back to the title only where there is
-- no description row to read.
UPDATE course_content cc
   JOIN courses c ON c.code = cc.code
   SET cc.section = 'communication_test'
 WHERE c.name = 'PLACEMENT'
   AND cc.section = 'mock_test'
   AND EXISTS (SELECT 1 FROM comm_description d
                WHERE d.test_id = cc.section_id AND d.round_id IS NOT NULL);

UPDATE course_content cc
   JOIN courses c ON c.code = cc.code
   SET cc.section = 'coding_test'
 WHERE c.name = 'PLACEMENT'
   AND cc.section = 'mock_test'
   AND (LOWER(cc.title) LIKE '%coding%'
     OR LOWER(cc.title) LIKE '%programming%'
     OR LOWER(cc.title) LIKE '%technical%');

UPDATE course_content cc
   JOIN courses c ON c.code = cc.code
   SET cc.section = 'communication_test'
 WHERE c.name = 'PLACEMENT'
   AND cc.section = 'mock_test'
   AND (LOWER(cc.title) LIKE '%communication%' OR LOWER(cc.title) LIKE '%verbal%');

UPDATE course_content cc
   JOIN courses c ON c.code = cc.code
   SET cc.section = 'aptitude_test'
 WHERE c.name = 'PLACEMENT'
   AND cc.section = 'mock_test'
   AND (LOWER(cc.title) LIKE '%aptitude%' OR LOWER(cc.title) LIKE '%reasoning%'
     OR LOWER(cc.title) LIKE '%quant%' OR LOWER(cc.title) LIKE '%logical%');

-- Step 4: narrow to the final vocabulary — only when step 1 actually widened,
-- so a re-run does not touch a column that 013 has since put a foreign key on.
SET @narrow := (SELECT COUNT(*) FROM information_schema.COLUMNS
                 WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'course_content'
                   AND COLUMN_NAME = 'section' AND COLUMN_TYPE LIKE '%Mock Test%');

SET @sql := IF(@narrow > 0,
  'ALTER TABLE course_content
     MODIFY COLUMN section ENUM(
       ''mock_test'',''notes'',''lecture'',''community'',''blog'',
       ''coding_test'',''communication_test'',''aptitude_test'',
       ''coding_practice'',''question_practice''
     ) NOT NULL',
  'DO 0');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ------------------------------------------------- link coding tests to course
-- cp_tests was standalone: a coding test belonged to no course. These columns
-- attach it to one content block, the same way test_description.test_id and
-- comm_description.test_id already do.
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='cp_tests' AND COLUMN_NAME='test_id') = 0,
  'ALTER TABLE cp_tests
     ADD COLUMN test_id VARCHAR(100) NULL AFTER slug,
     ADD COLUMN code VARCHAR(100) NULL AFTER test_id,
     ADD COLUMN test_key VARCHAR(100) NULL AFTER code,
     ADD INDEX idx_cp_tests_content (test_id, code)',
  'SELECT "cp_tests already linked to course content" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
