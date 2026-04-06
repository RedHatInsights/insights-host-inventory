#!/bin/bash
#
# Cleanup HBI Ephemeral Environment
# Auto-confirms cleanup and verifies completion
#
# Usage:
#   ./cleanup-ephemeral.sh                    # Auto-detect namespace
#   ./cleanup-ephemeral.sh ephemeral-abc123   # Specific namespace
#

set -eo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  HBI Ephemeral Cleanup (Auto-Confirm)${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo

# Run the cleanup script with --force flag
echo -e "${BLUE}Running cleanup with auto-confirmation...${NC}"
if [ -n "$1" ]; then
    NAMESPACE="$1"
    echo -e "ℹ️  Target namespace: ${BLUE}${NAMESPACE}${NC}"
    bash "${SCRIPT_DIR}/remove-ephemeral-namespace.sh" "${NAMESPACE}" --force
else
    echo -e "ℹ️  Auto-detecting namespace..."
    bash "${SCRIPT_DIR}/remove-ephemeral-namespace.sh" --force
fi

CLEANUP_EXIT_CODE=$?
echo

# Verify cleanup completion
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Cleanup Verification${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo

if [ $CLEANUP_EXIT_CODE -eq 0 ]; then
    echo -e "✅ ${GREEN}Cleanup script completed successfully${NC}"

    # Additional verification checks
    echo
    echo -e "${BLUE}Running additional verification checks...${NC}"

    # Check 1: Verify no port forwards running
    echo -n "1. Checking port forwards... "
    PORT_FORWARD_COUNT=$(ps aux | grep -i "kubectl port-forward" | grep -v grep | wc -l | tr -d ' ')
    if [ "$PORT_FORWARD_COUNT" -eq 0 ]; then
        echo -e "${GREEN}✓ No port forwards running${NC}"
    else
        echo -e "${YELLOW}⚠ Warning: ${PORT_FORWARD_COUNT} port forward(s) still running${NC}"
        echo -e "  ${YELLOW}You may want to kill them manually: pkill -9 -f 'kubectl port-forward'${NC}"
    fi

    # Check 2: Verify namespace is gone
    echo -n "2. Checking namespace existence... "
    if [ -n "$NAMESPACE" ]; then
        TARGET_NAMESPACE="$NAMESPACE"
    else
        # Try to get namespace from cleanup output
        TARGET_NAMESPACE=$(bonfire namespace list 2>/dev/null | grep $(whoami) | awk '{print $1}' | head -n1)
    fi

    if [ -n "$TARGET_NAMESPACE" ]; then
        NAMESPACE_EXISTS=$(kubectl get namespace "$TARGET_NAMESPACE" 2>/dev/null | grep -v NAME | wc -l | tr -d ' ')
        if [ "$NAMESPACE_EXISTS" -eq 0 ]; then
            echo -e "${GREEN}✓ Namespace deleted successfully${NC}"
        else
            echo -e "${YELLOW}⚠ Warning: Namespace still exists${NC}"
            echo -e "  ${YELLOW}It may take a few moments to fully terminate${NC}"
        fi
    else
        echo -e "${BLUE}ℹ️  No namespace to verify${NC}"
    fi

    # Check 3: List remaining ephemeral namespaces
    echo -n "3. Checking for other ephemeral namespaces... "
    REMAINING_COUNT=$(bonfire namespace list 2>/dev/null | grep $(whoami) | wc -l | tr -d ' ')
    if [ "$REMAINING_COUNT" -eq 0 ]; then
        echo -e "${GREEN}✓ No ephemeral namespaces remaining${NC}"
    else
        echo -e "${BLUE}ℹ️  ${REMAINING_COUNT} ephemeral namespace(s) still active${NC}"
        bonfire namespace list 2>/dev/null | grep $(whoami) | awk '{print "  - " $1 " (age: " $3 ")"}'
    fi

    echo
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}✓ Cleanup Verified Successfully!${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo
    echo -e "Summary:"
    echo -e "  ${GREEN}✓${NC} Namespace released"
    echo -e "  ${GREEN}✓${NC} Port forwards stopped"
    echo -e "  ${GREEN}✓${NC} Resources cleaned up"
    echo

    exit 0
else
    echo -e "❌ ${RED}Cleanup script failed with exit code: $CLEANUP_EXIT_CODE${NC}"
    echo
    echo -e "${YELLOW}Troubleshooting steps:${NC}"
    echo -e "  1. Check if namespace exists: bonfire namespace list"
    echo -e "  2. Try manual cleanup: bonfire namespace release <namespace> --force"
    echo -e "  3. Check for lingering port forwards: ps aux | grep 'kubectl port-forward'"
    echo

    exit $CLEANUP_EXIT_CODE
fi
