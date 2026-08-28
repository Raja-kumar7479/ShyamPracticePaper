-- MCQ quiz/assessment bank for the practice platform (pcq_*).
--
-- Correct answers live only in pcq_questions and are graded server-side; the
-- attempt tables exist so the review page can replay exactly what the student
-- picked against what was right.
--
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS pcq_questions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  subject VARCHAR(60) NOT NULL,
  question_text TEXT NULL,
  question_image VARCHAR(255) NULL,
  option_a TEXT NOT NULL,
  option_b TEXT NOT NULL,
  option_c TEXT NOT NULL,
  option_d TEXT NOT NULL,
  correct_option ENUM('A','B','C','D') NOT NULL,
  explanation TEXT NULL,
  is_paid TINYINT(1) NOT NULL DEFAULT 0,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  position INT DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_pcq_subject (subject, is_active, is_paid)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS pcq_attempts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  subject VARCHAR(60) NOT NULL,
  mode ENUM('quiz','assessment') NOT NULL,
  status ENUM('in_progress','finished') NOT NULL DEFAULT 'in_progress',
  total INT DEFAULT 0,
  correct INT DEFAULT 0,
  wrong INT DEFAULT 0,
  skipped INT DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  finished_at DATETIME NULL,
  FOREIGN KEY (user_id) REFERENCES auth(id) ON DELETE CASCADE,
  INDEX idx_pcq_att_user (user_id, subject, status)
) ENGINE=InnoDB;

-- One row per answered question. The unique key is the assessment-mode lock:
-- a second answer for the same question is refused by the database itself.
CREATE TABLE IF NOT EXISTS pcq_attempt_answers (
  id INT AUTO_INCREMENT PRIMARY KEY,
  attempt_id INT NOT NULL,
  question_id INT NOT NULL,
  selected ENUM('A','B','C','D') NULL,
  is_correct TINYINT(1) NOT NULL DEFAULT 0,
  UNIQUE KEY uq_pcq_answer (attempt_id, question_id),
  FOREIGN KEY (attempt_id) REFERENCES pcq_attempts(id) ON DELETE CASCADE,
  FOREIGN KEY (question_id) REFERENCES pcq_questions(id) ON DELETE CASCADE
) ENGINE=InnoDB;
