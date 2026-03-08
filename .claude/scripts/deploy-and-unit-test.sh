#!/bin/bash
# Deploy HBI to Ephemeral and Run Unit Tests
# This script automates the full deployment and testing workflow
#
# Usage:
#   ./deploy-and-unit-test.sh [--duration DURATION] [--force]
#
# Options:
#   --duration DURATION - Namespace reservation duration (default: 335h)
#   --force            - Use existing namespace without prompting
#
# Examples:
#   ./deploy-and-unit-test.sh
#   ./deploy-and-unit-test.sh --duration 8h
#   ./deploy-and-unit-test.sh --duration 4h --force

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Symbols
CHECK_MARK="✅"
CROSS_MARK="❌"
INFO_MARK="ℹ️"
TEST_MARK="🧪"

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"

# Default values
DURATION="335h"
FORCE_FLAG=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --duration)
            DURATION="$2"
            shift 2
            ;;
        --force)
            FORCE_FLAG="--force"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [--duration DURATION] [--force]"
            echo ""
            echo "Options:"
            echo "  --duration DURATION  Namespace reservation duration (default: 335h)"
            echo "  --force             Use existing namespace without prompting"
            echo ""
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  HBI Deploy and Unit Test${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Step 1: Deploy HBI
echo -e "${BLUE}Step 1: Deploying HBI to ephemeral environment${NC}"
echo -e "${INFO_MARK} Duration: $DURATION"
if [ -n "$FORCE_FLAG" ]; then
    echo -e "${INFO_MARK} Force mode: Using existing namespace"
fi
echo ""

cd "$PROJECT_ROOT"

if "$SCRIPT_DIR/../deployer/deploy-ephemeral.sh" --duration "$DURATION" $FORCE_FLAG; then
    echo ""
    echo -e "${CHECK_MARK} ${GREEN}Deployment successful${NC}"
else
    echo ""
    echo -e "${CROSS_MARK} ${RED}Deployment failed${NC}"
    exit 1
fi

# Get namespace from bonfire
NAMESPACE=$(bonfire namespace list 2>/dev/null | grep $(whoami) | awk '{print $1}' | head -1)
if [ -z "$NAMESPACE" ]; then
    echo -e "${CROSS_MARK} ${RED}Could not determine namespace${NC}"
    exit 1
fi
echo -e "${INFO_MARK} Using namespace: ${BLUE}$NAMESPACE${NC}"
echo ""

# Step 2: Verify deployment
echo -e "${BLUE}Step 2: Verifying deployment${NC}"
echo ""

if "$SCRIPT_DIR/verify-ephemeral-setup.sh"; then
    echo ""
    echo -e "${CHECK_MARK} ${GREEN}Verification successful${NC}"
else
    echo ""
    echo -e "${CROSS_MARK} ${RED}Verification failed${NC}"
    exit 1
fi
echo ""

# Step 3: Enable feature flags
echo -e "${BLUE}Step 3: Enabling Kessel feature flags${NC}"
echo ""

# Login to Unleash
echo -e "${INFO_MARK} Logging into Unleash..."
LOGIN_RESULT=$(curl -s -X POST http://localhost:4242/auth/simple/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "unleash4all"}' \
  -c /tmp/unleash-cookies-test.txt 2>/dev/null)

if ! echo "$LOGIN_RESULT" | grep -q "username"; then
    echo -e "${CROSS_MARK} ${RED}Failed to login to Unleash${NC}"
    exit 1
fi
echo -e "${CHECK_MARK} ${GREEN}Logged into Unleash${NC}"

# Feature flags to enable
FLAGS=(
    "hbi.api.kessel-phase-1"
    "hbi.api.kessel-groups"
    "hbi.api.kessel-force-single-checks-for-bulk"
)

# Create and enable flags
for flag in "${FLAGS[@]}"; do
    echo -e "${INFO_MARK} Configuring: $flag"

    # Create flag (ignore if already exists)
    curl -s -X POST http://localhost:4242/api/admin/projects/default/features \
        -b /tmp/unleash-cookies-test.txt \
        -H "Content-Type: application/json" \
        -d "{
            \"name\": \"$flag\",
            \"description\": \"Enable $flag feature\",
            \"type\": \"release\",
            \"impressionData\": false
        }" >/dev/null 2>&1 || true

    # Enable in development
    curl -s -X POST "http://localhost:4242/api/admin/projects/default/features/$flag/environments/development/on" \
        -b /tmp/unleash-cookies-test.txt \
        -H "Content-Type: application/json" >/dev/null 2>&1

    # Enable in production
    curl -s -X POST "http://localhost:4242/api/admin/projects/default/features/$flag/environments/production/on" \
        -b /tmp/unleash-cookies-test.txt \
        -H "Content-Type: application/json" >/dev/null 2>&1

    echo -e "   ${CHECK_MARK} Enabled: $flag"
done

# Cleanup
rm -f /tmp/unleash-cookies-test.txt

echo ""
echo -e "${CHECK_MARK} ${GREEN}All feature flags enabled${NC}"
echo ""

# Step 4: Run unit tests
echo -e "${BLUE}Step 4: Running unit tests${NC}"
echo ""

cd "$PROJECT_ROOT"

# Unset PIPENV_PIPFILE to use main Pipfile
unset PIPENV_PIPFILE

echo -e "${TEST_MARK} Running: pipenv run pytest tests/"
echo ""

if pipenv run pytest tests/; then
    TEST_RESULT="PASSED"
    TEST_COLOR="${GREEN}"
    TEST_SYMBOL="${CHECK_MARK}"
    EXIT_CODE=0
else
    TEST_RESULT="FAILED"
    TEST_COLOR="${RED}"
    TEST_SYMBOL="${CROSS_MARK}"
    EXIT_CODE=1
fi

# Summary
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Test Summary${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "Namespace:      ${BLUE}$NAMESPACE${NC}"
echo -e "Duration:       ${BLUE}$DURATION${NC}"
echo -e "Test Result:    ${TEST_SYMBOL} ${TEST_COLOR}${TEST_RESULT}${NC}"
echo ""

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${CHECK_MARK} ${GREEN}All tests passed!${NC}"
    echo ""
    echo "To cleanup the environment:"
    echo "  .claude/scripts/remove-ephemeral-namespace.sh $NAMESPACE"
    echo ""
else
    echo -e "${CROSS_MARK} ${RED}Tests failed${NC}"
    echo ""
    echo "To investigate:"
    echo "  kubectl get pods -n $NAMESPACE"
    echo "  kubectl logs -n $NAMESPACE deployment/host-inventory-service"
    echo ""
    echo "To cleanup:"
    echo "  .claude/scripts/remove-ephemeral-namespace.sh $NAMESPACE --force"
    echo ""
fi

exit $EXIT_CODE
