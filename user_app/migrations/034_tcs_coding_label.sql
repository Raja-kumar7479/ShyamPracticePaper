SET @db := DATABASE();

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='tcs_exams' AND COLUMN_NAME='coding_label') = 0,
  'ALTER TABLE tcs_exams ADD COLUMN coding_label VARCHAR(100) NULL AFTER coding_test_id',
  'SELECT "tcs_exams coding_label exists" AS note');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
