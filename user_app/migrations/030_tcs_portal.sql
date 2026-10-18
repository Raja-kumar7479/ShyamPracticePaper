CREATE TABLE IF NOT EXISTS tcs_exams (
  id INT AUTO_INCREMENT PRIMARY KEY,
  section_id VARCHAR(100) NOT NULL,
  code VARCHAR(100) NOT NULL,
  title VARCHAR(200) NOT NULL,
  subtitle VARCHAR(255) NULL,
  aptitude_test_key VARCHAR(100) NOT NULL,
  coding_test_id INT NOT NULL,
  is_published TINYINT(1) NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_tcs_exams_section (section_id),
  KEY idx_tcs_exams_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS tcs_attempts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tcs_exam_id INT NOT NULL,
  email VARCHAR(255) NOT NULL,
  stage ENUM('aptitude','coding','completed') NOT NULL DEFAULT 'aptitude',
  aptitude_attempt_number INT NULL,
  coding_attempt_id INT NULL,
  started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  aptitude_done_at TIMESTAMP NULL,
  completed_at TIMESTAMP NULL,
  UNIQUE KEY uq_tcs_attempt (tcs_exam_id, email),
  KEY idx_tcs_attempts_email (email),
  CONSTRAINT fk_tcs_attempt_exam FOREIGN KEY (tcs_exam_id) REFERENCES tcs_exams(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO content_sections (section_key, label, help_text, portal, editor, is_available, position) VALUES
  ('tcs_test', 'TCS NQT Exam', 'Full placement exam: aptitude sections in the mock-test window followed by a coding section in the coding editor. Opens the TCS portal.', 'tcs', 'competitive', 1, 3)
ON DUPLICATE KEY UPDATE
  label = VALUES(label), help_text = VALUES(help_text), portal = VALUES(portal),
  editor = VALUES(editor), is_available = VALUES(is_available);
