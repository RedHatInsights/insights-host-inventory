#!/bin/bash
# Deploy HBI to Ephemeral and Run Unit Tests
# This script orchestrates the complete deployment and testing workflow by
# calling existing modular scripts instead of duplicating logic.
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
            echo "This script orchestrates:"
            echo "  1. Check existing deployment health"
            echo "  2. /hbi-deploy (if needed) - Deploy HBI to ephemeral"
            echo "  3. /hbi-setup-for-dev      - Setup port forwards and .env"
            echo "  4. /hbi-verify-setup       - Verify deployment health"
            echo "  5. /hbi-enable-flags       - Enable Kessel feature flags"
            echo "  6. pytest tests/           - Run full test suite"
            echo ""
            echo "Smart deployment: If a healthy deployment exists, skips deployment"
            echo "and proceeds directly to testing (saves ~7 minutes)."
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

# Setup logging to file
LOG_DIR="$PROJECT_ROOT/tmp/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/hbi-deploy-test-$(date +%Y%m%d-%H%M%S).log"

# Redirect all output to both terminal and log file
exec > >(tee "$LOG_FILE") 2>&1

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  HBI Deploy and Unit Test${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${INFO_MARK} Log file: ${BLUE}$LOG_FILE${NC}"
echo ""

# Step 1: Check if environment already exists and is healthy
echo -e "${BLUE}Step 1: Checking for existing deployment${NC}"
echo ""

SKIP_DEPLOYMENT=false
NAMESPACE=$(bonfire namespace list 2>/dev/null | grep $(whoami) | awk '{print $1}' | head -1)

if [ -n "$NAMESPACE" ]; then
    echo -e "${INFO_MARK} Found existing namespace: ${BLUE}$NAMESPACE${NC}"
    echo -e "${INFO_MARK} Verifying deployment health..."
    echo ""

    # Run verification to check if environment is healthy
    if "$SCRIPT_DIR/verify-ephemeral-setup.sh" 2>/dev/null; then
        echo ""
        echo -e "${CHECK_MARK} ${GREEN}Existing deployment is healthy${NC}"
        echo -e "${INFO_MARK} Skipping deployment, will use existing environment"
        SKIP_DEPLOYMENT=true
    else
        echo ""
        echo -e "${YELLOW}⚠${NC}  ${YELLOW}Existing deployment is not healthy or verification failed${NC}"
        echo -e "${INFO_MARK} Will deploy fresh environment"
    fi
else
    echo -e "${INFO_MARK} No existing namespace found"
    echo -e "${INFO_MARK} Will deploy fresh environment"
fi
echo ""

# Step 2: Deploy HBI (if needed)
if [ "$SKIP_DEPLOYMENT" = false ]; then
    echo -e "${BLUE}Step 2: Deploying HBI to ephemeral environment${NC}"
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

    # Get namespace from bonfire after deployment
    NAMESPACE=$(bonfire namespace list 2>/dev/null | grep $(whoami) | awk '{print $1}' | head -1)
    if [ -z "$NAMESPACE" ]; then
        echo -e "${CROSS_MARK} ${RED}Could not determine namespace${NC}"
        exit 1
    fi
    echo -e "${INFO_MARK} Using namespace: ${BLUE}$NAMESPACE${NC}"
    echo ""
else
    echo -e "${BLUE}Step 2: Skipping deployment (using existing environment)${NC}"
    echo -e "${INFO_MARK} Namespace: ${BLUE}$NAMESPACE${NC}"
    echo ""
fi

# Step 3: Setup local development environment (port forwards, .env)
echo -e "${BLUE}Step 3: Setting up local development environment${NC}"
echo ""

if "$SCRIPT_DIR/../deployer/setup-for-dev.sh" --namespace "$NAMESPACE"; then
    echo ""
    echo -e "${CHECK_MARK} ${GREEN}Local setup successful${NC}"
else
    echo ""
    echo -e "${CROSS_MARK} ${RED}Local setup failed${NC}"
    exit 1
fi
echo ""

# Step 4: Verify deployment (final check before tests)
if [ "$SKIP_DEPLOYMENT" = false ]; then
    echo -e "${BLUE}Step 4: Verifying deployment${NC}"
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
else
    echo -e "${BLUE}Step 4: Skipping verification (already verified)${NC}"
    echo ""
fi

# Step 5: Enable feature flags
echo -e "${BLUE}Step 5: Enabling Kessel feature flags${NC}"
echo ""

if "$SCRIPT_DIR/enable-feature-flags.sh"; then
    echo ""
    echo -e "${CHECK_MARK} ${GREEN}Feature flags enabled${NC}"
else
    echo ""
    echo -e "${CROSS_MARK} ${RED}Failed to enable feature flags${NC}"
    exit 1
fi
echo ""

# Step 6: Run unit tests
echo -e "${BLUE}Step 6: Running unit tests${NC}"
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
echo -e "Log File:       ${BLUE}$LOG_FILE${NC}"
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
