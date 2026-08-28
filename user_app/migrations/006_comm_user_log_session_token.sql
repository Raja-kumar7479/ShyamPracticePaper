-- Fixes: starting any placement assessment crashed with "Unknown column
-- 'session_token' in 'field list'". generate_session_token() and
-- validate_token() in proctor_db.py read/write comm_user_log.session_token
-- and token_expiry, but neither schema.sql nor the live table had the columns.
-- Idempotent: safe to re-run.

SET @db := DATABASE();

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'comm_user_log'
     AND COLUMN_NAME = 'session_token') = 0,
  'ALTER TABLE comm_user_log ADD COLUMN session_token VARCHAR(64) NULL AFTER status',
  'SELECT "session_token already exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'comm_user_log'
     AND COLUMN_NAME = 'token_expiry') = 0,
  'ALTER TABLE comm_user_log ADD COLUMN token_expiry DATETIME NULL AFTER session_token',
  'SELECT "token_expiry already exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
