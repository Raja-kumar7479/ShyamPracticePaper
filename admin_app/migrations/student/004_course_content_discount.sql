-- Adds course_content.discount: a per-item percentage set by the admin.
-- The store and the admin cards show the original price struck through next to
-- the payable price, and checkout charges the discounted amount, so the column
-- must exist before the discount UI is used.
--
-- discount is a percentage (0-100). 0 means "no discount" and is the default, so
-- existing rows keep their current price with no visible change.
-- Idempotent: safe to re-run.

SET @db := DATABASE();

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'course_content'
     AND COLUMN_NAME = 'discount') = 0,
  'ALTER TABLE course_content ADD COLUMN discount DECIMAL(5,2) NOT NULL DEFAULT 0.00 AFTER price',
  'SELECT "discount already exists" AS note');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

UPDATE course_content SET discount = 0.00 WHERE discount IS NULL;
