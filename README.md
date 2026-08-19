# AI Knowledge Assistant

A full-stack RAG (Retrieval-Augmented Generation) application that lets users upload documents, search them semantically, and ask questions powered by an LLM with source citations.

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌────────────┐
│   Frontend   │────▶│   FastAPI Backend │────▶│ PostgreSQL  │
│  React/Vite  │     │    (Python 3.12)  │     │ + pgvector  │
└─────────────┘     └──────────────────┘     └────────────┘
                            │
                   ┌────────┴────────┐
                   │   LLM Provider   │
                   │ (OpenAI / Mock)  │
                   └─────────────────┘
```

## Features

- **Authentication** — JWT-based registration and login
- **Document Upload** — PDF, TXT, DOCX with automatic text extraction
- **Chunking & Embeddings** — Configurable text chunking with pgvector embeddings
- **RAG Search** — Semantic search over document chunks
- **Question Answering** — LLM-powered answers grounded in your documents
- **Conversations** — Persistent chat history with message storage
- **Source Citations** — Every answer includes source references
- **User Isolation** — Complete data isolation between users
- **Rate Limiting** — Configurable per-endpoint rate limits (disabled in tests)
- **Monitoring** — Prometheus metrics and health probes
- **Frontend** — React SPA with error boundary, dashboard, documents, chat, and settings

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy (async), Pydantic v2
- **Database**: PostgreSQL 16 + pgvector
- **Auth**: JWT (PyJWT), Argon2 password hashing (pwdlib)
- **LLM**: OpenAI API / Mock provider
- **Frontend**: React 19, TypeScript, Vite, oxlint
- **Testing**: pytest, vitest, @testing-library/react
- **Deployment**: Docker Compose

## Quick Start (Development)

### Prerequisites

- Python 3.12+
- PostgreSQL 16 with pgvector
- Node.js 20+ (for frontend development)

### Setup

```bash
# Clone and setup
git clone <repo-url>
cd ai-knowledge-assistant

# Copy environment file
cp .env.example .env

# Edit .env with your settings (especially APP_JWT_SECRET_KEY)
python -c "import secrets; print(secrets.token_urlsafe(64))"
# Paste the output into APP_JWT_SECRET_KEY in .env

# Install Python dependencies
pip install -e ".[dev]"

# Run database migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload --port 8000

# In another terminal, start the frontend
cd frontend && npm install && npm run dev
```

### Docker Compose (Development)

```bash
# Start everything with Docker
docker compose up --build

# The app will be available at:
# - Frontend: http://localhost:3000
# - Backend API: http://localhost:8000
# - API docs: http://localhost:8000/docs
# - PostgreSQL: localhost:5432
# - Redis: localhost:6379
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENVIRONMENT` | `development` | `development`, `test`, `staging`, `production` |
| `APP_DATABASE_URL` | (see .env.example) | PostgreSQL connection URL |
| `APP_JWT_SECRET_KEY` | — | **Required in production.** Secret key for JWT tokens |
| `APP_JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `APP_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Token expiry time |
| `APP_EMBEDDING_PROVIDER` | `mock` | `openai`, `local`, or `mock` |
| `APP_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model name |
| `APP_EMBEDDING_DIMENSION` | `1536` | Embedding vector dimension |
| `APP_OPENAI_API_KEY` | — | OpenAI API key (required if provider=openai) |
| `APP_CHUNK_SIZE` | `500` | Text chunk size in characters |
| `APP_CHUNK_OVERLAP` | `100` | Overlap between chunks |
| `APP_LLM_PROVIDER` | `mock` | `openai` or `mock` |
| `APP_LLM_MODEL` | `gpt-4o-mini` | LLM model name |
| `APP_LLM_TEMPERATURE` | `0.7` | LLM temperature |
| `APP_LLM_MAX_TOKENS` | `1024` | Max tokens in LLM response |
| `APP_CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed CORS origins |
| `APP_RATE_LIMIT_DEFAULT` | `60/minute` | Global rate limit |
| `APP_RATE_LIMIT_AUTH` | `10/minute` | Auth endpoint limit |
| `APP_RATE_LIMIT_UPLOAD` | `20/hour` | Document upload limit |
| `APP_RATE_LIMIT_RAG` | `30/minute` | RAG search limit |
| `APP_RATE_LIMIT_QA` | `20/minute` | QA endpoint limit |
| `APP_REDIS_URL` | — | Redis URL (optional, for distributed rate limiting) |

## Database

### Migrations

```bash
# Run all migrations
alembic upgrade head

