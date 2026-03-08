#!/bin/bash
# Cleanup HBI Ephemeral Environment
# This script stops port forwards and releases the ephemeral namespace
#
# Usage:
#   ./cleanup-ephemeral.sh [NAMESPACE]
#
# Arguments:
#   NAMESPACE - Ephemeral namespace to cleanup (optional, auto-detected if not provided)
#
# Examples:
#   ./cleanup-ephemeral.sh
#   ./cleanup-ephemeral.sh ephemeral-abc123

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
WARNING_MARK="⚠️"

# Parse arguments
NAMESPACE=""
FORCE=false

for arg in "$@"; do
    case $arg in
        --force|-f)
            FORCE=true
            shift
            ;;
        *)
            NAMESPACE="$arg"
            shift
            ;;
    esac
done

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  HBI Ephemeral Environment Cleanup${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Auto-detect namespace if not provided
if [ -z "$NAMESPACE" ]; then
    echo -e "${INFO_MARK} ${BLUE}No namespace provided, auto-detecting...${NC}"
    NAMESPACE=$(bonfire namespace list 2>/dev/null | grep $(whoami) | awk '{print $1}' | head -1)

    if [ -z "$NAMESPACE" ]; then
        echo -e "${WARNING_MARK} ${YELLOW}No ephemeral namespace found to cleanup${NC}"
        echo -e "${INFO_MARK} You may not have any active namespaces."
        echo ""
        echo "To check manually:"
        echo "  bonfire namespace list"
        exit 0
    fi

    echo -e "${INFO_MARK} Auto-detected namespace: ${BLUE}$NAMESPACE${NC}"
fi

# Verify namespace exists
echo ""
echo -e "${BLUE}Verifying namespace...${NC}"
if ! bonfire namespace list 2>/dev/null | grep -q "$NAMESPACE"; then
    echo -e "${CROSS_MARK} ${RED}Namespace '$NAMESPACE' not found or not owned by you${NC}"
    exit 1
fi
echo -e "${CHECK_MARK} ${GREEN}Namespace verified${NC}"

# Step 1: Stop port forwards
echo ""
echo -e "${BLUE}1. Stopping port forwards...${NC}"
PORT_FORWARDS=$(ps aux | grep "kubectl port-forward" | grep -v grep | wc -l | tr -d ' ')

if [ "$PORT_FORWARDS" -gt 0 ]; then
    echo -e "${INFO_MARK} Found $PORT_FORWARDS port forward(s) running"
    ps aux | grep "kubectl port-forward" | grep -v grep | awk '{print $2}' | xargs kill 2>/dev/null || true
    sleep 1

    # Verify stopped
    REMAINING=$(ps aux | grep "kubectl port-forward" | grep -v grep | wc -l | tr -d ' ')
    if [ "$REMAINING" -eq 0 ]; then
        echo -e "${CHECK_MARK} ${GREEN}All port forwards stopped${NC}"
    else
        echo -e "${WARNING_MARK} ${YELLOW}Some port forwards may still be running${NC}"
    fi
else
    echo -e "${CHECK_MARK} ${GREEN}No port forwards to stop${NC}"
fi

# Step 2: Release namespace
echo ""
echo -e "${BLUE}2. Releasing namespace: $NAMESPACE${NC}"
echo -e "${WARNING_MARK} ${YELLOW}This will permanently delete:${NC}"
echo "   • All pods and containers"
echo "   • All databases and data"
echo "   • All services and deployments"
echo "   • The entire namespace: $NAMESPACE"
echo ""

# Ask for confirmation unless --force is used
if [ "$FORCE" = false ]; then
    read -p "Are you sure you want to delete this namespace? (yes/no): " CONFIRM
    echo ""

    if [ "$CONFIRM" != "yes" ] && [ "$CONFIRM" != "y" ]; then
        echo -e "${INFO_MARK} ${BLUE}Cleanup cancelled by user${NC}"
        echo ""
        echo "To cleanup anyway, run:"
        echo "  $0 $NAMESPACE --force"
        exit 0
    fi

    echo -e "${INFO_MARK} Proceeding with deletion..."
fi

if bonfire namespace release "$NAMESPACE" --force 2>&1 | tee /tmp/bonfire-release.log; then
    echo -e "${CHECK_MARK} ${GREEN}Namespace released successfully${NC}"
else
    echo -e "${CROSS_MARK} ${RED}Failed to release namespace${NC}"
    cat /tmp/bonfire-release.log
    exit 1
fi

# Step 3: Clean up temporary files
echo ""
echo -e "${BLUE}3. Cleaning up temporary files...${NC}"

# Remove Unleash session cookies
rm -f /tmp/unleash-cookies*.txt 2>/dev/null && echo -e "${CHECK_MARK} Removed Unleash session files" || true

# Note: We don't remove ephemeral logs/credentials as they may be useful for debugging
echo -e "${INFO_MARK} Keeping ephemeral logs in tmp/ directory for reference"

# Step 4: Verify cleanup
echo ""
echo -e "${BLUE}4. Verifying cleanup...${NC}"

# Check port forwards
PORT_CHECK=$(ps aux | grep "kubectl port-forward" | grep -v grep | wc -l | tr -d ' ')
if [ "$PORT_CHECK" -eq 0 ]; then
    echo -e "${CHECK_MARK} ${GREEN}No port forwards running${NC}"
else
    echo -e "${WARNING_MARK} ${YELLOW}$PORT_CHECK port forward(s) still running${NC}"
fi

# Check namespaces
NS_CHECK=$(bonfire namespace list 2>/dev/null | grep $(whoami) | wc -l | tr -d ' ')
if [ "$NS_CHECK" -eq 0 ]; then
    echo -e "${CHECK_MARK} ${GREEN}No namespaces reserved${NC}"
else
    echo -e "${INFO_MARK} ${BLUE}You have $NS_CHECK other namespace(s) reserved${NC}"
    bonfire namespace list 2>/dev/null | grep $(whoami)
fi

# Summary
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${CHECK_MARK} ${GREEN}Cleanup Complete!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${INFO_MARK} Namespace ${BLUE}$NAMESPACE${NC} has been deleted"
echo -e "${INFO_MARK} All resources and data have been removed"
echo ""
echo "To deploy a new environment:"
echo "  /hbi-deploy"
echo ""

exit 0
