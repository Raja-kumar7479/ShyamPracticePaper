-- Assessment platform schema. Idempotent: safe to run on every boot.

CREATE TABLE IF NOT EXISTS cp_tests (
  id INT AUTO_INCREMENT PRIMARY KEY,
  slug VARCHAR(120) UNIQUE NOT NULL,
  title VARCHAR(255) NOT NULL,
  description TEXT,
  total_duration_min INT DEFAULT 60,
  is_published BOOLEAN DEFAULT FALSE,
  created_by INT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (created_by) REFERENCES auth(id) ON DELETE CASCADE,
  INDEX idx_slug (slug)
);

-- section_type decides which question type renders. A coding section can only
-- ever contain coding questions; the UI and the API both gate on this column.
CREATE TABLE IF NOT EXISTS cp_sections (
  id INT AUTO_INCREMENT PRIMARY KEY,
  test_id INT NOT NULL,
  title VARCHAR(255) NOT NULL,
  section_type ENUM('coding','sql','web') NOT NULL,
  duration_min INT DEFAULT 30,
  position INT DEFAULT 0,
  FOREIGN KEY (test_id) REFERENCES cp_tests(id) ON DELETE CASCADE,
  INDEX idx_test (test_id, position)
);

CREATE TABLE IF NOT EXISTS cp_questions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  section_id INT NOT NULL,
  position INT DEFAULT 0,
  title VARCHAR(255) NOT NULL,
  statement_html TEXT,
  marks INT DEFAULT 10,
  time_limit_sec INT DEFAULT 10,
  memory_limit VARCHAR(20) DEFAULT '512m',

  -- coding
  allowed_languages VARCHAR(255) DEFAULT 'python,java,c,cpp,csharp,javascript',
  output_spec TEXT,

  -- sql
  schema_image_path VARCHAR(255),
  sandbox_schema_sql MEDIUMTEXT,
  solution_query TEXT,
  ordered_comparison BOOLEAN DEFAULT FALSE,

  -- web
  starter_html MEDIUMTEXT,
  starter_css MEDIUMTEXT,
  starter_js MEDIUMTEXT,

  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (section_id) REFERENCES cp_sections(id) ON DELETE CASCADE,
  INDEX idx_section (section_id, position)
);

CREATE TABLE IF NOT EXISTS cp_question_templates (
  id INT AUTO_INCREMENT PRIMARY KEY,
  question_id INT NOT NULL,
  language ENUM('python','java','c','cpp','csharp','javascript') NOT NULL,
  template_code MEDIUMTEXT,
  UNIQUE KEY uq_question_lang (question_id, language),
  FOREIGN KEY (question_id) REFERENCES cp_questions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cp_testcases (
  id INT AUTO_INCREMENT PRIMARY KEY,
  question_id INT NOT NULL,
  input_text MEDIUMTEXT,
  expected_output MEDIUMTEXT,
  is_hidden BOOLEAN DEFAULT FALSE,
  position INT DEFAULT 0,
  FOREIGN KEY (question_id) REFERENCES cp_questions(id) ON DELETE CASCADE,
  INDEX idx_question (question_id, position)
);

CREATE TABLE IF NOT EXISTS cp_web_assertions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  question_id INT NOT NULL,
  kind ENUM('element_exists','text_equals','text_contains',
            'attr_equals','css_property','count_equals') NOT NULL,
  selector VARCHAR(255) NOT NULL,
  property_name VARCHAR(100),
  expected_value TEXT,
  message VARCHAR(255),
  is_hidden BOOLEAN DEFAULT FALSE,
  position INT DEFAULT 0,
  FOREIGN KEY (question_id) REFERENCES cp_questions(id) ON DELETE CASCADE,
  INDEX idx_question (question_id, position)
);

CREATE TABLE IF NOT EXISTS cp_attempts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  test_id INT NOT NULL,
  user_id INT NOT NULL,
  status ENUM('in_progress','submitted','expired') DEFAULT 'in_progress',
  -- Furthest question reached (linear index across the whole test).
  -- Navigation is forward-only: anything before this is locked.
  progress_idx INT NOT NULL DEFAULT 0,
  started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  submitted_at TIMESTAMP NULL,
  UNIQUE KEY uq_test_user (test_id, user_id),
  FOREIGN KEY (test_id) REFERENCES cp_tests(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES auth(id) ON DELETE CASCADE,
  INDEX idx_user (user_id)
);

-- Autosave target. Kept apart from cp_submissions` so saving a draft every few
-- seconds never creates graded rows.
CREATE TABLE IF NOT EXISTS cp_answers (
  id INT AUTO_INCREMENT PRIMARY KEY,
  attempt_id INT NOT NULL,
  question_id INT NOT NULL,
  language ENUM('python','java','c','cpp','csharp','javascript') NULL,
  code MEDIUMTEXT,
  code_html MEDIUMTEXT,
  code_css MEDIUMTEXT,
  code_js MEDIUMTEXT,
  is_attempted BOOLEAN DEFAULT FALSE,
  last_saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_attempt_question (attempt_id, question_id),
  FOREIGN KEY (attempt_id) REFERENCES cp_attempts(id) ON DELETE CASCADE,
  FOREIGN KEY (question_id) REFERENCES cp_questions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cp_submissions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  attempt_id INT NOT NULL,
  question_id INT NOT NULL,
  language VARCHAR(20),
  code MEDIUMTEXT,
  verdict ENUM('AC','WA','TLE','MLE','CE','RE','IE') DEFAULT 'WA',
  passed INT DEFAULT 0,
  total INT DEFAULT 0,
  score INT DEFAULT 0,
  execution_time FLOAT DEFAULT 0,
  error_message TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (attempt_id) REFERENCES cp_attempts(id) ON DELETE CASCADE,
  FOREIGN KEY (question_id) REFERENCES cp_questions(id) ON DELETE CASCADE,
  INDEX idx_attempt (attempt_id),
  INDEX idx_question (question_id)
);

CREATE TABLE IF NOT EXISTS cp_submission_testcases (
  id INT AUTO_INCREMENT PRIMARY KEY,
  submission_id INT NOT NULL,
  testcase_id INT NULL,
  status ENUM('PASS','FAIL','TLE','MLE','RE') DEFAULT 'FAIL',
  execution_time FLOAT DEFAULT 0,
  output MEDIUMTEXT,
  error_message TEXT,
  FOREIGN KEY (submission_id) REFERENCES cp_submissions(id) ON DELETE CASCADE,
  INDEX idx_submission (submission_id)
);
