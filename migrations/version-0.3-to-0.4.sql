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
-- 6. Verify migration success
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

    -- Check models table
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'papersorter'
                   AND table_name = 'models'
                   AND column_name = 'notes') THEN
        RAISE EXCEPTION 'Migration failed: models.notes column not found';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'papersorter'
               AND table_name = 'models'
               AND column_name = 'user_id') THEN
        RAISE EXCEPTION 'Migration failed: models.user_id column still exists';
    END IF;

    RAISE NOTICE 'Migration completed successfully!';
END $$;

COMMIT;

-- =====================================================================
-- Post-migration notes:
-- =====================================================================
-- 1. Users need to set their primary_channel_id to enable broadcast features
-- 2. The broadcast_hours field stores a JSON array of 24 boolean values
-- 3. Models no longer have user associations; they are system-wide
-- 4. The notes field in models table can store any descriptive information
-- =====================================================================