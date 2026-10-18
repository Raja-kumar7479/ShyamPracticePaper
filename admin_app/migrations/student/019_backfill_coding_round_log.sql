-- Backfills comm_user_log from coding attempts.
--
-- The round assessment list reads every assessment's status from
-- comm_user_log, but the coding portal only ever wrote cp_attempts. A student
-- who had finished a coding assessment still saw "Start Assessment" on the
-- round page, and nothing stopped them sitting it again.
--
-- The application now writes comm_user_log when a coding attempt starts and
-- when it is submitted. This migration repairs the attempts that already
-- exist so history matches what the code will do from now on.
--
-- Idempotent: safe to re-run. Existing rows are only ever upgraded towards
-- 'completed'; a row already marked completed is left alone.

INSERT INTO comm_user_log (email, test_key, course_code, status, start_time, end_time)
SELECT a.email, a.test_key, a.code, a.status, a.started_at, a.submitted_at
  FROM (
        SELECT u.email,
               t.test_key,
               t.code,
               CASE WHEN at.status = 'submitted' THEN 'completed' ELSE 'started' END AS status,
               MIN(at.started_at)   AS started_at,
               MAX(at.submitted_at) AS submitted_at
          FROM cp_attempts at
          JOIN cp_tests t ON t.id = at.test_id
          JOIN auth     u ON u.id = at.user_id
         WHERE t.test_key IS NOT NULL
           AND u.email IS NOT NULL
         GROUP BY u.email, t.test_key, t.code,
                  CASE WHEN at.status = 'submitted' THEN 'completed' ELSE 'started' END
       ) AS a
ON DUPLICATE KEY UPDATE
    status      = IF(comm_user_log.status = 'completed', 'completed', VALUES(status)),
    course_code = COALESCE(comm_user_log.course_code, VALUES(course_code)),
    end_time    = IF(VALUES(status) = 'completed',
                     COALESCE(comm_user_log.end_time, VALUES(end_time)),
                     comm_user_log.end_time);
