-- Taxonomy catalog: the course/section vocabulary becomes data instead of
-- schema and Python constants.
--
-- Why this replaces the enums added in 012:
--
--   1. An enum column holds the union of every group's values, so the database
--      could not express "coding_test only under PLACEMENT" - that rule lived
--      only in Python. A group/section join table states it as a fact the
--      database itself enforces.
--   2. Adding an exam type meant ALTER TABLE. Now it is an INSERT.
--   3. The label, help text and "portal not built yet" flag lived in a Python
--      dict duplicated across both apps, which would drift. They are columns
--      now, and both apps read the same rows.
--
-- Idempotent: safe to re-run.

SET @db := DATABASE();

-- ---------------------------------------------------------------- catalog
CREATE TABLE IF NOT EXISTS course_groups (
  group_name  VARCHAR(40) NOT NULL PRIMARY KEY,
  label       VARCHAR(80) NOT NULL,
  position    INT DEFAULT 0,
  is_active   TINYINT(1) DEFAULT 1
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS course_group_codes (
  group_name  VARCHAR(40) NOT NULL,
  code        VARCHAR(20) NOT NULL,
  label       VARCHAR(80) NULL,
  position    INT DEFAULT 0,
  PRIMARY KEY (group_name, code),
  UNIQUE KEY uq_code (code),
  FOREIGN KEY (group_name) REFERENCES course_groups(group_name) ON UPDATE CASCADE
) ENGINE=InnoDB;

-- One row per kind of content. `portal` is what opens for the student and is
-- the single fact the user app routes on; `editor` is which question editor the
-- admin gets. NULL portal means study material or not built yet.
CREATE TABLE IF NOT EXISTS content_sections (
  section_key  VARCHAR(40) NOT NULL PRIMARY KEY,
  label        VARCHAR(80) NOT NULL,
  help_text    VARCHAR(255) NULL,
  portal       VARCHAR(30) NULL,
  editor       VARCHAR(30) NULL,
  is_available TINYINT(1) DEFAULT 1,
  position     INT DEFAULT 0
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS course_group_sections (
  group_name  VARCHAR(40) NOT NULL,
  section_key VARCHAR(40) NOT NULL,
  position    INT DEFAULT 0,
  PRIMARY KEY (group_name, section_key),
  FOREIGN KEY (group_name)  REFERENCES course_groups(group_name)     ON UPDATE CASCADE ON DELETE CASCADE,
  FOREIGN KEY (section_key) REFERENCES content_sections(section_key) ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;

-- ------------------------------------------------------------------- seed
INSERT INTO course_groups (group_name, label, position) VALUES
  ('GATE',               'GATE',               1),
  ('PLACEMENT',          'Placement',          2),
  ('JEE MAIN + ADVANCE', 'JEE Main + Advance', 3)
ON DUPLICATE KEY UPDATE label = VALUES(label), position = VALUES(position);

INSERT INTO course_group_codes (group_name, code, label, position) VALUES
  ('GATE', 'CS', 'Computer Science',   1),
  ('GATE', 'DS', 'Data Science',       2),
  ('GATE', 'EC', 'Electronics',        3),
  ('GATE', 'EE', 'Electrical',         4),
  ('GATE', 'ME', 'Mechanical',         5),
  ('PLACEMENT', 'PLA', 'Placement',    1),
  ('PLACEMENT', 'PLM', 'Placement MNC',2),
  ('JEE MAIN + ADVANCE', 'JEE', 'JEE', 1)
ON DUPLICATE KEY UPDATE label = VALUES(label), position = VALUES(position);

INSERT INTO content_sections (section_key, label, help_text, portal, editor, is_available, position) VALUES
  ('mock_test','Mock Test','Full-length objective test. Opens the competitive exam portal.','competitive','competitive',1,1),
  ('coding_test','Coding Test','Programming round graded by test cases. Opens the coding portal.','coding','coding',1,2),
  ('communication_test','Communication Test','Speaking, listening and writing round. Opens the communication portal.','communication','communication',1,3),
  ('aptitude_test','Aptitude Test','Reasoning and quantitative round. Portal is not built yet.',NULL,NULL,0,4),
  ('coding_practice','Coding Practice','Untimed practice problems. Portal is not built yet.',NULL,NULL,0,5),
  ('question_practice','Question Practice','Practice question bank. Portal is not built yet.',NULL,NULL,0,6),
  ('notes','Notes','Study notes for the course.','notes',NULL,1,7),
  ('lecture','Lecture','Video lectures.','lecture',NULL,1,8),
  ('community','Community','Discussion space.','community',NULL,1,9),
  ('blog','Blog','Written articles.','blog',NULL,1,10)
ON DUPLICATE KEY UPDATE
  label = VALUES(label), help_text = VALUES(help_text), portal = VALUES(portal),
  editor = VALUES(editor), is_available = VALUES(is_available), position = VALUES(position);

INSERT INTO course_group_sections (group_name, section_key, position) VALUES
  ('GATE','mock_test',1), ('GATE','notes',2), ('GATE','lecture',3),
  ('GATE','community',4), ('GATE','blog',5),
  ('JEE MAIN + ADVANCE','mock_test',1), ('JEE MAIN + ADVANCE','notes',2),
  ('JEE MAIN + ADVANCE','lecture',3), ('JEE MAIN + ADVANCE','community',4),
  ('JEE MAIN + ADVANCE','blog',5),
  ('PLACEMENT','coding_test',1), ('PLACEMENT','communication_test',2),
  ('PLACEMENT','aptitude_test',3), ('PLACEMENT','coding_practice',4),
  ('PLACEMENT','question_practice',5), ('PLACEMENT','notes',6),
  ('PLACEMENT','lecture',7), ('PLACEMENT','community',8), ('PLACEMENT','blog',9)
ON DUPLICATE KEY UPDATE position = VALUES(position);

-- ------------------------------------------- point the live columns at it
-- course_content.section: enum -> VARCHAR + FK, so a new exam type needs no
-- schema change and an unknown value is rejected by the database.
SET @sql := IF((SELECT DATA_TYPE FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='course_content' AND COLUMN_NAME='section') = 'enum',
  'ALTER TABLE course_content MODIFY COLUMN section VARCHAR(40) NOT NULL',
  'SELECT "course_content.section already VARCHAR" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='course_content'
      AND CONSTRAINT_NAME='fk_content_section') = 0,
  'ALTER TABLE course_content
     ADD CONSTRAINT fk_content_section FOREIGN KEY (section)
     REFERENCES content_sections(section_key) ON UPDATE CASCADE',
  'SELECT "fk_content_section exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- courses.name / courses.code: enum -> VARCHAR, then one composite key so an
-- invalid group+code pair (PLM under GATE) cannot be stored at all. This is the
-- rule an enum could not express, because it spans two columns.
SET @sql := IF((SELECT DATA_TYPE FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='courses' AND COLUMN_NAME='name') = 'enum',
  'ALTER TABLE courses MODIFY COLUMN name VARCHAR(40) NOT NULL',
  'SELECT "courses.name already VARCHAR" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT DATA_TYPE FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='courses' AND COLUMN_NAME='code') = 'enum',
  'ALTER TABLE courses MODIFY COLUMN code VARCHAR(20) NOT NULL',
  'SELECT "courses.code already VARCHAR" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='courses'
      AND CONSTRAINT_NAME='fk_course_group_code') = 0,
  'ALTER TABLE courses
     ADD CONSTRAINT fk_course_group_code FOREIGN KEY (name, code)
     REFERENCES course_group_codes(group_name, code) ON UPDATE CASCADE',
  'SELECT "fk_course_group_code exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
