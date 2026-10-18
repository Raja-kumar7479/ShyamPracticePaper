-- Readable URLs for practice questions.
--
-- /practice-coding/problem/49 told a student nothing about what they were
-- opening, and nothing about what they had solved when they looked back
-- through history or shared a link. The slug carries the title:
-- /practice-coding/problem/two-sum
--
-- The numeric route still works and redirects to the slug, so old links and
-- bookmarks keep resolving.
--
-- Idempotent. MySQL has no ADD COLUMN IF NOT EXISTS, so the column and the
-- index are each added through a prepared statement that checks
-- information_schema first, which makes a re-run a no-op instead of an error.

SET @has_col := (SELECT COUNT(*) FROM information_schema.COLUMNS
                  WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'pcp_questions'
                    AND COLUMN_NAME = 'slug');
SET @sql := IF(@has_col = 0,
    'ALTER TABLE pcp_questions ADD COLUMN slug VARCHAR(120) DEFAULT NULL AFTER title',
    'DO 0');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Backfill from the title: lowercase, non-alphanumerics collapsed to a dash.
UPDATE pcp_questions
   SET slug = TRIM(BOTH '-' FROM REGEXP_REPLACE(LOWER(title), '[^a-z0-9]+', '-'))
 WHERE slug IS NULL OR slug = '';

-- Two questions may share a title, so the duplicates are made unique by id
-- before the unique index goes on.
UPDATE pcp_questions q
  JOIN (SELECT id, ROW_NUMBER() OVER (PARTITION BY slug ORDER BY id) AS rn
          FROM pcp_questions) d ON d.id = q.id
   SET q.slug = CONCAT(q.slug, '-', q.id)
 WHERE d.rn > 1;

-- A title made only of punctuation would leave an empty slug.
UPDATE pcp_questions SET slug = CONCAT('problem-', id)
 WHERE slug IS NULL OR slug = '';

SET @has_idx := (SELECT COUNT(*) FROM information_schema.STATISTICS
                  WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'pcp_questions'
                    AND INDEX_NAME = 'uq_pcp_question_slug');
SET @sql := IF(@has_idx = 0,
    'CREATE UNIQUE INDEX uq_pcp_question_slug ON pcp_questions (slug)',
    'DO 0');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
