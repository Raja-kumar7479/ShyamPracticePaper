SET @db := DATABASE();

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='cp_answers' AND COLUMN_NAME='is_review') = 0,
  'ALTER TABLE cp_answers ADD COLUMN is_review TINYINT(1) NOT NULL DEFAULT 0 AFTER is_attempted',
  'SELECT "cp_answers is_review exists" AS note');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
