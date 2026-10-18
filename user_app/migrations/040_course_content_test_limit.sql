SET @db := DATABASE();

-- Optional cap on how many test descriptions a content block may hold.
-- NULL means unlimited; the admin API refuses the (cap + 1)th description.
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='course_content' AND COLUMN_NAME='max_test_descriptions') = 0,
  'ALTER TABLE course_content ADD COLUMN max_test_descriptions INT UNSIGNED NULL DEFAULT NULL AFTER syllabus_label',
  'SELECT "course_content max_test_descriptions exists" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
