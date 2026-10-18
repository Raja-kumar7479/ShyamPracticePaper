-- Shareable result: each submitted coding attempt can carry an unguessable
-- public code; /coding/certificate/<code> renders a verifiable certificate
-- without login. Idempotent: safe to re-run.

SET @db := DATABASE();

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='cp_attempts' AND COLUMN_NAME='share_code') = 0,
  'ALTER TABLE cp_attempts ADD COLUMN share_code VARCHAR(32) NULL,
     ADD UNIQUE KEY uq_cp_share_code (share_code)',
  'SELECT "share_code exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
