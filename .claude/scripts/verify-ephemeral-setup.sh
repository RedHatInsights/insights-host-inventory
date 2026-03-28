#!/bin/bash
# Verify HBI Ephemeral Environment Setup
# This script checks that an ephemeral deployment is properly configured

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
INFO_MARK="📊"
LINK_MARK="🔗"
SUMMARY_MARK="📝"

# Error tracking
ERRORS=0

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  HBI Ephemeral Environment Verification${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# 1. Check Namespace
echo -e "${YELLOW}1. Checking Ephemeral Namespace...${NC}"
NAMESPACE=$(bonfire namespace list 2>/dev/null | grep $(whoami) | awk '{print $1}' || echo "")
if [ -z "$NAMESPACE" ]; then
    echo -e "${CROSS_MARK} ${RED}No ephemeral namespace found${NC}"
    ERRORS=$((ERRORS + 1))
else
    echo -e "${CHECK_MARK} ${GREEN}Namespace: $NAMESPACE${NC}"

    # Get namespace details
    NAMESPACE_INFO=$(bonfire namespace list 2>/dev/null | grep "$NAMESPACE")
    echo "   Status: $(echo $NAMESPACE_INFO | awk '{print $3}')"
    echo "   Pods: $(echo $NAMESPACE_INFO | awk '{print $4}')"
    echo "   Age: $(echo $NAMESPACE_INFO | awk '{print $8}')"
fi
echo ""

# 2. Verify Pods
echo -e "${YELLOW}2. Verifying Pod Status...${NC}"
if [ -n "$NAMESPACE" ]; then
    POD_COUNT=$(kubectl get pods -n $NAMESPACE 2>/dev/null | grep -c "Running" || echo "0")
    TOTAL_PODS=$(kubectl get pods -n $NAMESPACE 2>/dev/null | tail -n +2 | wc -l | tr -d ' ')

    if [ "$POD_COUNT" -gt 0 ]; then
        echo -e "${CHECK_MARK} ${GREEN}$POD_COUNT running pods (out of $TOTAL_PODS total)${NC}"

        # Check key services
        echo "   Key services:"
        kubectl get pods -n $NAMESPACE 2>/dev/null | grep -E "(host-inventory-service|kessel-inventory-api|kessel-relations-api|rbac-service)" | awk '{printf "   - %s: %s\n", $1, $3}' || true
    else
        echo -e "${CROSS_MARK} ${RED}No running pods found${NC}"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo -e "${CROSS_MARK} ${RED}Skipped (no namespace)${NC}"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# 3. Check Port Forwards
echo -e "${YELLOW}3. Checking Port Forwards...${NC}"
PORT_FORWARDS=$(ps aux | grep "kubectl port-forward" | grep -v grep | wc -l | tr -d ' ')
if [ "$PORT_FORWARDS" -gt 0 ]; then
    echo -e "${CHECK_MARK} ${GREEN}$PORT_FORWARDS port forwards active${NC}"
    echo -e "${LINK_MARK} Active ports:"
    ps aux | grep "kubectl port-forward" | grep -v grep | awk '{
        for(i=11; i<=NF; i++) {
            if($i ~ /^[0-9]+:[0-9]+$/) {
                split($i, ports, ":");
                printf "   - localhost:%s\n", ports[1];
            }
        }
    }' | sort -u
else
    echo -e "${CROSS_MARK} ${RED}No port forwards running${NC}"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# 4. Test API Health
echo -e "${YELLOW}4. Testing API Health...${NC}"

# HBI API
HBI_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null || echo "000")
if [ "$HBI_HEALTH" = "200" ]; then
    echo -e "${CHECK_MARK} ${GREEN}HBI API: Healthy (HTTP $HBI_HEALTH)${NC}"
else
    echo -e "${CROSS_MARK} ${RED}HBI API: Not responding (HTTP $HBI_HEALTH)${NC}"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# 5. Verify Database Connectivity
echo -e "${YELLOW}5. Verifying Database Connectivity...${NC}"

# Check .env file
if [ ! -f ".env" ]; then
    echo -e "${CROSS_MARK} ${RED}.env file not found${NC}"
    ERRORS=$((ERRORS + 1))
