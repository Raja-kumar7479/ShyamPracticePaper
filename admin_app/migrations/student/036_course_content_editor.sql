SET @db := DATABASE();

-- The preview link was never shown to students; the cover image and the rich
-- description replaced it.
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='course_content' AND COLUMN_NAME='preview_url') = 1,
  'ALTER TABLE course_content DROP COLUMN preview_url',
  'SELECT "course_content preview_url already dropped" AS note');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Details now hold formatted HTML (headings, tables, images), so TEXT's 64 KB
-- is no longer a comfortable ceiling.
SET @sql := IF((SELECT DATA_TYPE FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='course_content' AND COLUMN_NAME='details') = 'text',
  'ALTER TABLE course_content MODIFY COLUMN details MEDIUMTEXT NULL',
  'SELECT "course_content details already widened" AS note');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
