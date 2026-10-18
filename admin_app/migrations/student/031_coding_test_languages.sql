SET @db := DATABASE();

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='cp_tests' AND COLUMN_NAME='allowed_languages') = 0,
  'ALTER TABLE cp_tests ADD COLUMN allowed_languages VARCHAR(255) NULL AFTER total_duration_min',
  'SELECT "cp_tests allowed_languages exists" AS note');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
