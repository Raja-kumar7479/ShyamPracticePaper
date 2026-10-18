SET @db := DATABASE();
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='notes_content' AND COLUMN_NAME='access_label') = 0,
  'ALTER TABLE notes_content ADD COLUMN access_label ENUM(''free'',''paid'') NOT NULL DEFAULT ''free'' AFTER type',
  'SELECT "notes access_label exists" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
