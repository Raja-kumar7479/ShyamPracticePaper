-- Fixes: "Unknown column 'last_active' in 'field list'" logged on every profile
-- and dashboard view. update_last_active()/get_last_active_time() in
-- auth_db.py and profile_handler_db.py read and write this column.
-- Idempotent: safe to re-run.

SET @db := DATABASE();

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'auth'
     AND COLUMN_NAME = 'last_active') = 0,
  'ALTER TABLE auth ADD COLUMN last_active DATETIME NULL AFTER updated_at',
  'SELECT "last_active already exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
