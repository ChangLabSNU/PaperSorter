#!/bin/bash
# Web container entrypoint script

set -e

echo "Starting PaperSorter web service..."
echo "Data directory: $PAPERSORTER_DATADIR"
echo "Config file: $PAPERSORTER_CONFIG"

# Wait for database to be ready
echo "Waiting for database..."
until pg_isready -h postgres -U ${POSTGRES_USER:-papersorter}; do
  echo "Database is unavailable - sleeping"
  sleep 2
done
echo "Database is ready!"

# Create data directories if they don't exist
mkdir -p /data/logs /data/models /data/posters

# Execute the command
exec "$@"