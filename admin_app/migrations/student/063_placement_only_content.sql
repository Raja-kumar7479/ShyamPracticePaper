DROP TRIGGER IF EXISTS trg_content_platform_insert;
CREATE TRIGGER trg_content_platform_insert BEFORE INSERT ON course_content FOR EACH ROW
BEGIN
  DECLARE portal_name VARCHAR(30) DEFAULT NULL;
  DECLARE group_platform VARCHAR(20) DEFAULT 'competitive';
  SELECT portal INTO portal_name FROM content_sections WHERE section_key = NEW.section LIMIT 1;
  SELECT platform INTO group_platform FROM course_groups WHERE group_name = NEW.name LIMIT 1;
  IF portal_name IN ('coding', 'communication', 'tcs', 'coding_practice') AND group_platform <> 'placement' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Coding, communication and TCS content is allowed only under a Placement group';
  END IF;
END;
DROP TRIGGER IF EXISTS trg_content_platform_update;
CREATE TRIGGER trg_content_platform_update BEFORE UPDATE ON course_content FOR EACH ROW
BEGIN
  DECLARE portal_name VARCHAR(30) DEFAULT NULL;
  DECLARE group_platform VARCHAR(20) DEFAULT 'competitive';
  SELECT portal INTO portal_name FROM content_sections WHERE section_key = NEW.section LIMIT 1;
  SELECT platform INTO group_platform FROM course_groups WHERE group_name = NEW.name LIMIT 1;
  IF portal_name IN ('coding', 'communication', 'tcs', 'coding_practice') AND group_platform <> 'placement' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Coding, communication and TCS content is allowed only under a Placement group';
  END IF;
END;
