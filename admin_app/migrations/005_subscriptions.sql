SET @db := DATABASE();

SET @s := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='test_description' AND COLUMN_NAME='access_label')=0,
    'ALTER TABLE test_description ADD COLUMN access_label ENUM(''inherit'',''free'',''paid'') NOT NULL DEFAULT ''inherit''',
    'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @s := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='comm_description' AND COLUMN_NAME='access_label')=0,
    'ALTER TABLE comm_description ADD COLUMN access_label ENUM(''inherit'',''free'',''paid'') NOT NULL DEFAULT ''inherit''',
    'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @s := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='cp_tests' AND COLUMN_NAME='access_label')=0,
    'ALTER TABLE cp_tests ADD COLUMN access_label ENUM(''inherit'',''free'',''paid'') NOT NULL DEFAULT ''inherit''',
    'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
