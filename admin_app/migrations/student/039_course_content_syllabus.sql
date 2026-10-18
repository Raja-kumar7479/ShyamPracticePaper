SET @db := DATABASE();

-- Optional syllabus PDF for a content block, and where the admin wants its
-- link to sit relative to the description on the student's page.
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='course_content' AND COLUMN_NAME='syllabus_url') = 0,
  'ALTER TABLE course_content ADD COLUMN syllabus_url VARCHAR(500) NULL AFTER image_url',
  'SELECT "course_content syllabus_url exists" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='course_content' AND COLUMN_NAME='syllabus_position') = 0,
  'ALTER TABLE course_content ADD COLUMN syllabus_position ENUM(''above'',''below'') NOT NULL DEFAULT ''below'' AFTER syllabus_url',
  'SELECT "course_content syllabus_position exists" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='course_content' AND COLUMN_NAME='syllabus_label') = 0,
  'ALTER TABLE course_content ADD COLUMN syllabus_label VARCHAR(120) NULL AFTER syllabus_position',
  'SELECT "course_content syllabus_label exists" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
