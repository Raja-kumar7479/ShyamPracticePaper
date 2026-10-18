SET @db := DATABASE();

-- A test's key now encodes its access (free_/prem_), so switching an unused
-- test between Free and Premium re-issues the key. Every child of a
-- description already follows a key change (ON UPDATE CASCADE) except the
-- question/section tables, whose keys were NO ACTION and blocked the update.

-- test_questions.test_key -> test_description.test_key: follow a key change like every other child.
SET @cname := (SELECT k.CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE k
    WHERE k.TABLE_SCHEMA=@db AND k.TABLE_NAME='test_questions' AND k.COLUMN_NAME='test_key'
      AND k.REFERENCED_TABLE_NAME='test_description' AND k.REFERENCED_COLUMN_NAME='test_key' LIMIT 1);
SET @needs := (SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS r
    JOIN information_schema.KEY_COLUMN_USAGE k
      ON k.CONSTRAINT_NAME = r.CONSTRAINT_NAME AND k.TABLE_SCHEMA = r.CONSTRAINT_SCHEMA
    WHERE k.TABLE_SCHEMA=@db AND r.TABLE_NAME='test_questions' AND k.COLUMN_NAME='test_key'
      AND k.REFERENCED_TABLE_NAME='test_description' AND r.UPDATE_RULE IN ('NO ACTION', 'RESTRICT'));
SET @sql := IF(@needs > 0, CONCAT('ALTER TABLE test_questions DROP FOREIGN KEY ', @cname),
  'SELECT "test_questions test_key already cascades on update" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql := IF(@needs > 0, CONCAT('ALTER TABLE test_questions ADD CONSTRAINT ', @cname,
         ' FOREIGN KEY (test_key) REFERENCES test_description(test_key) ON DELETE CASCADE ON UPDATE CASCADE'),
  'SELECT "test_questions test_key already cascades on update" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- comm_questions.test_key -> comm_description.test_key: follow a key change like every other child.
SET @cname := (SELECT k.CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE k
    WHERE k.TABLE_SCHEMA=@db AND k.TABLE_NAME='comm_questions' AND k.COLUMN_NAME='test_key'
      AND k.REFERENCED_TABLE_NAME='comm_description' AND k.REFERENCED_COLUMN_NAME='test_key' LIMIT 1);
SET @needs := (SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS r
    JOIN information_schema.KEY_COLUMN_USAGE k
      ON k.CONSTRAINT_NAME = r.CONSTRAINT_NAME AND k.TABLE_SCHEMA = r.CONSTRAINT_SCHEMA
    WHERE k.TABLE_SCHEMA=@db AND r.TABLE_NAME='comm_questions' AND k.COLUMN_NAME='test_key'
      AND k.REFERENCED_TABLE_NAME='comm_description' AND r.UPDATE_RULE IN ('NO ACTION', 'RESTRICT'));
SET @sql := IF(@needs > 0, CONCAT('ALTER TABLE comm_questions DROP FOREIGN KEY ', @cname),
  'SELECT "comm_questions test_key already cascades on update" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql := IF(@needs > 0, CONCAT('ALTER TABLE comm_questions ADD CONSTRAINT ', @cname,
         ' FOREIGN KEY (test_key) REFERENCES comm_description(test_key) ON DELETE CASCADE ON UPDATE CASCADE'),
  'SELECT "comm_questions test_key already cascades on update" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- comm_sections.test_key -> comm_description.test_key: follow a key change like every other child.
SET @cname := (SELECT k.CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE k
    WHERE k.TABLE_SCHEMA=@db AND k.TABLE_NAME='comm_sections' AND k.COLUMN_NAME='test_key'
      AND k.REFERENCED_TABLE_NAME='comm_description' AND k.REFERENCED_COLUMN_NAME='test_key' LIMIT 1);
SET @needs := (SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS r
    JOIN information_schema.KEY_COLUMN_USAGE k
      ON k.CONSTRAINT_NAME = r.CONSTRAINT_NAME AND k.TABLE_SCHEMA = r.CONSTRAINT_SCHEMA
    WHERE k.TABLE_SCHEMA=@db AND r.TABLE_NAME='comm_sections' AND k.COLUMN_NAME='test_key'
      AND k.REFERENCED_TABLE_NAME='comm_description' AND r.UPDATE_RULE IN ('NO ACTION', 'RESTRICT'));
SET @sql := IF(@needs > 0, CONCAT('ALTER TABLE comm_sections DROP FOREIGN KEY ', @cname),
  'SELECT "comm_sections test_key already cascades on update" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql := IF(@needs > 0, CONCAT('ALTER TABLE comm_sections ADD CONSTRAINT ', @cname,
         ' FOREIGN KEY (test_key) REFERENCES comm_description(test_key) ON DELETE CASCADE ON UPDATE CASCADE'),
  'SELECT "comm_sections test_key already cascades on update" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
