-- Repairs the link between coding test descriptions and cp_tests.
--
-- A cp_tests row used to be created only when an admin opened the coding
-- question editor. Any coding description nobody had opened yet had no row, so
-- the student dashboard showed fewer tests than the admin had created. And a
-- deleted description left its cp_tests row behind, so the dashboard could
-- also show a test that no longer existed.
--
-- The application now creates and deletes the row alongside the description.
-- This migration fixes the rows that already exist.
--
-- Idempotent: safe to re-run.

-- 1. Drop coding tests whose description is gone. Sections, questions and
--    attempts under them cascade, which is intended: the description that
--    owned them was already deleted.
DELETE cp FROM cp_tests cp
 WHERE cp.test_key IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM comm_description d WHERE d.test_key = cp.test_key);

-- 2. Create the missing row for every coding description that has none.
--    The slug must be unique, so it is built from the test_key, which is.
INSERT INTO cp_tests (slug, test_id, code, test_key, title, description,
                      total_duration_min, is_published)
SELECT CONCAT('coding-', d.test_key),
       d.test_id, d.code, d.test_key,
       COALESCE(NULLIF(TRIM(d.subject_title), ''), 'Coding Test'),
       d.subject_subtitle,
       COALESCE(NULLIF(d.total_duration_minutes, 0), 60),
       1
  FROM comm_description d
  JOIN course_content cc ON cc.section_id = d.test_id
 WHERE cc.section = 'coding_test'
   AND NOT EXISTS (SELECT 1 FROM cp_tests cp WHERE cp.test_key = d.test_key);

-- 3. Older rows were created before cp_tests carried the course link, so their
--    test_id / code are NULL and the dashboard cannot scope them to a course.
UPDATE cp_tests cp
  JOIN comm_description d ON d.test_key = cp.test_key
   SET cp.test_id = COALESCE(cp.test_id, d.test_id),
       cp.code    = COALESCE(cp.code, d.code)
 WHERE cp.test_id IS NULL OR cp.code IS NULL;
