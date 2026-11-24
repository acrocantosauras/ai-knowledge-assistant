# Deployment Readiness Summary

Status as of the last validation run (2026-11-24, Windows + Docker Desktop, isolated compose project `aika-prodtest`).

**Verdict: deployable for a controlled production rollout once the items under "Manual configuration required" are done. Real OpenAI providers and GitHub Actions have NOT been executed, so they are not claimed as verified.**

## Verification results

| Area | Status | Evidence |
|---|---|---|
| Backend tests | PASS | `pytest`: 186 passed (real PostgreSQL + pgvector) |
| Lint / format | PASS | `ruff check` and `ruff format --check` clean |
| Frontend | PASS | oxlint clean, `tsc -b` clean, vitest 15/15, `vite build` OK |
| Docker build, non-root, read-only FS | PASS | image builds; runs as uid 1000; `touch /app/x` fails; txt/docx/PDF uploads work with `read_only: true`, `cap_drop: ALL` |
| Migrations | PASS | `migrate` one-shot service applies 3 migrations in order on an empty DB; API starts only after it exits 0 |
| Smoke test | PASS | `scripts/smoke-test.sh`: 26/26 against the production stack |
| Metrics security | PASS | no token -> 401, wrong token -> 401, correct token -> 200, `/health*` unaffected |
| Auth / ingestion / RAG / citations | PASS | automated tests + smoke test (mock providers) |
| Streaming SSE | PASS | `tests/test_metrics_auth_and_providers.py`: event order (sources -> chunks -> final), citations persisted, error events sanitized, client disconnect safe |
| pgvector | PASS | `tests/test_pgvector.py` against PostgreSQL: extension, vector column, insert, cosine ranking, threshold, per-user scope, dimension mismatch |
| Container reliability | PASS | `scripts/reliability-test.sh`: 17/17 (restart, Redis outage, Postgres outage, recreate with persisted data, SIGTERM exit 0) |
| OpenAI providers (real API) | NEEDS CONFIGURATION | no API key available. Error translation (invalid key, rate limit, timeout, server error, dimension mismatch) is covered by tests using *simulated* SDK errors only |
| GitHub Actions | NOT RUN | `ci.yml` parses as valid YAML; workflow never executed |
| TLS | NOT PROVIDED BY APP | must be terminated by a reverse proxy / load balancer |

## Defects found and fixed during validation

- Docker image could not build the frontend (Vite 8 needs Node >= 20.19; image used 20.18) -> Node 22.12.
- No migrations ran on deploy -> `migrate` service.
- `openai` was not a declared dependency, so the OpenAI providers could never work in the image -> added.
- pgvector similarity search passed a Python list into raw SQL and failed under asyncpg; **semantic search with a real embedding provider never worked** -> rewritten with pgvector's cosine-distance operator.
- Searching with a different embedding dimension would raise a SQL error -> filtered by dimension.
- Redis outage turned every request (including `/health`) into a 500 -> rate limiter now falls back to in-memory.
- PDF/DOCX extraction passed raw bytes to the parsers; corrupt/non-UTF-8/oversize uploads returned 500 or buffered unbounded data -> fixed (422/413).
- Streaming answers did not persist their citations -> persisted.
- `/metrics` was public -> bearer token required in production.
- Provider failures leaked as generic 500s -> mapped to 429/502/504 with sanitized messages.

## Known limitations

- With `APP_EMBEDDING_PROVIDER=mock` (the default), retrieval is a plain substring (`ILIKE`) match of the whole question, not semantic search. Use `openai` embeddings for real semantic retrieval.
- The `embedding` column is an unconstrained `vector`, so there is no HNSW/IVFFlat index; similarity search is a sequential scan per user. Fine for small corpora, slow at scale.
- Changing `APP_EMBEDDING_MODEL`/dimension requires re-ingesting documents (old vectors are ignored, not migrated).
- Rate limits are per client IP. Behind a proxy, set `FORWARDED_ALLOW_IPS` for uvicorn to the proxy address, otherwise all users share the proxy's IP. In-memory fallback limits are per process.
- `/metrics` token protection is a single shared bearer token; no rotation mechanism beyond redeploying.
- No refresh tokens / token revocation: JWTs are valid until expiry (30 min default).
- Single `api` replica tested; multi-replica behaviour not tested.
- Uploads are processed synchronously in the request (10 MB cap).
- Backups are manual (`pg_dump`); restore procedure documented but a full restore drill was not executed.

## Manual configuration required

1. Create `.env.production` from `.env.production.example` with strong `POSTGRES_PASSWORD`, `APP_JWT_SECRET_KEY` (>= 32 chars), `APP_METRICS_TOKEN` (>= 16 chars), `APP_CORS_ORIGINS`.
2. Put a TLS-terminating reverse proxy in front (see `deploy/nginx.example.conf`) and restrict `/metrics`.
3. For real AI answers: set `APP_LLM_PROVIDER=openai`, `APP_EMBEDDING_PROVIDER=openai`, `APP_OPENAI_API_KEY`, then run a real-provider check (see checklist section 6).
4. Schedule database backups and test a restore.
5. Run the GitHub Actions workflow once and confirm it is green.
