-- Migration from PaperSorter v0.3 to v0.4
-- Run this script to update your database schema from version 0.3 to 0.4
--
-- IMPORTANT: Always backup your database before running migrations
-- Run: pg_dump -U your_user -d your_database > backup_$(date +%Y%m%d_%H%M%S).sql
--
-- To apply this migration:
-- psql -U your_user -d your_database -f version-0.3-to-0.4.sql

BEGIN;

-- =====================================================================
-- 1. Add broadcast_limit and broadcast_hours to channels table
-- =====================================================================

-- Add broadcast_limit column with default value of 20
ALTER TABLE papersorter.channels
ADD COLUMN IF NOT EXISTS broadcast_limit INTEGER DEFAULT 20;

-- Add check constraint to ensure reasonable limits
ALTER TABLE papersorter.channels
ADD CONSTRAINT broadcast_limit_check CHECK (broadcast_limit >= 1 AND broadcast_limit <= 100);

-- Update any NULL values to the default
UPDATE papersorter.channels
SET broadcast_limit = 20
WHERE broadcast_limit IS NULL;

-- Make the column NOT NULL after setting defaults
ALTER TABLE papersorter.channels
ALTER COLUMN broadcast_limit SET NOT NULL;

-- Add broadcast_hours column for scheduling
ALTER TABLE papersorter.channels
ADD COLUMN IF NOT EXISTS broadcast_hours TEXT;

COMMENT ON COLUMN papersorter.channels.broadcast_limit IS 'Maximum number of items to broadcast per run for this channel';
COMMENT ON COLUMN papersorter.channels.broadcast_hours IS 'JSON array of 24 boolean values for hourly broadcast scheduling';

-- =====================================================================
-- 2. Add primary_channel_id to users table
-- =====================================================================

-- Add primary_channel field to users table
-- This field references the user's primary notification channel
-- When NULL, no broadcast badges are shown and starring doesn't queue broadcasts
ALTER TABLE papersorter.users
ADD COLUMN IF NOT EXISTS primary_channel_id INTEGER DEFAULT NULL;

-- Add foreign key constraint to channels table
ALTER TABLE papersorter.users
ADD CONSTRAINT users_primary_channel_fk
FOREIGN KEY (primary_channel_id)
REFERENCES papersorter.channels(id)
ON DELETE SET NULL;

-- Add index for faster lookups
CREATE INDEX IF NOT EXISTS idx_users_primary_channel
ON papersorter.users(primary_channel_id);

COMMENT ON COLUMN papersorter.users.primary_channel_id IS 'User''s primary channel for broadcast notifications';

-- =====================================================================
-- 3. Update models table: replace user_id with notes
-- =====================================================================

-- Add notes field to models table
ALTER TABLE papersorter.models
ADD COLUMN IF NOT EXISTS notes TEXT;

-- Update existing models to have a default note if needed
UPDATE papersorter.models
SET notes = 'Default preference prediction model'
WHERE id = 1 AND notes IS NULL;

-- Drop the foreign key constraint first
ALTER TABLE papersorter.models
DROP CONSTRAINT IF EXISTS fk_models_user_id;

-- Drop the index on user_id
DROP INDEX IF EXISTS papersorter.idx_models_user;

-- Drop the user_id column
ALTER TABLE papersorter.models
DROP COLUMN IF EXISTS user_id;

COMMENT ON COLUMN papersorter.models.notes IS 'General description or notes about this preference prediction model';

-- =====================================================================
-- 4. Add trigger for feed source name propagation
-- =====================================================================

-- Create function to propagate feed source name updates to feeds
CREATE OR REPLACE FUNCTION papersorter.propagate_feed_source_name_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.name <> OLD.name THEN
        UPDATE papersorter.feeds
        SET origin = NEW.name
        WHERE origin = OLD.name;
    END IF;
    RETURN NEW;
END;
$$;

-- Create trigger on feed_sources table
DROP TRIGGER IF EXISTS trg_feed_source_name_update ON papersorter.feed_sources;
CREATE TRIGGER trg_feed_source_name_update
AFTER UPDATE ON papersorter.feed_sources
FOR EACH ROW
EXECUTE FUNCTION papersorter.propagate_feed_source_name_update();

COMMENT ON FUNCTION papersorter.propagate_feed_source_name_update() IS 'Propagates feed source name changes to the feeds table origin column';

-- =====================================================================
-- 5. Clean up temporary migration table (if exists)
-- =====================================================================

