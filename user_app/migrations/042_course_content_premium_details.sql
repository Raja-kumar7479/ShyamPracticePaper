SET @db := DATABASE();

-- What the admin wants a student to read before subscribing to premium for
-- this content block. Rich text from the same editor as `details`; the
-- placeholder [[SUBSCRIBE]] inside it is replaced by the real Subscribe
-- button, so the admin decides where that button sits.
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='course_content' AND COLUMN_NAME='premium_details') = 0,
  'ALTER TABLE course_content ADD COLUMN premium_details MEDIUMTEXT NULL AFTER details',
  'SELECT "course_content premium_details exists" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
