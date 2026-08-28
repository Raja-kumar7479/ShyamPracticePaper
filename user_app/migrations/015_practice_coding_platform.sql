-- Practice Coding Platform (pcp_*): a LeetCode-style question bank, separate
-- from the exam portal's cp_* tables on purpose - practice questions, solves
-- and subscriptions must never mix with proctored exam data.
--
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS pcp_questions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  title VARCHAR(255) NOT NULL,
  difficulty ENUM('Easy','Moderate','Hard') NOT NULL DEFAULT 'Easy',
  subject VARCHAR(60) NOT NULL DEFAULT 'General',
  statement_html TEXT NULL,
  input_spec TEXT NULL,
  example_html TEXT NULL,
  statement_image VARCHAR(255) NULL,
  input_image VARCHAR(255) NULL,
  example_image VARCHAR(255) NULL,
  allowed_languages VARCHAR(255) DEFAULT 'python,java,c,cpp,csharp,javascript',
  output_spec TEXT NULL,
  time_limit_sec INT DEFAULT 10,
  memory_limit VARCHAR(20) DEFAULT '512m',
  is_paid TINYINT(1) NOT NULL DEFAULT 0,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  position INT DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_pcp_subject (subject, is_active),
  INDEX idx_pcp_paid (is_paid, is_active)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS pcp_testcases (
  id INT AUTO_INCREMENT PRIMARY KEY,
  question_id INT NOT NULL,
  input_text MEDIUMTEXT,
  expected_output MEDIUMTEXT,
  is_hidden TINYINT(1) DEFAULT 0,
  position INT DEFAULT 0,
  FOREIGN KEY (question_id) REFERENCES pcp_questions(id) ON DELETE CASCADE,
  INDEX idx_pcp_tc (question_id, position)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS pcp_templates (
  id INT AUTO_INCREMENT PRIMARY KEY,
  question_id INT NOT NULL,
  language ENUM('python','java','c','cpp','csharp','javascript') NOT NULL,
  template_code MEDIUMTEXT,
  UNIQUE KEY uq_pcp_tpl (question_id, language),
  FOREIGN KEY (question_id) REFERENCES pcp_questions(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS pcp_submissions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  question_id INT NOT NULL,
  language VARCHAR(20),
  code MEDIUMTEXT,
  verdict ENUM('AC','WA','TLE','MLE','CE','RE','IE') DEFAULT 'WA',
  passed INT DEFAULT 0,
  total INT DEFAULT 0,
  execution_time FLOAT DEFAULT 0,
  error_message TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES auth(id) ON DELETE CASCADE,
  FOREIGN KEY (question_id) REFERENCES pcp_questions(id) ON DELETE CASCADE,
  INDEX idx_pcp_sub_user (user_id, question_id, verdict)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS pcp_subscriptions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  plan ENUM('monthly','yearly') NOT NULL,
  amount_paise INT NOT NULL,
  razorpay_order_id VARCHAR(100) NOT NULL UNIQUE,
  razorpay_payment_id VARCHAR(100) NULL,
  status ENUM('created','active','failed') NOT NULL DEFAULT 'created',
  starts_at DATETIME NULL,
  expires_at DATETIME NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_pcp_sub_email (email, status, expires_at)
) ENGINE=InnoDB;

-- The section goes live: dashboards route through the catalog, so this single
-- row change is what turns "coming soon" into a working portal.
UPDATE content_sections
   SET portal = 'coding_practice',
       is_available = 1,
       help_text = 'LeetCode-style practice problems. Opens the coding practice portal.'
 WHERE section_key = 'coding_practice';