-- Drop the temporary RSS duplicate check table if it exists
DROP TABLE IF EXISTS papersorter.migrtmp_rss_dup_check;

-- =====================================================================
-- 6. Add theme and timezone columns to users table
-- =====================================================================

-- Add theme column to users table with default value 'light'
ALTER TABLE papersorter.users ADD COLUMN IF NOT EXISTS theme VARCHAR(10) DEFAULT 'light';

-- Valid values: 'light', 'dark', 'auto'
-- 'auto' follows system preference
-- Default to 'light' for backward compatibility

-- Add check constraint to ensure valid theme values
ALTER TABLE papersorter.users ADD CONSTRAINT check_theme_valid
    CHECK (theme IN ('light', 'dark', 'auto'));

-- Update existing users to have 'light' theme (if needed)
UPDATE papersorter.users SET theme = 'light' WHERE theme IS NULL;

-- Add timezone column to users table
ALTER TABLE papersorter.users ADD COLUMN IF NOT EXISTS timezone VARCHAR(50) DEFAULT 'UTC';

COMMENT ON COLUMN papersorter.users.theme IS 'User interface theme preference: light, dark, or auto';
COMMENT ON COLUMN papersorter.users.timezone IS 'User timezone for date/time display';

-- =====================================================================
-- 7. Add score_name field to models table
-- =====================================================================

-- Add score_name column to models table with default value 'Score'
ALTER TABLE papersorter.models
ADD COLUMN IF NOT EXISTS score_name VARCHAR(50) DEFAULT 'Score';

-- Update existing models to have default score name if NULL
UPDATE papersorter.models
SET score_name = 'Score'
WHERE score_name IS NULL;

-- Make the column NOT NULL after setting defaults
ALTER TABLE papersorter.models
ALTER COLUMN score_name SET NOT NULL;

COMMENT ON COLUMN papersorter.models.score_name IS 'Display name for model prediction scores';

-- =====================================================================
-- 8. Verify migration success
-- =====================================================================

-- Check that all expected columns exist
DO $$
BEGIN
    -- Check channels table
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'papersorter'
                   AND table_name = 'channels'
                   AND column_name = 'broadcast_limit') THEN
        RAISE EXCEPTION 'Migration failed: channels.broadcast_limit column not found';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'papersorter'
                   AND table_name = 'channels'
                   AND column_name = 'broadcast_hours') THEN
        RAISE EXCEPTION 'Migration failed: channels.broadcast_hours column not found';
    END IF;

    -- Check users table
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'papersorter'
                   AND table_name = 'users'
                   AND column_name = 'primary_channel_id') THEN
        RAISE EXCEPTION 'Migration failed: users.primary_channel_id column not found';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'papersorter'
                   AND table_name = 'users'
                   AND column_name = 'theme') THEN
        RAISE EXCEPTION 'Migration failed: users.theme column not found';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'papersorter'
                   AND table_name = 'users'
                   AND column_name = 'timezone') THEN
        RAISE EXCEPTION 'Migration failed: users.timezone column not found';
    END IF;

    -- Check models table
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'papersorter'
                   AND table_name = 'models'
                   AND column_name = 'notes') THEN
        RAISE EXCEPTION 'Migration failed: models.notes column not found';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'papersorter'
                   AND table_name = 'models'
                   AND column_name = 'score_name') THEN
        RAISE EXCEPTION 'Migration failed: models.score_name column not found';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'papersorter'
               AND table_name = 'models'
               AND column_name = 'user_id') THEN
        RAISE EXCEPTION 'Migration failed: models.user_id column still exists';
    END IF;

    RAISE NOTICE 'Migration completed successfully!';
END $$;

-- =====================================================================
-- 9. Add assisted_query column to saved_searches table for AI Assist
-- =====================================================================

-- Add column to store AI-enhanced version of search queries
ALTER TABLE papersorter.saved_searches
ADD COLUMN IF NOT EXISTS assisted_query TEXT;

-- Add descriptive comment
COMMENT ON COLUMN papersorter.saved_searches.assisted_query IS 'AI-enhanced version of the search query generated by AI Assist feature';

COMMIT;

-- =====================================================================
-- Post-migration notes:
-- =====================================================================
-- 1. Users need to set their primary_channel_id to enable broadcast features
-- 2. The broadcast_hours field stores a JSON array of 24 boolean values
-- 3. Models no longer have user associations; they are system-wide
-- 4. The notes field in models table can store any descriptive information
-- 5. Users can now set theme preference (light/dark/auto) and timezone
-- 6. Models now have a score_name field for customizing score display names
-- =====================================================================