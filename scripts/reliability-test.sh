#!/usr/bin/env bash
# =============================================================================
# Container reliability test (restart, dependency outage, persistence, uploads)
# =============================================================================
# Runs against an ALREADY RUNNING production compose project and only touches
# containers of that project. It never removes volumes.
#
# Usage:
#   COMPOSE="docker compose -p myproj --env-file .env.production \
#            -f docker-compose.yml -f docker-compose.prod.yml" \
#   METRICS_TOKEN=... ./scripts/reliability-test.sh [BASE_URL]
# =============================================================================
set -uo pipefail

BASE_URL="${1:-http://localhost:8000}"
: "${COMPOSE:?set COMPOSE to the docker compose command for the project}"
PASS=0
FAIL=0
pass() { PASS=$((PASS + 1)); echo "  PASS $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  FAIL $1"; }

code() { curl -s -o /dev/null -w "%{http_code}" "$@" 2>/dev/null || echo 000; }

wait_ready() { # $1 = timeout seconds
  local t=0
  while [ "$t" -lt "$1" ]; do
    [ "$(code "$BASE_URL/health/ready")" = "200" ] && return 0
    sleep 2; t=$((t + 2))
  done
  return 1
}

EMAIL="rel-$(date +%s)@test.example.com"
PASSWORD="Reliab$(date +%s)!"
curl -s -o /dev/null -X POST "$BASE_URL/api/v1/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"display_name\":\"rel\"}"
TOKEN=$(curl -s -X POST "$BASE_URL/api/v1/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
AUTH=(-H "Authorization: Bearer $TOKEN")
[ -n "$TOKEN" ] && pass "registered + logged in" || { fail "login"; exit 1; }

echo "--- read-only FS + dropped caps: uploads (txt/pdf/docx) ---"
TMPD=$(mktemp -d)
echo "Paris is the capital of France." > "$TMPD/a.txt"
"${PYTHON:-python}" -c "
import docx,sys
d = docx.Document(); d.add_paragraph('Berlin is the capital of Germany.')
d.save(sys.argv[1])" "$TMPD/a.docx" > "$TMPD/gen.log" 2>&1 || echo "  (python-docx unavailable on host; set PYTHON)"
printf '%%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 20 100 Td (Madrid is in Spain) Tj ET\nendstream endobj\n5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\ntrailer<</Root 1 0 R/Size 6>>\n%%%%EOF' > "$TMPD/a.pdf"
for f in a.txt a.docx a.pdf; do
  [ -f "$TMPD/$f" ] || { fail "could not create $f"; continue; }
  s=$(code -X POST "$BASE_URL/api/v1/documents/upload" "${AUTH[@]}" -F "file=@$TMPD/$f")
  # a hand-written PDF may legitimately be rejected as unreadable (422), but
  # it must never be a 500 caused by the read-only filesystem
  if [ "$s" = "201" ] || { [ "$f" = "a.pdf" ] && [ "$s" = "422" ]; }; then pass "upload $f -> $s"; else fail "upload $f -> $s"; fi
done
rm -rf "$TMPD"

echo "--- write attempt on read-only root FS must fail ---"
if $COMPOSE exec -T api sh -c 'touch /app/x 2>/dev/null'; then fail "root FS writable"; else pass "root FS is read-only"; fi

DOCS_BEFORE=$(curl -s "${AUTH[@]}" "$BASE_URL/api/v1/documents/" | grep -o '"total":[0-9]*' | head -1)

echo "--- API container restart ---"
$COMPOSE restart api >/dev/null 2>&1
wait_ready 90 && pass "api recovered after restart" || fail "api did not recover after restart"
[ "$(code "${AUTH[@]}" "$BASE_URL/api/v1/users/me/profile")" = "200" ] && pass "existing JWT valid after restart" || fail "JWT invalid after restart"

echo "--- Redis outage and recovery ---"
$COMPOSE stop redis >/dev/null 2>&1
sleep 3
echo "  liveness during redis outage: $(code "$BASE_URL/health") ; readiness: $(code "$BASE_URL/health/ready")"
[ "$(code "$BASE_URL/health")" = "200" ] && pass "liveness stays 200 with redis down" || fail "liveness failed with redis down"
$COMPOSE start redis >/dev/null 2>&1
wait_ready 60 && pass "readiness recovers after redis returns" || fail "readiness did not recover after redis"

echo "--- Postgres outage and recovery ---"
$COMPOSE stop postgres >/dev/null 2>&1
sleep 3
s=$(code "$BASE_URL/health/ready")
[ "$s" = "503" ] && pass "readiness -> 503 with postgres down" || fail "readiness with postgres down -> $s (expected 503)"
[ "$(code "$BASE_URL/health")" = "200" ] && pass "liveness stays 200 with postgres down" || fail "liveness failed with postgres down"
$COMPOSE start postgres >/dev/null 2>&1
wait_ready 90 && pass "readiness recovers after postgres returns (no api restart)" || fail "api did not reconnect to postgres"

echo "--- Data survives container recreation (volumes kept) ---"
$COMPOSE up -d --force-recreate --no-deps postgres api >/dev/null 2>&1
wait_ready 120 && pass "stack healthy after recreate" || fail "stack unhealthy after recreate"
DOCS_AFTER=$(curl -s "${AUTH[@]}" "$BASE_URL/api/v1/documents/" | grep -o '"total":[0-9]*' | head -1)
[ -n "$DOCS_BEFORE" ] && [ "$DOCS_BEFORE" = "$DOCS_AFTER" ] && pass "documents persisted ($DOCS_AFTER)" || fail "documents changed: $DOCS_BEFORE -> $DOCS_AFTER"
[ "$(code -X POST "$BASE_URL/api/v1/auth/login" -H 'Content-Type: application/json' -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")" = "200" ] && pass "user persisted (login works)" || fail "login failed after recreate"

echo "--- Graceful shutdown ---"
start=$(date +%s)
$COMPOSE stop api >/dev/null 2>&1
dur=$(( $(date +%s) - start ))
code_exit=$(docker inspect -f '{{.State.ExitCode}}' "$($COMPOSE ps -aq api)" 2>/dev/null || echo "?")
echo "  stop took ${dur}s, exit code $code_exit"
[ "$code_exit" = "0" ] && pass "api exited 0 on SIGTERM (${dur}s)" || fail "api exit code $code_exit on stop"
$COMPOSE start api >/dev/null 2>&1
wait_ready 90 && pass "api back after stop/start" || fail "api not back"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
