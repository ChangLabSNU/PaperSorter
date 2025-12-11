-- Migration: add covering index for predicted_preferences by model/score/feed
-- This speeds up feed listing when filtering by prediction score.
--
-- How to apply (cannot run inside a transaction because of CONCURRENTLY):
--   psql -d your_database -f migrations/add-predicted-preferences-score-index.sql
--
-- Recommended: run during low traffic; CREATE INDEX CONCURRENTLY takes a bit longer
-- but avoids long writes locks on the table.

SET search_path TO papersorter;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_predpref_model_score_feed
    ON papersorter.predicted_preferences (model_id, score DESC, feed_id);
