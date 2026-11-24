# Deployment Checklist

Companion to `DEPLOYMENT_READINESS_SUMMARY.md` (what was verified) and the
Production Deployment section of `README.md`.

## 1. Environment variables

Required in production (compose refuses to start without them; the app also
refuses to start with insecure values when `APP_ENVIRONMENT=production`):

| Variable | Requirement |
|---|---|
| `POSTGRES_PASSWORD` | strong, not the dev default (`ai_knowledge_password` is rejected) |
| `APP_JWT_SECRET_KEY` | >= 32 chars, not the placeholder |
| `APP_METRICS_TOKEN` | >= 16 chars; Prometheus presents it as a bearer token |
| `APP_CORS_ORIGINS` | JSON list, e.g. `["https://app.example.com"]`; `*` is rejected |

Optional: `POSTGRES_USER`, `POSTGRES_DB`, `APP_PORT`, `APP_LOG_LEVEL`,
`APP_RATE_LIMIT_*`, `APP_LLM_PROVIDER` / `APP_EMBEDDING_PROVIDER`
(`mock` | `openai`), `APP_OPENAI_API_KEY`, `APP_LLM_MODEL`,
`APP_EMBEDDING_MODEL`, `APP_EMBEDDING_DIMENSION` (must match the model, 1536 for
`text-embedding-3-small`), `APP_LLM_TIMEOUT`.

## 2. Generate secrets

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"   # APP_JWT_SECRET_KEY
python -c "import secrets; print(secrets.token_hex(24))"       # POSTGRES_PASSWORD
python -c "import secrets; print(secrets.token_urlsafe(32))"   # APP_METRICS_TOKEN
```

Keep `.env.production` out of git (it is ignored). Quote JSON values correctly
in the file; do **not** `source` the file in a shell (it strips quotes from
`APP_CORS_ORIGINS` and shell variables override the env file in compose).

## 3. Deploy

```bash
cp .env.production.example .env.production      # then fill in
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml config -q
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml up -d --build --wait
```

Order: `postgres` + `redis` healthy -> `migrate` (alembic upgrade head) exits 0
-> `api` starts. Postgres and Redis are not published on the host.

## 4. Verify

```bash
curl -fsS http://localhost:8000/health/ready
METRICS_TOKEN=<token> COMPOSE_PROJECT_NAME=<project> bash scripts/smoke-test.sh http://localhost:8000
COMPOSE="docker compose -p <project> --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml" \
  bash scripts/reliability-test.sh      # restarts containers of that project; use on staging
```

## 5. Reverse proxy, TLS and metrics access

- TLS is **not** terminated by the application. Use nginx/Caddy/a cloud LB
  (`deploy/nginx.example.conf`), redirect HTTP to HTTPS, set HSTS.
- `/metrics` must not be internet-reachable: restrict by network in the proxy
  **and** keep `APP_METRICS_TOKEN` (defence in depth). Prometheus scrapes the
  private address with the token (`deploy/prometheus.example.yml`).
- `/health` (liveness) and `/health/ready` (DB + Redis) are unauthenticated and
  reveal only status.
- Streaming (`/api/v1/qa/ask/stream`) needs proxy buffering off and a long read
  timeout (see example config). Set `client_max_body_size` >= 11m.
- Behind a proxy set `FORWARDED_ALLOW_IPS` (uvicorn) so rate limiting sees real
  client IPs. API docs (`/docs`) are disabled in production.

## 6. OpenAI configuration (NEEDS CONFIGURATION until you run it)

```bash
APP_LLM_PROVIDER=openai
APP_EMBEDDING_PROVIDER=openai
APP_OPENAI_API_KEY=<key>            # from a secret store, never committed
```

Then, against the running stack: upload a document, `POST /api/v1/rag/search`,
`POST /api/v1/qa/ask`, and the stream endpoint; confirm sources/citations. Error
mapping: invalid key -> 502 "misconfigured", rate limit/quota -> 429, timeout ->
504, other provider failure -> 502; keys are never logged. Switching embedding
model/dimension requires re-uploading documents.

## 7. Migrations

Automatic via the `migrate` service. Manual run:

```bash
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate
```

Migrations are forward-only in this process; take a backup first.

## 8. Backup and recovery

```bash
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > backup-$(date +%F).sql.gz
# restore into an empty database
gunzip -c backup-YYYY-MM-DD.sql.gz | docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml \
  exec -T postgres sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'
```

Data lives in the `postgres_data` volume; never run `docker compose down -v` on
production. A restore drill was **not** executed during validation: perform one
before relying on backups.

## 9. Troubleshooting

- `migrate` fails: `docker compose logs migrate` (DB credentials, extension permission).
- `api` restarts immediately: `docker compose logs api` shows the config
  validation error (secrets are never printed). A `cors_origins` parse error
  means the JSON list is malformed or unquoted.
- `/health/ready` is 503: DB or Redis unreachable; liveness stays 200 and the
  API reconnects automatically when they return.
- `/metrics` is 401: missing/incorrect bearer token.
- Docker build slow/fails on pip downloads: network to PyPI; the Dockerfile uses
  retries/timeouts, re-run the build.

## 10. Pre-go-live sign-off

- [ ] Secrets generated and stored outside git
- [ ] Reverse proxy with TLS in place, `/metrics` restricted
- [ ] Smoke test passes against the real URL
- [ ] OpenAI path verified with real credentials (if used)
- [ ] Backup taken and restore tested
- [ ] GitHub Actions workflow green on `main`
