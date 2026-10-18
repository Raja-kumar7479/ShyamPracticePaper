CREATE TABLE IF NOT EXISTS content_orders (
  id INT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  username VARCHAR(255) NULL,
  phone VARCHAR(20) NULL,
  course_code VARCHAR(20) NOT NULL,
  unique_code VARCHAR(100) NULL,
  razorpay_order_id VARCHAR(100) NOT NULL UNIQUE,
  razorpay_payment_id VARCHAR(100) NULL,
  amount_paise INT NOT NULL,
  list_paise INT NULL,
  discount_pct DECIMAL(5,2) NULL,
  cart_json MEDIUMTEXT NOT NULL,
  status ENUM('created','paid','failed','refunded') NOT NULL DEFAULT 'created',
  gateway_status VARCHAR(20) NULL,
  payment_method VARCHAR(40) NULL,
  fulfilled_by VARCHAR(60) NULL,
  fulfilled_at DATETIME NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_co_email (email, status),
  INDEX idx_co_status (status, created_at),
  INDEX idx_co_payment (razorpay_payment_id)
) ENGINE=InnoDB;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'pcp_subscriptions' AND COLUMN_NAME = 'gateway_status') = 0,
  'ALTER TABLE pcp_subscriptions ADD COLUMN gateway_status VARCHAR(20) NULL AFTER status, ADD COLUMN fulfilled_by VARCHAR(60) NULL AFTER gateway_status, ADD COLUMN plan_ends_at DATETIME NULL AFTER expires_at',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

ALTER TABLE pcp_subscriptions MODIFY COLUMN status ENUM('created','active','failed','refunded') NOT NULL DEFAULT 'created';