else
    # Get credentials from .env
    HBI_USER=$(grep "^INVENTORY_DB_USER=" .env | cut -d= -f2)
    HBI_PASS=$(grep "^INVENTORY_DB_PASS=" .env | cut -d= -f2)
    HBI_NAME=$(grep "^INVENTORY_DB_NAME=" .env | cut -d= -f2)

    # Get credentials from log file
    CRED_FILE=$(ls -t tmp/ephemeral_db_credentials_*.log 2>/dev/null | head -1)
    if [ -n "$CRED_FILE" ]; then
        RBAC_USER=$(grep "^RBAC_USER:" "$CRED_FILE" | awk '{print $2}')
        RBAC_PASS=$(grep "^RBAC_PASSWORD:" "$CRED_FILE" | awk '{print $2}')
        KESSEL_USER=$(grep "^KESSEL_USER:" "$CRED_FILE" | awk '{print $2}')
        KESSEL_PASS=$(grep "^KESSEL_PASSWORD:" "$CRED_FILE" | awk '{print $2}')
    fi

    # Test HBI Database
    if [ -n "$HBI_USER" ] && [ -n "$HBI_PASS" ]; then
        HOST_COUNT=$(PGPASSWORD="$HBI_PASS" psql -h localhost -p 5432 -U "$HBI_USER" -d "$HBI_NAME" -t -c "SELECT COUNT(*) FROM hbi.hosts;" 2>/dev/null | tr -d ' ' || echo "ERROR")
        if [ "$HOST_COUNT" != "ERROR" ]; then
            echo -e "${CHECK_MARK} ${GREEN}HBI Database: Connected${NC}"
            echo -e "${INFO_MARK}   Hosts: $HOST_COUNT"
        else
            echo -e "${CROSS_MARK} ${RED}HBI Database: Connection failed${NC}"
            ERRORS=$((ERRORS + 1))
        fi
    else
        echo -e "${CROSS_MARK} ${RED}HBI Database: Credentials not found in .env${NC}"
        ERRORS=$((ERRORS + 1))
    fi

    # Test RBAC Database
    if [ -n "$RBAC_USER" ] && [ -n "$RBAC_PASS" ]; then
        WORKSPACE_COUNT=$(PGPASSWORD="$RBAC_PASS" psql -h localhost -p 5433 -U "$RBAC_USER" -d rbac -t -c "SELECT COUNT(*) FROM management_workspace;" 2>/dev/null | tr -d ' ' || echo "ERROR")
        if [ "$WORKSPACE_COUNT" != "ERROR" ]; then
            echo -e "${CHECK_MARK} ${GREEN}RBAC Database: Connected${NC}"
            echo -e "${INFO_MARK}   Workspaces: $WORKSPACE_COUNT"
        else
            echo -e "${CROSS_MARK} ${RED}RBAC Database: Connection failed${NC}"
            ERRORS=$((ERRORS + 1))
        fi
    else
        echo -e "${CROSS_MARK} ${RED}RBAC Database: Credentials not found${NC}"
        ERRORS=$((ERRORS + 1))
    fi

    # Test Kessel Database
    if [ -n "$KESSEL_USER" ] && [ -n "$KESSEL_PASS" ]; then
        RESOURCE_COUNT=$(PGPASSWORD="$KESSEL_PASS" psql -h localhost -p 5434 -U "$KESSEL_USER" -d kessel-inventory -t -c "SELECT COUNT(*) FROM resource;" 2>/dev/null | tr -d ' ' || echo "ERROR")
        if [ "$RESOURCE_COUNT" != "ERROR" ]; then
            echo -e "${CHECK_MARK} ${GREEN}Kessel Database: Connected${NC}"
            echo -e "${INFO_MARK}   Resources: $RESOURCE_COUNT"
        else
            echo -e "${CROSS_MARK} ${RED}Kessel Database: Connection failed${NC}"
            ERRORS=$((ERRORS + 1))
        fi
    else
        echo -e "${CROSS_MARK} ${RED}Kessel Database: Credentials not found${NC}"
        ERRORS=$((ERRORS + 1))
    fi
fi
echo ""

# 6. Check Configuration Files
echo -e "${YELLOW}6. Checking Configuration Files...${NC}"

