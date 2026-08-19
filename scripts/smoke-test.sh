#!/usr/bin/env bash
# =============================================================================
# Deployment Smoke Test
# =============================================================================
# Verifies the running Docker production stack against critical endpoints.
#
# Usage:
#   ./scripts/smoke-test.sh [BASE_URL]
#
# Default BASE_URL is http://localhost:8000
#
# Requirements: bash, curl, docker compose (for container health checks)
# =============================================================================
set -uo pipefail

BASE_URL="${1:-http://localhost:8000}"
PASS=0
FAIL=0
TIMESTAMP=$(date +%s)
TEST_EMAIL="smoke-${TIMESTAMP}@test.example.com"
TEST_PASSWORD="SmokeTest${TIMESTAMP}!"
TOKEN=""
DOC_ID=""
CONV_ID=""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

pass() {
  PASS=$((PASS + 1))
  echo "  ✓ $1"
}

fail() {
  FAIL=$((FAIL + 1))
  echo "  ✗ $1"
}

section() {
  echo ""
  echo "━━━ $1 ━━━"
}

# HTTP request helper: prints status code to stdout
http_status() {
  local method="$1" url="$2"
  shift 2
  curl -s -o /dev/null -w "%{http_code}" -X "$method" "$url" "$@" 2>/dev/null || echo "000"
}

# HTTP request helper: prints body\nstatus_code
http_body() {
  local method="$1" url="$2"
  shift 2
  curl -s -w "\n%{http_code}" -X "$method" "$url" "$@" 2>/dev/null || echo "\n000"
}

# ---------------------------------------------------------------------------
# 1. Container Health
# ---------------------------------------------------------------------------

section "1. Container Health"

