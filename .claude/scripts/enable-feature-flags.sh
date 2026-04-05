#!/bin/bash

#############################################################################
# Enable HBI Feature Flags in Unleash
#############################################################################
# This script enables Kessel-related feature flags in Unleash.
# Assumes port-forwarding is already set up to Unleash (localhost:4242)
#############################################################################

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Symbols
CHECK_MARK="✅"
CROSS_MARK="❌"
INFO_MARK="ℹ️"

# Log functions
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] ✓${NC} $1"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ✗${NC} $1"
}

log_info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] ${INFO_MARK}${NC} $1"
}

# Default values
UNLEASH_URL="${UNLEASH_URL:-http://localhost:4242}"
UNLEASH_USER="${UNLEASH_USER:-admin}"
UNLEASH_PASS="${UNLEASH_PASS:-unleash4all}"
COOKIE_FILE="/tmp/unleash-cookies-enable-flags.txt"

# Default feature flags to enable
DEFAULT_FLAGS=(
    "hbi.api.kessel-phase-1"
    "hbi.api.kessel-groups"
    "hbi.api.kessel-force-single-checks-for-bulk"
)

# Function to check if Unleash is accessible
check_unleash_available() {
    log "Checking Unleash availability at $UNLEASH_URL..."

    if ! curl -s --connect-timeout 5 "$UNLEASH_URL/health" >/dev/null 2>&1; then
        log_error "Unleash is not accessible at $UNLEASH_URL"
        log_error "Please ensure:"
        log_error "  1. Port forwarding is set up: kubectl port-forward svc/env-<namespace>-featureflags 4242:4242"
        log_error "  2. Unleash pod is running: kubectl get pods | grep featureflags"
        log_error "  3. You can run /hbi-setup-for-dev to set up port forwarding"
        exit 1
    fi

    log_success "Unleash is accessible"
}

# Function to login to Unleash
login_to_unleash() {
    log "Logging into Unleash as $UNLEASH_USER..."

    local login_result=$(curl -s -X POST "$UNLEASH_URL/auth/simple/login" \
        -H "Content-Type: application/json" \
        -d "{\"username\": \"$UNLEASH_USER\", \"password\": \"$UNLEASH_PASS\"}" \
        -c "$COOKIE_FILE" 2>/dev/null)

    if ! echo "$login_result" | grep -q "username"; then
        log_error "Failed to login to Unleash"
        log_error "Response: $login_result"
        rm -f "$COOKIE_FILE"
        exit 1
    fi

    log_success "Logged into Unleash"
}

# Function to enable a feature flag
enable_feature_flag() {
    local flag_name="$1"
    local environments="${2:-development production}"

    log_info "Processing flag: $flag_name"

    # Create flag if it doesn't exist
    local create_response=$(curl -s -X POST "$UNLEASH_URL/api/admin/projects/default/features" \
        -b "$COOKIE_FILE" \
        -H "Content-Type: application/json" \
        -d "{
            \"name\": \"$flag_name\",
            \"description\": \"Enable $flag_name feature\",
            \"type\": \"release\",
            \"impressionData\": false
        }" 2>/dev/null)

    # Check if creation succeeded or if flag already exists
    if echo "$create_response" | grep -q "already exists"; then
        log_info "  Flag already exists"
    elif echo "$create_response" | grep -q "name"; then
        log_info "  Flag created"
    fi

    # Enable in each environment
    for env in $environments; do
        local enable_response=$(curl -s -X POST "$UNLEASH_URL/api/admin/projects/default/features/$flag_name/environments/$env/on" \
            -b "$COOKIE_FILE" \
            -H "Content-Type: application/json" 2>/dev/null)

        if [ $? -eq 0 ]; then
            echo -e "  ${CHECK_MARK} ${GREEN}Enabled in $env${NC}"
        else
            echo -e "  ${CROSS_MARK} ${RED}Failed to enable in $env${NC}"
        fi
    done
}

# Function to verify feature flags are enabled
verify_feature_flags() {
    log "Verifying feature flags..."

    local all_enabled=true

    for flag in "$@"; do
        local flag_status=$(curl -s "$UNLEASH_URL/api/admin/projects/default/features/$flag" \
            -b "$COOKIE_FILE" 2>/dev/null)

        if echo "$flag_status" | grep -q "environments"; then
            local dev_enabled=$(echo "$flag_status" | jq -r '.environments[] | select(.name=="development") | .enabled' 2>/dev/null)
            local prod_enabled=$(echo "$flag_status" | jq -r '.environments[] | select(.name=="production") | .enabled' 2>/dev/null)

            if [ "$dev_enabled" = "true" ] && [ "$prod_enabled" = "true" ]; then
                echo -e "  ${CHECK_MARK} ${GREEN}$flag: enabled (dev + prod)${NC}"
            else
                echo -e "  ${CROSS_MARK} ${RED}$flag: NOT fully enabled (dev: $dev_enabled, prod: $prod_enabled)${NC}"
                all_enabled=false
            fi
        else
            echo -e "  ${CROSS_MARK} ${RED}$flag: not found${NC}"
            all_enabled=false
        fi
    done

    if [ "$all_enabled" = true ]; then
        log_success "All feature flags verified"
    else
        log_error "Some feature flags are not properly enabled"
        return 1
    fi
}

