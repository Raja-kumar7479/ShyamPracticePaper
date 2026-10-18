-- A student's attempts, answers, feedback and results are their own record of
-- work. Every one of these tables cascaded off test_description, so deleting a
-- test silently erased the history of everyone who had taken it. They become
-- RESTRICT: the delete is refused at the database, whatever code asks for it.
--
-- test_questions keeps ON DELETE CASCADE on purpose: questions belong to the
-- test, not to the student, and removing a test should take its questions.

-- test_result
SET @sql := IF((SELECT r.DELETE_RULE FROM information_schema.REFERENTIAL_CONSTRAINTS r
    WHERE r.CONSTRAINT_SCHEMA=DATABASE() AND r.CONSTRAINT_NAME='fk_test_result_desc') = 'CASCADE',
  'ALTER TABLE test_result DROP FOREIGN KEY fk_test_result_desc',
  'SELECT "test_result already protected" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS r
    WHERE r.CONSTRAINT_SCHEMA=DATABASE() AND r.CONSTRAINT_NAME='fk_test_result_desc') = 0,
  'ALTER TABLE test_result ADD CONSTRAINT fk_test_result_desc FOREIGN KEY (test_key) REFERENCES test_description(test_key) ON DELETE RESTRICT ON UPDATE CASCADE',
  'SELECT "test_result constraint present" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- user_test_log
SET @sql := IF((SELECT r.DELETE_RULE FROM information_schema.REFERENTIAL_CONSTRAINTS r
    WHERE r.CONSTRAINT_SCHEMA=DATABASE() AND r.CONSTRAINT_NAME='fk_user_log_desc') = 'CASCADE',
  'ALTER TABLE user_test_log DROP FOREIGN KEY fk_user_log_desc',
  'SELECT "user_test_log already protected" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS r
    WHERE r.CONSTRAINT_SCHEMA=DATABASE() AND r.CONSTRAINT_NAME='fk_user_log_desc') = 0,
  'ALTER TABLE user_test_log ADD CONSTRAINT fk_user_log_desc FOREIGN KEY (test_key) REFERENCES test_description(test_key) ON DELETE RESTRICT ON UPDATE CASCADE',
  'SELECT "user_test_log constraint present" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- test_attempt_details
SET @sql := IF((SELECT r.DELETE_RULE FROM information_schema.REFERENTIAL_CONSTRAINTS r
    WHERE r.CONSTRAINT_SCHEMA=DATABASE() AND r.CONSTRAINT_NAME='fk_attempt_desc') = 'CASCADE',
  'ALTER TABLE test_attempt_details DROP FOREIGN KEY fk_attempt_desc',
  'SELECT "test_attempt_details already protected" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS r
    WHERE r.CONSTRAINT_SCHEMA=DATABASE() AND r.CONSTRAINT_NAME='fk_attempt_desc') = 0,
  'ALTER TABLE test_attempt_details ADD CONSTRAINT fk_attempt_desc FOREIGN KEY (test_key) REFERENCES test_description(test_key) ON DELETE RESTRICT ON UPDATE CASCADE',
  'SELECT "test_attempt_details constraint present" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- test_feedback
SET @sql := IF((SELECT r.DELETE_RULE FROM information_schema.REFERENTIAL_CONSTRAINTS r
    WHERE r.CONSTRAINT_SCHEMA=DATABASE() AND r.CONSTRAINT_NAME='fk_feedback_desc') = 'CASCADE',
  'ALTER TABLE test_feedback DROP FOREIGN KEY fk_feedback_desc',
  'SELECT "test_feedback already protected" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS r
    WHERE r.CONSTRAINT_SCHEMA=DATABASE() AND r.CONSTRAINT_NAME='fk_feedback_desc') = 0,
  'ALTER TABLE test_feedback ADD CONSTRAINT fk_feedback_desc FOREIGN KEY (test_key) REFERENCES test_description(test_key) ON DELETE RESTRICT ON UPDATE CASCADE',
  'SELECT "test_feedback constraint present" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
