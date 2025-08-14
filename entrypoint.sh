#!/bin/bash
set -euo pipefail

echo "[entrypoint] Rendering /app/config.yml from /app/config.yml.tmpl..."
if [ ! -f /app/config.yml.tmpl ]; then
  echo "ERROR: /app/config.yml.tmpl not found" >&2
  exit 1
fi
# Export all env vars so envsubst can see them
export $(env | cut -d= -f1)
envsubst < /app/config.yml.tmpl > /app/config.yml

echo "[entrypoint] Waiting for Postgres at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
for i in {1..60}; do
  if pg_isready -h "${POSTGRES_HOST}" \
                -p "${POSTGRES_PORT}" \
                -U "${POSTGRES_USER}" \
                -d "${POSTGRES_DB}" >/dev/null 2>&1; then
    echo "[entrypoint] Postgres is ready"
    break
  fi
  echo "[entrypoint] Postgres not ready yet... retrying"
  sleep 2
done

echo "[entrypoint] Running database initialization (idempotent)..."
# This should succeed even if DB is already initialized
papersorter init --config /app/config.yml || true

echo "[entrypoint] Creating admin user..."
echo "[entrypoint] DEBUG: ADMIN_EMAIL=${ADMIN_EMAIL}"
if [ -z "${ADMIN_EMAIL:-}" ]; then
    echo "[entrypoint] ERROR: ADMIN_EMAIL environment variable is not set"
    exit 1
fi
python tools/create-admin-user.py -e "${ADMIN_EMAIL}" || true

echo "[entrypoint] Starting uWSGI..."
exec uwsgi \
  --http 0.0.0.0:5001 \
  --wsgi-file /app/PaperSorter/web/wsgi.py \
  --callable app \
  --processes 4