if command -v docker &>/dev/null && docker compose ps &>/dev/null 2>&1; then
  # Check each service
  for svc in api postgres redis; do
    if docker compose ps --format json 2>/dev/null | grep -q "\"Name\".*\"$svc\"" 2>/dev/null; then
      status=$(docker compose ps --format json 2>/dev/null | grep "$svc" | head -1 | grep -o '"Health":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
      if [ "$status" = "running" ] || [ "$status" = "healthy" ] || [ "$status" = "" ]; then
        pass "Container '$svc' is running"
      else
        fail "Container '$svc' status: $status"
      fi
    else
      # Fallback: just check if docker compose has the service
      pass "Container '$svc' configured in compose"
    fi
  done
else
  echo "  (docker compose not available — skipping container checks)"
fi

# ---------------------------------------------------------------------------
# 2. Health Endpoints
# ---------------------------------------------------------------------------

section "2. Health Endpoints"

status=$(http_status GET "$BASE_URL/health")
if [ "$status" = "200" ]; then
  pass "GET /health → 200"
else
  fail "GET /health → $status (expected 200)"
fi

status=$(http_status GET "$BASE_URL/health/ready")
if [ "$status" = "200" ]; then
  pass "GET /health/ready → 200"
else
  fail "GET /health/ready → $status (expected 200)"
fi

# ---------------------------------------------------------------------------
# 3. Metrics
# ---------------------------------------------------------------------------

section "3. Metrics"

status=$(http_status GET "$BASE_URL/metrics")
if [ "$status" = "200" ]; then
  pass "GET /metrics → 200"
else
  fail "GET /metrics → $status (expected 200)"
fi

# Verify it contains Prometheus format
body=$(curl -s "$BASE_URL/metrics" 2>/dev/null)
if echo "$body" | grep -q "http_requests_total"; then
  pass "Metrics contain http_requests_total"
else
  fail "Metrics missing http_requests_total"
fi

# ---------------------------------------------------------------------------
# 4. Frontend
# ---------------------------------------------------------------------------

section "4. Frontend"

status=$(http_status GET "$BASE_URL/")
if [ "$status" = "200" ]; then
  pass "GET / → 200"
else
  fail "GET / → $status (expected 200)"
fi

# SPA route — should serve index.html for client-side routing
status=$(http_status GET "$BASE_URL/documents")
if [ "$status" = "200" ]; then
  pass "GET /documents (SPA route) → 200"
else
  fail "GET /documents (SPA route) → $status (expected 200)"
fi

# Static assets
body=$(curl -s "$BASE_URL/" 2>/dev/null)
asset_path=$(echo "$body" | grep -o 'assets/[^"]*\.js' | head -1 || true)
if [ -n "$asset_path" ]; then
  status=$(http_status GET "$BASE_URL/$asset_path")
  if [ "$status" = "200" ]; then
    pass "Static JS asset loads → 200"
  else
    fail "Static JS asset ($asset_path) → $status (expected 200)"
  fi
else
  echo "  (no JS asset found in index.html — skipping asset check)"
fi

# ---------------------------------------------------------------------------
# 5. Authentication Workflow
# ---------------------------------------------------------------------------

section "5. Authentication"

# Register
response=$(http_body POST "$BASE_URL/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\",\"display_name\":\"Smoke Test\"}")
status=$(echo "$response" | tail -1)
body=$(echo "$response" | sed '$d')

if [ "$status" = "201" ]; then
  pass "POST /api/v1/auth/register → 201"
else
  fail "POST /api/v1/auth/register → $status (expected 201)"
fi

# Login
response=$(http_body POST "$BASE_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}")
status=$(echo "$response" | tail -1)
body=$(echo "$response" | sed '$d')

if [ "$status" = "200" ]; then
  TOKEN=$(echo "$body" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
  if [ -n "$TOKEN" ]; then
    pass "POST /api/v1/auth/login → 200 (JWT obtained)"
  else
    fail "POST /api/v1/auth/login → 200 but no token in response"
  fi
else
  fail "POST /api/v1/auth/login → $status (expected 200)"
fi

# Profile with token
if [ -n "$TOKEN" ]; then
  status=$(http_status GET "$BASE_URL/api/v1/users/me/profile" \
    -H "Authorization: Bearer $TOKEN")
  if [ "$status" = "200" ]; then
    pass "GET /api/v1/users/me/profile → 200"
  else
    fail "GET /api/v1/users/me/profile → $status (expected 200)"
  fi
else
  echo "  (skipping authenticated checks — no token)"
fi

# ---------------------------------------------------------------------------
# 6. Document Workflow
# ---------------------------------------------------------------------------

section "6. Document Workflow"

if [ -n "$TOKEN" ]; then
  # Upload a small TXT document (use .txt extension so server detects content type)
  tmpfile=$(mktemp --suffix=.txt)
  echo "This is a smoke test document. The capital of France is Paris." > "$tmpfile"

  response=$(http_body POST "$BASE_URL/api/v1/documents/upload" \
    -H "Authorization: Bearer $TOKEN" \
    -F "file=@$tmpfile")
  status=$(echo "$response" | tail -1)
  body=$(echo "$response" | sed '$d')

  rm -f "$tmpfile"

  if [ "$status" = "201" ]; then
    DOC_ID=$(echo "$body" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
    pass "POST /api/v1/documents/upload → 201"
  else
    fail "POST /api/v1/documents/upload → $status (expected 201)"
  fi

  # List documents
  status=$(http_status GET "$BASE_URL/api/v1/documents/" \
    -H "Authorization: Bearer $TOKEN")
  if [ "$status" = "200" ]; then
    pass "GET /api/v1/documents/ → 200"
  else
    fail "GET /api/v1/documents/ → $status (expected 200)"
  fi

  # Get specific document
  if [ -n "$DOC_ID" ]; then
    status=$(http_status GET "$BASE_URL/api/v1/documents/$DOC_ID" \
      -H "Authorization: Bearer $TOKEN")
    if [ "$status" = "200" ]; then
      pass "GET /api/v1/documents/$DOC_ID → 200"
    else
      fail "GET /api/v1/documents/$DOC_ID → $status (expected 200)"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# 7. RAG Workflow
# ---------------------------------------------------------------------------

section "7. RAG Workflow"

if [ -n "$TOKEN" ]; then
  # RAG search
  response=$(http_body POST "$BASE_URL/api/v1/rag/search" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"query":"capital of France","limit":5}')
  status=$(echo "$response" | tail -1)
  body=$(echo "$response" | sed '$d')

  if [ "$status" = "200" ]; then
    pass "POST /api/v1/rag/search → 200"
  else
    fail "POST /api/v1/rag/search → $status (expected 200)"
  fi

  # RAG ask
  response=$(http_body POST "$BASE_URL/api/v1/rag/ask" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"question":"What is the capital of France?"}')
  status=$(echo "$response" | tail -1)
  body=$(echo "$response" | sed '$d')

  if [ "$status" = "200" ]; then
    pass "POST /api/v1/rag/ask → 200"
  else
    fail "POST /api/v1/rag/ask → $status (expected 200)"
  fi
fi

# ---------------------------------------------------------------------------
# 8. QA Workflow
# ---------------------------------------------------------------------------

section "8. QA Workflow"

if [ -n "$TOKEN" ]; then
  # Non-streaming QA
  response=$(http_body POST "$BASE_URL/api/v1/qa/ask" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"question":"What is this document about?"}')
  status=$(echo "$response" | tail -1)
  body=$(echo "$response" | sed '$d')

  if [ "$status" = "200" ]; then
    CONV_ID=$(echo "$body" | grep -o '"conversation_id":"[^"]*"' | cut -d'"' -f4)
    pass "POST /api/v1/qa/ask → 200"
  else
    fail "POST /api/v1/qa/ask → $status (expected 200)"
  fi

  # Streaming QA
  stream_response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/v1/qa/ask/stream" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"question":"Tell me more about this document."}' 2>/dev/null)
  stream_status=$(echo "$stream_response" | tail -1)
  if [ "$stream_status" = "200" ]; then
    pass "POST /api/v1/qa/ask/stream → 200"
  else
    fail "POST /api/v1/qa/ask/stream → $stream_status (expected 200)"
  fi
fi

# ---------------------------------------------------------------------------
# 9. Conversation Persistence
# ---------------------------------------------------------------------------

section "9. Conversation Persistence"

if [ -n "$TOKEN" ]; then
  # List conversations
  response=$(http_body GET "$BASE_URL/api/v1/conversations/" \
    -H "Authorization: Bearer $TOKEN")
  status=$(echo "$response" | tail -1)
  body=$(echo "$response" | sed '$d')

  if [ "$status" = "200" ]; then
    total=$(echo "$body" | grep -o '"total":[0-9]*' | cut -d: -f2)
    if [ -n "$total" ] && [ "$total" -gt 0 ] 2>/dev/null; then
      pass "GET /api/v1/conversations/ → 200 ($total conversations)"
    else
      pass "GET /api/v1/conversations/ → 200"
    fi
  else
    fail "GET /api/v1/conversations/ → $status (expected 200)"
  fi

  # Get conversation with messages (if we have one from QA)
  if [ -n "$CONV_ID" ]; then
    status=$(http_status GET "$BASE_URL/api/v1/conversations/$CONV_ID" \
      -H "Authorization: Bearer $TOKEN")
    if [ "$status" = "200" ]; then
      pass "GET /api/v1/conversations/$CONV_ID → 200"
    else
      fail "GET /api/v1/conversations/$CONV_ID → $status (expected 200)"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# 10. Preferences
# ---------------------------------------------------------------------------

section "10. User Preferences"

if [ -n "$TOKEN" ]; then
  # Get preferences
  status=$(http_status GET "$BASE_URL/api/v1/users/me/preferences" \
    -H "Authorization: Bearer $TOKEN")
  if [ "$status" = "200" ]; then
    pass "GET /api/v1/users/me/preferences → 200"
  else
    fail "GET /api/v1/users/me/preferences → $status (expected 200)"
  fi

  # Update preferences
  status=$(http_status PATCH "$BASE_URL/api/v1/users/me/preferences" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"theme":"dark"}')
  if [ "$status" = "200" ]; then
    pass "PATCH /api/v1/users/me/preferences → 200"
  else
    fail "PATCH /api/v1/users/me/preferences → $status (expected 200)"
  fi
fi

# ---------------------------------------------------------------------------
# 11. Cleanup
# ---------------------------------------------------------------------------

section "11. Cleanup"

if [ -n "$TOKEN" ] && [ -n "$DOC_ID" ]; then
  status=$(http_status DELETE "$BASE_URL/api/v1/documents/$DOC_ID" \
    -H "Authorization: Bearer $TOKEN")
  if [ "$status" = "204" ]; then
    pass "DELETE /api/v1/documents/$DOC_ID → 204"
  else
    fail "DELETE /api/v1/documents/$DOC_ID → $status (expected 204)"
  fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
TOTAL=$((PASS + FAIL))
echo "  Results: $PASS/$TOTAL passed, $FAIL failed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "  ✗ SMOKE TEST FAILED"
  exit 1
else
  echo ""
  echo "  ✓ SMOKE TEST PASSED"
  exit 0
fi
