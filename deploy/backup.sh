#!/bin/sh
# Nightly database backup, keeping the last 14 days. Called from deploy/crontab.
set -e
cd "$(dirname "$0")"
STAMP=$(date +%Y%m%d)
docker compose -f docker-compose.prod.yml --env-file .env exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /backups/flood_pipeline_'"$STAMP"'.dump'
find backups -name 'flood_pipeline_*.dump' -mtime +14 -delete
