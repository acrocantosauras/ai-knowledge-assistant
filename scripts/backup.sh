#!/usr/bin/env bash
# Dump the production database to ./backups/ (gzip). Never deletes anything.
# Usage: ./scripts/backup.sh [env-file]   (default: .env.production)
set -euo pipefail
ENV_FILE="${1:-.env.production}"
mkdir -p backups
OUT="backups/aika-$(date +%Y%m%d-%H%M%S).sql.gz"
docker compose --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.prod.yml \
  exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$OUT"
echo "Backup written to $OUT"
