-- Fixes: Communication round page showed "No assessments currently available"
-- because comm_test_definitions.round_id was NULL, and get_assessments_by_round()
-- filters through assessment_rounds via that FK (JOIN on d.round_id = r.id).
--
-- assessment_rounds already contains the Communication round (round_type='COMM').
-- All existing comm_test_definitions rows are communication assessments
-- (test_id 'COMM_%'), so linking NULL rows to the COMM round is correct.
--
-- comm_test_definitions and assessment_rounds are legacy tables: 007 migrates
-- their data into comm_description / comm_questions and drops them, and
-- schema.sql no longer creates them. On a fresh database there is nothing to
-- link, so this runs only when both tables are actually present. Without that
-- guard, provisioning a new environment failed here with
-- "Table 'comm_test_definitions' doesn't exist".
--
-- Idempotent: safe to re-run.

SET @legacy := (SELECT COUNT(*) FROM information_schema.TABLES
                 WHERE TABLE_SCHEMA = DATABASE()
                   AND TABLE_NAME IN ('comm_test_definitions', 'assessment_rounds'));

SET @sql := IF(@legacy = 2,
    'UPDATE comm_test_definitions d
       JOIN assessment_rounds r ON r.round_type = ''COMM''
        SET d.round_id = r.id
      WHERE d.round_id IS NULL AND d.test_id LIKE ''COMM%''',
    'DO 0');

PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
