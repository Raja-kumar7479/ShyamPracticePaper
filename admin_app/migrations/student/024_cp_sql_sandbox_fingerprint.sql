-- Records which schema each SQL sandbox database was actually built from.
--
-- ensure_sandbox() only ever created a sandbox when one did not exist yet, and
-- the single "rebuild it" call lived in the coding portal's own authoring
-- screens. Those screens are gone -- coding questions are authored in the admin
-- app -- so editing a question's sandbox_schema_sql left every student running
-- against the schema the sandbox happened to be seeded with the first time
-- anyone opened the question.
--
-- Storing the fingerprint here rather than inside the sandbox keeps the
-- student-visible database to exactly the tables the question defines.
--
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS cp_sql_sandboxes (
    question_id INT NOT NULL PRIMARY KEY,
    fingerprint CHAR(64) NOT NULL,
    built_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;
