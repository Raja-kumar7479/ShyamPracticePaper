ALTER TABLE course_groups ADD COLUMN platform VARCHAR(20) NOT NULL DEFAULT 'competitive';
UPDATE course_groups SET platform = 'placement' WHERE group_name = 'PLACEMENT';
