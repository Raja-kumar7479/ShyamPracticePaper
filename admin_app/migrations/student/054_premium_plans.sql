SET @db := DATABASE();

CREATE TABLE IF NOT EXISTS premium_plans (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(20) NOT NULL,
    plan_key VARCHAR(40) NOT NULL,
    label VARCHAR(80) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    discount DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    discount_ends_at DATETIME NULL,
    duration_days INT NULL,
    valid_until DATETIME NULL,
    extra_days INT NOT NULL DEFAULT 0,
    position INT NOT NULL DEFAULT 0,
    status ENUM('active','inactive') NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_plan (code, plan_key)
) ENGINE=InnoDB;

INSERT INTO premium_plans (code, plan_key, label, price, discount, discount_ends_at, duration_days, extra_days, position)
SELECT code, 'monthly', 'Monthly', monthly_price, monthly_discount, monthly_offer_ends_at, 30, monthly_extra_days, 1
FROM premium_catalog
ON DUPLICATE KEY UPDATE plan_key = plan_key;

INSERT INTO premium_plans (code, plan_key, label, price, discount, discount_ends_at, duration_days, extra_days, position)
SELECT code, 'yearly', 'Yearly', yearly_price, yearly_discount, yearly_offer_ends_at, 365, yearly_extra_days, 2
FROM premium_catalog
ON DUPLICATE KEY UPDATE plan_key = plan_key;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='pcp_subscriptions' AND COLUMN_NAME='plan_label') = 0,
  'ALTER TABLE pcp_subscriptions ADD COLUMN plan_label VARCHAR(80) NULL AFTER plan',
  'SELECT "plan_label exists" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

UPDATE pcp_subscriptions SET plan_label = CONCAT(UPPER(LEFT(plan,1)), SUBSTRING(plan,2)) WHERE plan_label IS NULL;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='premium_catalog' AND COLUMN_NAME='monthly_price') > 0,
  'ALTER TABLE premium_catalog
     DROP COLUMN monthly_price, DROP COLUMN monthly_discount, DROP COLUMN monthly_offer_ends_at, DROP COLUMN monthly_extra_days,
     DROP COLUMN yearly_price, DROP COLUMN yearly_discount, DROP COLUMN yearly_offer_ends_at, DROP COLUMN yearly_extra_days',
  'SELECT "catalog plan columns already dropped" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=@db AND TABLE_NAME='course_content' AND COLUMN_NAME='validity_expires_at') > 0,
  'ALTER TABLE course_content DROP COLUMN validity_expires_at',
  'SELECT "content expiry already dropped" AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
