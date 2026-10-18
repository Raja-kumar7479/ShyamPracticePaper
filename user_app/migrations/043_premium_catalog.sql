SET @db := DATABASE();

-- Premium is sold per course. One row per course code: the two plans, each
-- with its own amount and discount, the "What you get" copy, and a switch.
CREATE TABLE IF NOT EXISTS premium_catalog (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    monthly_price DECIMAL(10,2) NOT NULL DEFAULT 999.00,
    monthly_discount DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    yearly_price DECIMAL(10,2) NOT NULL DEFAULT 6999.00,
    yearly_discount DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    details MEDIUMTEXT NULL,
    status ENUM('active','inactive') NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- A subscription belongs to the course it was bought for. NULL means the old
-- platform-wide kind, which stays valid in every course.
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='pcp_subscriptions' AND COLUMN_NAME='course_code') = 0,
  'ALTER TABLE pcp_subscriptions ADD COLUMN course_code VARCHAR(20) NULL AFTER email, ADD INDEX idx_pcp_sub_course (course_code)',
  'SELECT "pcp_subscriptions course_code exists" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- The premium copy briefly lived on course_content. Carry any text an admin
-- already wrote over to the course's catalog row, then drop the column.
SET @has_col := (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='course_content' AND COLUMN_NAME='premium_details');
SET @sql := IF(@has_col > 0,
  'INSERT INTO premium_catalog (code, details)
     SELECT cc.code, cc.premium_details
     FROM course_content cc
     WHERE cc.premium_details IS NOT NULL AND TRIM(cc.premium_details) <> ''''
       AND cc.id = (SELECT cc2.id FROM course_content cc2
                    WHERE cc2.code = cc.code AND cc2.premium_details IS NOT NULL AND TRIM(cc2.premium_details) <> ''''
                    ORDER BY cc2.updated_at DESC, cc2.id DESC LIMIT 1)
   ON DUPLICATE KEY UPDATE details = COALESCE(premium_catalog.details, VALUES(details))',
  'SELECT "no premium_details column to migrate" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql := IF(@has_col > 0,
  'ALTER TABLE course_content DROP COLUMN premium_details',
  'SELECT "course_content premium_details already dropped" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
