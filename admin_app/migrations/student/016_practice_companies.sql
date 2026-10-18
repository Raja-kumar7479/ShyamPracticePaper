-- Company tags for practice questions: the "Trending Companies" rail becomes
-- real data, and each company gets its own question-bank page.
--
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS pcp_companies (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(80) NOT NULL,
  slug VARCHAR(90) NOT NULL UNIQUE,
  position INT DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_pcp_company_name (name)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS pcp_question_companies (
  question_id INT NOT NULL,
  company_id INT NOT NULL,
  PRIMARY KEY (question_id, company_id),
  FOREIGN KEY (question_id) REFERENCES pcp_questions(id) ON DELETE CASCADE,
  FOREIGN KEY (company_id) REFERENCES pcp_companies(id) ON DELETE CASCADE,
  INDEX idx_pcp_qc_company (company_id)
) ENGINE=InnoDB;
