DROP TRIGGER IF EXISTS trg_enrollment_cap;
CREATE TRIGGER trg_enrollment_cap BEFORE INSERT ON enrollment FOR EACH ROW
BEGIN
  DECLARE existing INT DEFAULT 0;
  SELECT COUNT(*) INTO existing FROM enrollment WHERE email = NEW.email;
  IF existing >= 3 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Enrollment limit reached';
  END IF;
END
