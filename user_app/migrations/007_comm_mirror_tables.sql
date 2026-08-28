-- Restructures communication (placement) storage to mirror the mock-test tables:
--   test_description     -> comm_description
--   test_questions       -> comm_questions   (+ audio/speaking columns)
--   test_feedback        -> comm_feedback
--   test_result          -> comm_result
--   test_attempt_details -> comm_attempt_details (already existed)
--   user_test_log        -> comm_user_log        (already existed)
--
-- Communication test descriptions created by the admin panel were landing in
-- test_description (shared with competitive mock tests). This migration creates
-- the comm_* mirror tables and moves rows belonging to PLACEMENT-group courses
-- (courses.name = 'PLACEMENT') into them, keyed by test_key.
--
-- comm_description and comm_questions start AUTO_INCREMENT at 1000000 so their
-- ids never collide with test_description/test_questions ids — the admin panel
-- routes id-based API calls to the right table by that offset.
--
-- The legacy prototype tables (comm_test_definitions, comm_test_sections,
-- comm_test_questions) are dropped along with their sample data
-- (test_key 'SET_A'); nothing in the apps reads them any more.
--
-- assessment_rounds was originally dropped here too, but it was later promoted
-- to a real table: schema.sql creates it, comm_description.round_id has a
-- foreign key to it (fk_cd_round, added by 008) and proctor_db.py joins it.
-- The DROP only appeared to work because that foreign key blocked it; on a
-- fresh database it aborted provisioning with
-- "Cannot drop table 'assessment_rounds' referenced by a foreign key".

CREATE TABLE IF NOT EXISTS comm_description LIKE test_description;
ALTER TABLE comm_description AUTO_INCREMENT = 1000000;

CREATE TABLE IF NOT EXISTS comm_questions LIKE test_questions;
ALTER TABLE comm_questions AUTO_INCREMENT = 1000000;

SET @db := DATABASE();
SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'comm_questions' AND COLUMN_NAME = 'instruction_text') = 0,
  'ALTER TABLE comm_questions
     ADD COLUMN instruction_text TEXT NULL,
     ADD COLUMN media_url VARCHAR(255) NULL,
     ADD COLUMN options_title VARCHAR(100) NULL,
     ADD COLUMN recording_time_seconds INT DEFAULT 0,
     ADD COLUMN thinking_time_seconds INT DEFAULT 0,
     ADD COLUMN word_limit INT DEFAULT 0,
     ADD COLUMN sub_questions JSON NULL',
  'SELECT "comm_questions extras already exist" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

CREATE TABLE IF NOT EXISTS comm_feedback LIKE test_feedback;
CREATE TABLE IF NOT EXISTS comm_result LIKE test_result;

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
   WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'comm_questions' AND CONSTRAINT_NAME = 'fk_comm_question_desc') = 0,
  'ALTER TABLE comm_questions ADD CONSTRAINT fk_comm_question_desc FOREIGN KEY (test_key) REFERENCES comm_description(test_key) ON DELETE CASCADE',
  'SELECT "fk exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- Move communication descriptions (PLACEMENT-group courses) out of test_description.
INSERT INTO comm_description
    (test_id, code, test_key, subject_title, subject_subtitle,
     total_questions, total_marks, total_duration_minutes, created_at, updated_at)
SELECT td.test_id, td.code, td.test_key, td.subject_title, td.subject_subtitle,
       td.total_questions, td.total_marks, td.total_duration_minutes, td.created_at, td.updated_at
FROM test_description td
JOIN course_content cc ON cc.section_id = td.test_id
JOIN courses c ON c.code = cc.code
WHERE UPPER(c.name) = 'PLACEMENT'
  AND td.test_key NOT IN (SELECT test_key FROM comm_description);

INSERT INTO comm_questions
    (test_id, test_key, test_description_id, section_id, section_name, question_number,
     question_type, question_text, option_a, option_b, option_c, option_d,
     correct_option, correct_marks, negative_marks, question_level,
     answer_text, answer_link, created_at, updated_at)
SELECT tq.test_id, tq.test_key, cd.id, tq.section_id, tq.section_name, tq.question_number,
       tq.question_type, tq.question_text, tq.option_a, tq.option_b, tq.option_c, tq.option_d,
       tq.correct_option, tq.correct_marks, tq.negative_marks, tq.question_level,
       tq.answer_text, tq.answer_link, tq.created_at, tq.updated_at
FROM test_questions tq
JOIN comm_description cd ON cd.test_key = tq.test_key
WHERE tq.id NOT IN (SELECT id FROM comm_questions);

DELETE FROM test_questions WHERE test_key IN (SELECT test_key FROM comm_description);
DELETE FROM test_description WHERE test_key IN (SELECT test_key FROM comm_description);

-- Legacy prototype data and tables.
DELETE FROM comm_attempt_details WHERE test_key = 'SET_A';
DELETE FROM comm_user_log WHERE test_key = 'SET_A';
DELETE FROM comm_proctoring_logs WHERE test_key = 'SET_A';
DROP TABLE IF EXISTS comm_test_questions;
DROP TABLE IF EXISTS comm_test_sections;
DROP TABLE IF EXISTS comm_test_definitions;
