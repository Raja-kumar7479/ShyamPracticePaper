-- Shareable communication result: each completed assessment can carry an
-- unguessable public code for its verification certificate. Idempotent.

SET @db := DATABASE();

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='comm_user_log' AND COLUMN_NAME='share_code') = 0,
  'ALTER TABLE comm_user_log ADD COLUMN share_code VARCHAR(32) NULL,
     ADD UNIQUE KEY uq_comm_share_code (share_code)',
  'SELECT "share_code exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
