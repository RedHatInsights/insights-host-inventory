#!/bin/bash
#
# Demo script for the F2F tracing presentation.
# Spins up the local environment, ingests hosts, makes API requests,
# and opens Grafana so you can show live traces in Tempo.
#
# Usage:
#   ./scripts/demo-tracing.sh          # Full setup (build + start + seed + requests)
#   ./scripts/demo-tracing.sh --quick  # Skip build, just seed data and make requests
#   ./scripts/demo-tracing.sh --clean  # Tear everything down
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

NUM_HOSTS="${NUM_HOSTS:-100}"
API_URL="http://localhost:8080/api/inventory/v1"
ORG_ID="${INVENTORY_HOST_ACCOUNT:-321}"
IDENTITY=$(echo -n "{\"identity\":{\"org_id\":\"$ORG_ID\",\"auth_type\":\"basic-auth\",\"type\":\"User\",\"user\":{\"username\":\"demo-user\",\"email\":\"demo@example.com\",\"is_org_admin\":true}}}" | base64 -w0 2>/dev/null || echo -n "{\"identity\":{\"org_id\":\"$ORG_ID\",\"auth_type\":\"basic-auth\",\"type\":\"User\",\"user\":{\"username\":\"demo-user\",\"email\":\"demo@example.com\",\"is_org_admin\":true}}}" | base64)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[demo]${NC} $1"; }
warn() { echo -e "${YELLOW}[demo]${NC} $1"; }
err()  { echo -e "${RED}[demo]${NC} $1"; }
step() { echo -e "\n${CYAN}=== $1 ===${NC}\n"; }

if [[ "${1:-}" == "--clean" ]]; then
    step "Tearing down containers"
    podman-compose -f dev.yml down -v
    log "Done. All containers and volumes removed."
    exit 0
fi

if [[ "${1:-}" != "--quick" ]]; then
    step "Step 1: Starting containers"
    log "Building and starting all services (DB, Kafka, Tempo, Grafana, HBI)..."
    podman-compose -f dev.yml up -d --build

    step "Step 2: Waiting for services to be healthy"
    log "Waiting for hbi-web to be ready..."
    for i in $(seq 1 60); do
        if curl -s -o /dev/null -w "%{http_code}" "$API_URL/hosts" -H "x-rh-identity: $IDENTITY" 2>/dev/null | grep -q "200"; then
            log "hbi-web is ready!"
            break
        fi
        if [ "$i" -eq 60 ]; then
            err "hbi-web did not become ready in 60 seconds."
            err "Check logs: podman-compose -f dev.yml logs hbi-web"
            exit 1
        fi
        sleep 2
        printf "."
    done
    echo ""

    step "Step 3: Running database migrations"
    podman exec hbi-web bash -c "FLASK_APP=manage.py flask db upgrade"
    log "Migrations complete."
else
    step "Quick mode: skipping build and migrations"
fi

step "Step 4: Ingesting $NUM_HOSTS hosts via Kafka"
log "Producing $NUM_HOSTS host messages..."
NUM_HOSTS=$NUM_HOSTS podman exec hbi-mq bash -c "NUM_HOSTS=$NUM_HOSTS python3 utils/kafka_producer.py"
log "Messages sent. Waiting 15s for MQ service to process them..."
sleep 15
log "Ingestion complete. These will show as mq.batch traces in Tempo."

step "Step 5: Making API requests (these generate Flask + SQL traces)"

log "Request 1: GET /hosts (list all hosts)"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/hosts?per_page=50" \
    -H "x-rh-identity: $IDENTITY" \
    -H "x-rh-insights-request-id: demo-list-hosts-001")
log "  -> Status: $STATUS"

log "Request 2: GET /hosts (with system_profile)"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/hosts?per_page=10&fields%5Bsystem_profile%5D=os_release,arch" \
    -H "x-rh-identity: $IDENTITY" \
    -H "x-rh-insights-request-id: demo-system-profile-001")
log "  -> Status: $STATUS"

log "Request 3: GET /hosts (filter by staleness)"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/hosts?per_page=20&staleness=fresh" \
    -H "x-rh-identity: $IDENTITY" \
    -H "x-rh-insights-request-id: demo-staleness-filter-001")
log "  -> Status: $STATUS"

HOSTS_RESPONSE=$(curl -s "$API_URL/hosts?per_page=1" \
    -H "x-rh-identity: $IDENTITY" \
    -H "x-rh-insights-request-id: demo-get-one-host")
HOST_ID=$(echo "$HOSTS_RESPONSE" | python3 -c "import sys, json; r=json.load(sys.stdin); print(r['results'][0]['id'] if r.get('results') else '')" 2>/dev/null || echo "")

if [[ -n "$HOST_ID" ]]; then
    log "Request 4: GET /hosts/$HOST_ID (single host detail)"
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/hosts/$HOST_ID" \
        -H "x-rh-identity: $IDENTITY" \
        -H "x-rh-insights-request-id: demo-single-host-001")
    log "  -> Status: $STATUS"

    log "Request 5: GET /hosts/$HOST_ID/system_profile (system profile)"
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/hosts/$HOST_ID/system_profile" \
        -H "x-rh-identity: $IDENTITY" \
        -H "x-rh-insights-request-id: demo-host-sysprofile-001")
    log "  -> Status: $STATUS"
fi

log "Request 6: GET /groups (list groups)"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/groups" \
    -H "x-rh-identity: $IDENTITY" \
    -H "x-rh-insights-request-id: demo-list-groups-001")
log "  -> Status: $STATUS"

log "Request 7: GET /hosts (large page for heavier trace)"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/hosts?per_page=100" \
    -H "x-rh-identity: $IDENTITY" \
    -H "x-rh-insights-request-id: demo-large-page-001")
log "  -> Status: $STATUS"

step "Done! Ready for the demo."

echo ""
log "Open Grafana:  ${CYAN}http://localhost:3000${NC}"
log "Navigate to:   Explore -> Select 'Tempo' datasource"
log ""
log "Things to show in the demo:"
log "  1. Search by Service Name: ${CYAN}host-inventory${NC}"
log "  2. Find the mq.batch trace (Kafka ingestion of $NUM_HOSTS hosts)"
log "  3. Find a GET /hosts trace and expand the SQL spans"
log "  4. Click on a SQL span to see the query text and duration"
log "  5. Filter by attribute: ${CYAN}hbi.org_id = $ORG_ID${NC}"
log "  6. Filter by attribute: ${CYAN}hbi.request_id = demo-list-hosts-001${NC}"
log "  7. Compare the per_page=50 vs per_page=100 traces"
log ""
log "Tip: Sort traces by duration to find the slowest request."
