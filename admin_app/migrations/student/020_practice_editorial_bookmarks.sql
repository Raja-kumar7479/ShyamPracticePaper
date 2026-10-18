-- Editorial solutions and bookmarks for practice coding problems.
--
-- An editorial is a list of approaches (brute force, better, optimal...). Each
-- approach carries a title, an explanation before the code, the same solution
-- in several languages, and a closing note (complexity analysis, and so on).
-- The per-language code lives in its own table so a language can be added to
-- an approach without rewriting the approach row.
--
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS pcp_editorials (
    id INT AUTO_INCREMENT PRIMARY KEY,
    question_id INT NOT NULL,
    position INT NOT NULL DEFAULT 0,
    title VARCHAR(255) NOT NULL,
    intro_html MEDIUMTEXT,
    outro_html MEDIUMTEXT,
    time_complexity VARCHAR(120) DEFAULT NULL,
    space_complexity VARCHAR(120) DEFAULT NULL,
    is_published TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_pcp_editorial_question (question_id, position),
    CONSTRAINT fk_pcp_editorial_question FOREIGN KEY (question_id)
        REFERENCES pcp_questions (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS pcp_editorial_code (
    id INT AUTO_INCREMENT PRIMARY KEY,
    editorial_id INT NOT NULL,
    language ENUM('python','java','c','cpp','csharp','javascript') NOT NULL,
    code MEDIUMTEXT,
    UNIQUE KEY uq_pcp_editorial_lang (editorial_id, language),
    CONSTRAINT fk_pcp_editorial_code FOREIGN KEY (editorial_id)
        REFERENCES pcp_editorials (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS pcp_bookmarks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    question_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_pcp_bookmark (user_id, question_id),
    KEY idx_pcp_bookmark_user (user_id),
    CONSTRAINT fk_pcp_bookmark_question FOREIGN KEY (question_id)
        REFERENCES pcp_questions (id) ON DELETE CASCADE
) ENGINE=InnoDB;
