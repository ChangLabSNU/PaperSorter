-- Add primary_channel field to users table
-- This field references the user's primary notification channel
-- When NULL, no broadcast badges are shown and starring doesn't queue broadcasts

ALTER TABLE papersorter.users
ADD COLUMN primary_channel_id integer DEFAULT NULL;

-- Add foreign key constraint to channels table
ALTER TABLE papersorter.users
ADD CONSTRAINT users_primary_channel_fk
FOREIGN KEY (primary_channel_id)
REFERENCES papersorter.channels(id)
ON DELETE SET NULL;

-- Add index for faster lookups
CREATE INDEX idx_users_primary_channel ON papersorter.users(primary_channel_id);

-- Note: primary_channel_id defaults to NULL for all existing users
-- Users must explicitly set their primary channel to enable broadcast features