# Create a new migration
alembic revision --autogenerate -m "description"
```

### Tables

- `users` — User accounts with password hashes and preferences
- `documents` — Uploaded document metadata and content
- `document_chunks` — Text chunks from documents
- `chunk_embeddings` — pgvector embeddings for chunks
- `conversations` — Chat conversations
- `messages` — Conversation messages

### Backup & Recovery

PostgreSQL data is persisted in the `postgres_data` Docker volume. To back up the database:

```bash
# Backup (run from host, not inside container)
docker compose exec -T postgres pg_dump -U ai_knowledge_user ai_knowledge_assistant > backup_$(date +%Y%m%d_%H%M%S).sql

# Backup with compression
docker compose exec -T postgres pg_dump -U ai_knowledge_user ai_knowledge_assistant | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz
```

To restore from a backup:

```bash
# Restore from .sql
docker compose exec -T postgres psql -U ai_knowledge_user ai_knowledge_assistant < backup.sql

# Restore from .sql.gz
gunzip -c backup.sql.gz | docker compose exec -T postgres psql -U ai_knowledge_user ai_knowledge_assistant
```

**Important:** Backup files contain user data and credentials — store them securely and exclude them from version control.

## API Endpoints

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register` | Register a new user |
| POST | `/api/v1/auth/login` | Login and get JWT token |

### Documents

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/documents/upload` | Upload a document (PDF/TXT/DOCX) |
| GET | `/api/v1/documents/` | List user's documents |
| GET | `/api/v1/documents/{id}` | Get document details |
| DELETE | `/api/v1/documents/{id}` | Delete a document |

### RAG

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/rag/search` | Search document chunks |
| POST | `/api/v1/rag/ask` | Ask a question using RAG |
| POST | `/api/v1/rag/ask/stream` | Ask with streaming response |

### QA

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/qa/ask` | Ask question (creates conversation) |
| POST | `/api/v1/qa/ask/stream` | Ask with SSE streaming |

### Conversations

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/conversations/` | Create conversation |
| GET | `/api/v1/conversations/` | List conversations |
| GET | `/api/v1/conversations/{id}` | Get conversation with messages |
| PUT | `/api/v1/conversations/{id}` | Update conversation |
| DELETE | `/api/v1/conversations/{id}` | Delete conversation |
| POST | `/api/v1/conversations/{id}/messages` | Add message |

### Health & Monitoring

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Liveness probe (200 if app is running) |
| GET | `/health/ready` | Readiness probe (verifies DB + Redis) |
| GET | `/metrics` | Prometheus metrics |

### Users

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/users/me/preferences` | Get preferences |
| PATCH | `/api/v1/users/me/preferences` | Update preferences |
| GET | `/api/v1/users/me/profile` | Get user profile |

## Testing

### Backend

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_auth.py -v

# Lint check
ruff check src/ tests/

# Format check
ruff format --check src/ tests/
```

### Frontend

```bash
cd frontend

# Run all checks
npm run lint        # oxlint (0 warnings, 0 errors)
npm run typecheck   # TypeScript compilation
npm run test        # vitest unit tests
npm run build       # Production build
```

## Production Deployment

### 1. Generate Secrets

```bash
# Generate a secure JWT secret key
python -c "import secrets; print(secrets.token_urlsafe(64))"

# Generate a strong database password
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Create Production Environment File

```bash
cp .env.production.example .env.production
# Edit .env.production with your actual values
```

### 3. Deploy with Docker Compose

```bash
# Build and start services
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --env-file .env.production up -d --build

# Run database migrations
docker compose exec api alembic upgrade head

# Verify health
curl http://localhost:8000/health
curl http://localhost:8000/health/ready
```

### 4. Production Security Configuration

The production environment enforces:

- **JWT secret key** — Must be set and not be the default value
- **No exposed database ports** — PostgreSQL and Redis are internal-only
- **Rate limiting** — Configurable per-endpoint limits
- **CORS** — Restricted to configured origins
- **File upload limits** — 10 MB max, PDF/TXT/DOCX only
- **Password hashing** — Argon2 via pwdlib
- **User isolation** — All queries filtered by user_id
- **Safe logging** — Credentials redacted from logs

### 5. Health Checks

```bash
# Liveness — confirms the app process is running
curl http://localhost:8000/health
# Response: {"status": "ok", "service": "AI Knowledge Assistant", ...}

# Readiness — confirms DB and Redis connectivity
curl http://localhost:8000/health/ready
# Response: {"status": "ok", "checks": {"database": "ok"}, ...}
```

### 6. Rollback Procedure

```bash
# Stop the current deployment
docker compose down

# Check out the previous release tag
git checkout <previous-tag>

# Rebuild and deploy
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --env-file .env.production up -d --build

