-- Add notes field to models table
ALTER TABLE models ADD COLUMN IF NOT EXISTS notes TEXT;

-- Update existing models to have a default note if needed
UPDATE models SET notes = 'Default preference prediction model' WHERE id = 1 AND notes IS NULL;

-- Drop the user_id column as it's no longer needed
ALTER TABLE models DROP COLUMN IF EXISTS user_id;