# Function to list all HBI feature flags
list_feature_flags() {
    log "Listing all HBI feature flags..."

    local all_flags=$(curl -s "$UNLEASH_URL/api/admin/projects/default/features" \
        -b "$COOKIE_FILE" 2>/dev/null)

    echo "$all_flags" | jq -r '.features[] | select(.name | startswith("hbi.")) | .name' 2>/dev/null | while read -r flag; do
        local flag_status=$(curl -s "$UNLEASH_URL/api/admin/projects/default/features/$flag" \
            -b "$COOKIE_FILE" 2>/dev/null)

        local dev_enabled=$(echo "$flag_status" | jq -r '.environments[] | select(.name=="development") | .enabled' 2>/dev/null)
        local prod_enabled=$(echo "$flag_status" | jq -r '.environments[] | select(.name=="production") | .enabled' 2>/dev/null)

        if [ "$dev_enabled" = "true" ] && [ "$prod_enabled" = "true" ]; then
            echo -e "  ${CHECK_MARK} ${GREEN}$flag${NC}"
        else
            echo -e "  ${CROSS_MARK} ${YELLOW}$flag (dev: $dev_enabled, prod: $prod_enabled)${NC}"
        fi
    done
}

# Function to cleanup
cleanup() {
    rm -f "$COOKIE_FILE"
}

trap cleanup EXIT

# Main execution
main() {
    echo ""
    echo "========================================================================"
    echo "  Enable HBI Feature Flags in Unleash"
    echo "========================================================================"
    echo ""

    # Parse arguments
    FLAGS_TO_ENABLE=()
    LIST_ONLY=false
    VERIFY_ONLY=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --list)
                LIST_ONLY=true
                shift
                ;;
            --verify)
                VERIFY_ONLY=true
                shift
                ;;
            --url)
                UNLEASH_URL="$2"
                shift 2
                ;;
            --user)
                UNLEASH_USER="$2"
                shift 2
                ;;
            --password)
                UNLEASH_PASS="$2"
                shift 2
                ;;
            --help)
                echo "Usage: $0 [OPTIONS] [FLAG_NAMES...]"
                echo ""
                echo "Options:"
                echo "  --list              List all HBI feature flags and their status"
                echo "  --verify            Verify feature flags are enabled (don't modify)"
                echo "  --url URL           Unleash URL (default: http://localhost:4242)"
                echo "  --user USER         Unleash username (default: admin)"
                echo "  --password PASS     Unleash password (default: unleash4all)"
                echo "  --help              Show this help message"
                echo ""
                echo "Flag Names:"
                echo "  Specify flag names to enable (default: all Kessel flags)"
                echo ""
                echo "Default flags enabled:"
                for flag in "${DEFAULT_FLAGS[@]}"; do
                    echo "  - $flag"
                done
                echo ""
                echo "Examples:"
                echo "  $0                                    # Enable all default flags"
                echo "  $0 --list                             # List all HBI flags"
                echo "  $0 --verify                           # Verify default flags"
                echo "  $0 hbi.api.kessel-phase-1             # Enable specific flag"
                echo ""
                exit 0
                ;;
            *)
                FLAGS_TO_ENABLE+=("$1")
                shift
                ;;
        esac
    done

    # Use default flags if none specified
    if [ ${#FLAGS_TO_ENABLE[@]} -eq 0 ]; then
        FLAGS_TO_ENABLE=("${DEFAULT_FLAGS[@]}")
    fi

    # Check Unleash availability
    check_unleash_available

    # Login
    login_to_unleash

    # Execute requested action
    if [ "$LIST_ONLY" = true ]; then
        list_feature_flags
    elif [ "$VERIFY_ONLY" = true ]; then
        verify_feature_flags "${FLAGS_TO_ENABLE[@]}"
    else
        # Enable flags
        echo ""
        log "Enabling ${#FLAGS_TO_ENABLE[@]} feature flag(s)..."
        echo ""

        for flag in "${FLAGS_TO_ENABLE[@]}"; do
            enable_feature_flag "$flag" "development production"
        done

        echo ""
        # Verify
        verify_feature_flags "${FLAGS_TO_ENABLE[@]}"
    fi

    echo ""
    echo "========================================================================"
    log_success "Complete!"
    echo "========================================================================"
    echo ""
}

main "$@"
