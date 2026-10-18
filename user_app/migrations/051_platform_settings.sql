CREATE TABLE IF NOT EXISTS platform_settings (
    setting_key VARCHAR(64) NOT NULL PRIMARY KEY,
    setting_value VARCHAR(255) NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

INSERT INTO platform_settings (setting_key, setting_value) VALUES ('max_enrollments', '3')
ON DUPLICATE KEY UPDATE setting_key = setting_key;

DROP TRIGGER IF EXISTS trg_enrollment_cap;
CREATE TRIGGER trg_enrollment_cap BEFORE INSERT ON enrollment FOR EACH ROW
BEGIN
  DECLARE existing INT DEFAULT 0;
  DECLARE cap INT DEFAULT 3;
  SELECT COUNT(*) INTO existing FROM enrollment WHERE email = NEW.email;
  SELECT CAST(setting_value AS UNSIGNED) INTO cap FROM platform_settings WHERE setting_key = 'max_enrollments';
  IF cap < 1 THEN SET cap = 3; END IF;
  IF existing >= cap THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Enrollment limit reached';
  END IF;
END
