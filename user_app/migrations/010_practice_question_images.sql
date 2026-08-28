-- Image-question support for practice papers, mirroring the mock-test feature:
-- questions.question_image  = uploaded image URL (question_text stays empty)
-- questions.option_regions  = JSON {a:{x,y,w,h},...} percent rectangles marking
--                             each option's area on the image.
-- Idempotent: safe to re-run.

SET @db := DATABASE();

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='questions' AND COLUMN_NAME='question_image') = 0,
  'ALTER TABLE questions
     ADD COLUMN question_image VARCHAR(255) NULL,
     ADD COLUMN option_regions JSON NULL',
  'SELECT "questions image columns exist" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
