-- Communication assessment structure upgrade (reference schema mapped onto the
-- EXISTING comm_* tables — table names unchanged):
--   assessment_rounds        -> recreated with round_type ENUM (COMM/CODING/APTITUDE/APTITUDE_CODING)
--   comm_test_definitions    -> comm_description (adds round_id, requires_seb, difficulty_level)
--   comm_test_sections       -> comm_sections (NEW: real per-section title/instruction/duration/order)
--   comm_test_questions      -> comm_questions (question_type becomes ENUM of the portal's UI types)
--   comm_user_log / comm_attempt_details / comm_proctoring_logs already match.
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS assessment_rounds (
    id INT AUTO_INCREMENT PRIMARY KEY,
    round_name VARCHAR(50),
    round_type ENUM('COMM','CODING','APTITUDE','APTITUDE_CODING') NOT NULL DEFAULT 'COMM',
    round_description TEXT,
    is_active TINYINT DEFAULT 1
) ENGINE=InnoDB;

INSERT INTO assessment_rounds (round_name, round_type, round_description, is_active)
SELECT 'Communication', 'COMM', 'Verbal and Audio Assessments', 1
WHERE NOT EXISTS (SELECT 1 FROM assessment_rounds WHERE round_type = 'COMM');
INSERT INTO assessment_rounds (round_name, round_type, round_description, is_active)
SELECT 'Aptitude', 'APTITUDE', 'Logical and Quantitative Assessments', 1
WHERE NOT EXISTS (SELECT 1 FROM assessment_rounds WHERE round_type = 'APTITUDE');
INSERT INTO assessment_rounds (round_name, round_type, round_description, is_active)
SELECT 'Coding', 'CODING', 'Programming and Technical Assessments', 1
WHERE NOT EXISTS (SELECT 1 FROM assessment_rounds WHERE round_type = 'CODING');

SET @db := DATABASE();

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='comm_description' AND COLUMN_NAME='round_id') = 0,
  'ALTER TABLE comm_description ADD COLUMN round_id INT NULL,
     ADD COLUMN requires_seb TINYINT DEFAULT 0,
     ADD COLUMN difficulty_level VARCHAR(20) DEFAULT ''Medium'',
     ADD CONSTRAINT fk_cd_round FOREIGN KEY (round_id) REFERENCES assessment_rounds(id) ON DELETE SET NULL',
  'SELECT "comm_description round columns exist" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

UPDATE comm_description cd
JOIN assessment_rounds r ON r.round_type = 'COMM'
SET cd.round_id = r.id
WHERE cd.round_id IS NULL;

CREATE TABLE IF NOT EXISTS comm_sections (
    id INT AUTO_INCREMENT PRIMARY KEY,
    test_key VARCHAR(100) NOT NULL,
    section_id VARCHAR(50),
    section_name VARCHAR(50),
    section_title VARCHAR(100),
    section_instruction TEXT,
    section_duration_seconds INT,
    section_order INT,
    INDEX idx_cs_test_key (test_key),
    CONSTRAINT fk_cs_desc FOREIGN KEY (test_key) REFERENCES comm_description(test_key) ON DELETE CASCADE
) ENGINE=InnoDB;

-- The portal UI branches on these exact types; enforce them.
UPDATE comm_questions
SET question_type = 'MCQ'
WHERE question_type IS NULL
   OR UPPER(question_type) NOT IN ('MCQ','SPEAK','THINK_SPEAK','WRITING','COMPREHENSION','LISTEN_SPEAK','FILL_BLANK');
UPDATE comm_questions SET question_type = UPPER(question_type);
ALTER TABLE comm_questions
    MODIFY question_type ENUM('MCQ','SPEAK','THINK_SPEAK','WRITING','COMPREHENSION','LISTEN_SPEAK','FILL_BLANK') NOT NULL DEFAULT 'MCQ';