# Check .env
if [ -f ".env" ]; then
    echo -e "${CHECK_MARK} ${GREEN}.env file exists${NC}"
    DB_CREDS=$(grep -c "^INVENTORY_DB_" .env || echo "0")
    echo "   Database credentials: $DB_CREDS entries"
else
    echo -e "${CROSS_MARK} ${RED}.env file not found${NC}"
    ERRORS=$((ERRORS + 1))
fi

# Check credential log
CRED_LOG=$(ls -t tmp/ephemeral_db_credentials_*.log 2>/dev/null | head -1)
if [ -n "$CRED_LOG" ]; then
    echo -e "${CHECK_MARK} ${GREEN}Credential log exists: $(basename $CRED_LOG)${NC}"
else
    echo -e "${CROSS_MARK} ${RED}No credential log found${NC}"
    ERRORS=$((ERRORS + 1))
fi

# Check port forward log
PORT_LOG=$(ls -t tmp/ephemeral_ports_*.log 2>/dev/null | head -1)
if [ -n "$PORT_LOG" ]; then
    echo -e "${CHECK_MARK} ${GREEN}Port forward log exists: $(basename $PORT_LOG)${NC}"
else
    echo -e "${CROSS_MARK} ${RED}No port forward log found${NC}"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# 7. Check Feature Flags
echo -e "${YELLOW}7. Checking Feature Flags...${NC}"

# Login to Unleash
LOGIN_RESULT=$(curl -s -X POST http://localhost:4242/auth/simple/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "unleash4all"}' \
  -c /tmp/unleash-cookies-verify.txt 2>/dev/null)

if [ $? -eq 0 ] && echo "$LOGIN_RESULT" | grep -q "username"; then
    echo -e "${CHECK_MARK} ${GREEN}Connected to Unleash${NC}"

    # Check HBI Kessel feature flags
    FLAGS=("hbi.api.kessel-phase-1" "hbi.api.kessel-groups" "hbi.api.kessel-force-single-checks-for-bulk")

    for flag in "${FLAGS[@]}"; do
        FLAG_STATUS=$(curl -s "http://localhost:4242/api/admin/projects/default/features/$flag" \
          -b /tmp/unleash-cookies-verify.txt 2>/dev/null)

        if [ $? -eq 0 ] && echo "$FLAG_STATUS" | grep -q "environments"; then
            DEV_ENABLED=$(echo "$FLAG_STATUS" | jq -r '.environments[] | select(.name=="development") | .enabled' 2>/dev/null)
            PROD_ENABLED=$(echo "$FLAG_STATUS" | jq -r '.environments[] | select(.name=="production") | .enabled' 2>/dev/null)

            if [ "$DEV_ENABLED" = "true" ] && [ "$PROD_ENABLED" = "true" ]; then
                echo -e "   ${CHECK_MARK} ${GREEN}$flag: enabled${NC}"
            elif [ "$DEV_ENABLED" = "true" ] || [ "$PROD_ENABLED" = "true" ]; then
                echo -e "   ${YELLOW}⚠️  $flag: partially enabled (dev: $DEV_ENABLED, prod: $PROD_ENABLED)${NC}"
            else
                echo -e "   ${CROSS_MARK} ${RED}$flag: disabled${NC}"
            fi
        else
            echo -e "   ${CROSS_MARK} ${RED}$flag: not found${NC}"
        fi
    done

    # Cleanup
    rm -f /tmp/unleash-cookies-verify.txt
else
    echo -e "${CROSS_MARK} ${RED}Unable to connect to Unleash${NC}"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# 8. Summary
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${SUMMARY_MARK} ${BLUE}Verification Summary${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"

if [ $ERRORS -eq 0 ]; then
    echo -e "${CHECK_MARK} ${GREEN}All checks passed!${NC}"
    echo -e "${GREEN}Your ephemeral environment is fully functional.${NC}"
    exit 0
else
    echo -e "${CROSS_MARK} ${RED}$ERRORS check(s) failed${NC}"
    echo -e "${RED}Some components may not be working properly.${NC}"
    echo ""
    echo -e "${YELLOW}Troubleshooting tips:${NC}"
    echo "  - Ensure /hbi-deploy completed successfully"
    echo "  - Check that port forwards are running"
    echo "  - Verify .env file has correct credentials"
    echo "  - Run: kubectl get pods -n $NAMESPACE"
    exit 1
fi