# Run migrations for the previous version if needed
docker compose exec api alembic upgrade head
```

**Database rollback:** If a migration needs to be reverted:

```bash
docker compose exec api alembic downgrade -1
```

## Monitoring

### Prometheus

The `/metrics` endpoint exposes Prometheus-compatible metrics:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: ai-knowledge-assistant
    static_configs:
      - targets: ["localhost:8000"]
    metrics_path: /metrics
    scrape_interval: 15s
```

**Available metrics:**

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `http_requests_total` | Counter | method, endpoint, status | Total HTTP requests |
| `http_request_duration_seconds` | Histogram | method, endpoint | Request latency |
| `http_requests_in_flight` | Gauge | — | Requests being processed |
| `documents_uploaded_total` | Counter | user_id | Documents uploaded |
| `conversations_created_total` | Counter | user_id | Conversations created |
| `qa_questions_total` | Counter | provider | QA questions asked |
| `qa_latency_seconds` | Histogram | provider | QA response latency |
| `rag_search_total` | Counter | — | RAG search requests |
| `rag_chunks_returned` | Histogram | — | Chunks per RAG search |

Path parameters are normalised to `{id}` for low-cardinality labels.

## Logging

The application uses Python's standard `logging` module with a configurable level.

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |

### Log format

```
2025-01-15 10:30:00 | INFO | app.main | Application startup complete
2025-01-15 10:30:01 | WARNING | app.core.redis | Redis connection check failed: Connection refused
```

### Security notes

- **Credentials are never logged.** Redis URLs have passwords redacted. Database connection strings are not included in application logs.
- **Production should use `INFO` or `WARNING`** — `DEBUG` logs may include request bodies and timing details.
- **Structured `extra` fields** are used for key context (attempt numbers, latency, environment) — grep-friendly.

### Verifying logging in production

```bash
# Check application logs
docker compose logs api | tail -20

# Verify log level
docker compose exec api python -c "import logging; print(logging.getLogger().level)"

# Watch for errors
docker compose logs api -f | grep -i error
```

## Troubleshooting

### Database connection errors
- Ensure PostgreSQL is running and accessible
- Check `APP_DATABASE_URL` in `.env`
- Run `alembic upgrade head` to create tables

### Authentication errors
- Ensure `APP_JWT_SECRET_KEY` is set in `.env`
- Tokens expire after `APP_ACCESS_TOKEN_EXPIRE_MINUTES` (default 30)

### Upload failures
- Supported formats: PDF, TXT, DOCX
- Max file size: 10 MB
- Check that required Python packages are installed (pypdf, python-docx)

### Frontend connection issues
- Backend must be running on port 8000
- Check `APP_CORS_ORIGINS` includes your frontend URL
- Vite dev server proxies `/api` to `localhost:8000` by default

### LLM failures
- **Missing API key:** Ensure `APP_OPENAI_API_KEY` is set when `APP_LLM_PROVIDER=openai`
- **OpenAI rate limits:** Check OpenAI usage dashboard; the app returns a safe error without crashing
- **Timeout:** Default timeout is 60s (`APP_LLM_TIMEOUT`); increase for large prompts
- **Streaming interruption:** The frontend gracefully handles dropped SSE connections
- **Mock provider:** Use `APP_LLM_PROVIDER=mock` for development without OpenAI costs

### Redis
- Redis is optional — used for distributed rate limiting and caching
- When `APP_REDIS_URL` is empty, in-memory rate limiting is used
- Check Redis connectivity via `GET /health/ready`
- If Redis is unavailable, the app continues with in-memory rate limiting (no crash)

### Rate limiting
- Rate limits are disabled in the test environment (`APP_ENVIRONMENT=test`)
- Auth endpoints: 10 requests/minute (default)
- Upload: 20 requests/hour (default)
- RAG search: 30 requests/minute (default)
- QA: 20 requests/minute (default)
- Check limits via the 429 response `retry_after` field

### Production verification commands

```bash
# Health check
curl -s http://localhost:8000/health | python -m json.tool

# Readiness check (verifies DB + Redis)
curl -s http://localhost:8000/health/ready | python -m json.tool

# Metrics
curl -s http://localhost:8000/metrics | head -20

# Test authentication
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email": "test@example.com", "password": "TestPassword123!"}'

# Test document upload
curl -s -X POST http://localhost:8000/api/v1/documents/upload \
  -H 'Authorization: Bearer <token>' \
  -F 'file=@test.txt'

# Test RAG search
curl -s -X POST http://localhost:8000/api/v1/rag/search \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{"query": "test query"}'

# Test QA
curl -s -X POST http://localhost:8000/api/v1/qa/ask \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{"question": "What is this about?"}'
```
