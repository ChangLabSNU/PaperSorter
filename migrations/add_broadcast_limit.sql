-- Migration: Add broadcast_limit column to channels table
-- This migration adds per-channel broadcast limits

-- Add the broadcast_limit column with a default value of 20
ALTER TABLE channels
ADD COLUMN IF NOT EXISTS broadcast_limit INTEGER DEFAULT 20;

-- Add a check constraint to ensure reasonable limits
ALTER TABLE channels
ADD CONSTRAINT broadcast_limit_check CHECK (broadcast_limit >= 1 AND broadcast_limit <= 100);

-- Update any NULL values to the default
UPDATE channels
SET broadcast_limit = 20
WHERE broadcast_limit IS NULL;

-- Make the column NOT NULL after setting defaults
ALTER TABLE channels
ALTER COLUMN broadcast_limit SET NOT NULL;

COMMENT ON COLUMN channels.broadcast_limit IS 'Maximum number of items to broadcast per run for this channel';