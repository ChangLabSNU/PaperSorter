#!/bin/bash
# Scheduler entrypoint script

set -e

echo "Starting PaperSorter scheduler..."
echo "Data directory: $PAPERSORTER_DATADIR"
echo "Config file: $PAPERSORTER_CONFIG"

# Wait for database to be ready
echo "Waiting for database..."
until pg_isready -h postgres -U ${POSTGRES_USER:-papersorter}; do
  echo "Database is unavailable - sleeping"
  sleep 2
done
echo "Database is ready!"

# Create log directory if it doesn't exist
mkdir -p /data/logs

# Ensure cron environment has access to environment variables
printenv | grep -E '^(DATABASE_URL|PAPERSORTER_|OPENAI_|EMBEDDING_|PATH)' > /etc/environment

# Start cron in foreground
echo "Starting cron daemon..."
cron -f