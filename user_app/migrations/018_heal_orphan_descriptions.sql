-- One-time heal of test descriptions whose content card was hard-deleted
-- before delete_content became purchase-safe.
--
-- Only removes descriptions that are BOTH orphaned (no course_content row) AND
-- never paid for. Anything a student paid for is left untouched. Their
-- questions/sections/results cascade off the description FK; coding cp_tests
-- rows (no FK) are removed explicitly first.
--
-- Idempotent: re-running finds nothing to heal.

-- coding tests behind orphaned, unpaid comm descriptions
DELETE cp FROM cp_tests cp
  JOIN comm_description cd ON cd.test_key = cp.test_key
  LEFT JOIN course_content cc ON cc.section_id = cd.test_id
 WHERE cc.id IS NULL
   AND NOT EXISTS (SELECT 1 FROM purchase p
                    WHERE p.section_id = cd.test_id AND p.status = 'Paid');

DELETE cd FROM comm_description cd
  LEFT JOIN course_content cc ON cc.section_id = cd.test_id
 WHERE cc.id IS NULL
   AND NOT EXISTS (SELECT 1 FROM purchase p
                    WHERE p.section_id = cd.test_id AND p.status = 'Paid');

DELETE td FROM test_description td
  LEFT JOIN course_content cc ON cc.section_id = td.test_id
 WHERE cc.id IS NULL
   AND NOT EXISTS (SELECT 1 FROM purchase p
                    WHERE p.section_id = td.test_id AND p.status = 'Paid');
