#!/bin/bash
# Deploy IQE Test Pod with ClowdJobInvocation Cleanup
# This script cleans up any existing IQE ClowdJobInvocations before deploying a fresh pod
#
# Usage:
#   ./hbi-deploy-iqe-pod.sh [OPTIONS] [NAMESPACE] [TEST_EXPRESSION]
#
# Arguments:
#   NAMESPACE         - Ephemeral namespace (optional, auto-detected if not provided)
#   TEST_EXPRESSION   - Pytest markers (-m) or test filter (-k) expression
#                       Default: "backend and not resilience and not cert_auth and not rbac_dependent"
#
# Options:
#   -k, --filter      - Use pytest -k filter (test name matching) instead of -m markers
#   -m, --marker      - Use pytest -m markers (default behavior)
#   --debug-pod       - Create debug pod (interactive shell access)
#
# Returns:
#   Outputs pod name to stdout on success
#   Returns exit code 0 on success, non-zero on failure
#
# Examples:
#   ./hbi-deploy-iqe-pod.sh
#   ./hbi-deploy-iqe-pod.sh ephemeral-abc123
#   ./hbi-deploy-iqe-pod.sh -k "test_cache_invalidation or test_rbac"
#   ./hbi-deploy-iqe-pod.sh -m "smoke" ephemeral-abc123
#   ./hbi-deploy-iqe-pod.sh --debug-pod

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
DEFAULT_MARKERS="backend and not resilience and not cert_auth and not rbac_dependent"
USE_FILTER=false
DEBUG_POD=false

# Parse options
while [[ $# -gt 0 ]]; do
    case $1 in
        -k|--filter)
            USE_FILTER=true
            shift
            ;;
        -m|--marker)
            USE_FILTER=false
            shift
            ;;
        --debug-pod)
            DEBUG_POD=true
            shift
            ;;
        *)
            break
            ;;
    esac
done

# Parse positional arguments
NAMESPACE="${1:-}"
TEST_EXPRESSION="${2:-$DEFAULT_MARKERS}"

# Function to log messages to stderr (so stdout is clean for pod name)
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1" >&2
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" >&2
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" >&2
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# Auto-detect namespace if not provided
if [ -z "$NAMESPACE" ]; then
    log_info "No namespace provided, auto-detecting..."
    NAMESPACE=$(bonfire namespace list 2>/dev/null | grep $(whoami) | awk '{print $1}' | head -1)

    if [ -z "$NAMESPACE" ]; then
        log_error "Could not auto-detect namespace. Please provide namespace as first argument."
        exit 1
    fi

    log_info "Auto-detected namespace: $NAMESPACE"
fi

# Verify namespace exists and is owned by user
log_info "Verifying namespace ownership..."
if ! bonfire namespace list 2>/dev/null | grep -q "$NAMESPACE"; then
    log_error "Namespace '$NAMESPACE' not found or not owned by user."
    exit 1
fi

# Check for existing ClowdJobInvocations
log_info "Checking for existing IQE ClowdJobInvocations..."
EXISTING_CJI=$(oc get ClowdJobInvocation -n "$NAMESPACE" 2>/dev/null | grep -E "iqe-host-inventory|iqe-hbi" | awk '{print $1}' || true)

if [ -n "$EXISTING_CJI" ]; then
    log_warning "Found existing ClowdJobInvocation(s):"
    echo "$EXISTING_CJI" | while read cji; do
        log_warning "  - $cji" >&2
    done

    log_info "Deleting old ClowdJobInvocation(s)..."
    echo "$EXISTING_CJI" | while read cji; do
        if oc delete ClowdJobInvocation "$cji" -n "$NAMESPACE" >/dev/null 2>&1; then
            log_success "Deleted: $cji"
        else
            log_warning "Failed to delete: $cji (may not exist)"
        fi
    done

    # Wait a moment for cleanup to complete
    log_info "Waiting for cleanup to complete..."
    sleep 3
else
    log_info "No existing ClowdJobInvocations found"
fi

# Build bonfire command
BONFIRE_CMD="bonfire deploy-iqe-cji host-inventory"

# Add debug-pod flag if requested
if [ "$DEBUG_POD" = true ]; then
    BONFIRE_CMD="$BONFIRE_CMD --debug-pod"
    log_info "Debug pod mode enabled"
fi

# Add test expression
if [ "$USE_FILTER" = true ]; then
    BONFIRE_CMD="$BONFIRE_CMD -k \"$TEST_EXPRESSION\""
    log_info "Test filter (-k): $TEST_EXPRESSION"
else
    BONFIRE_CMD="$BONFIRE_CMD -m \"$TEST_EXPRESSION\""
    log_info "Test markers (-m): $TEST_EXPRESSION"
fi

# Add namespace
BONFIRE_CMD="$BONFIRE_CMD -n \"$NAMESPACE\""

# Deploy IQE pod using bonfire
log_info "Creating new ClowdJobInvocation..."
log_info "Command: $BONFIRE_CMD"

# Run bonfire deploy-iqe-cji and capture output
DEPLOY_OUTPUT=$(eval "$BONFIRE_CMD" 2>&1)

# Extract pod name from output
POD_NAME=$(echo "$DEPLOY_OUTPUT" | grep -oE "pod '[^']+' related to CJI" | grep -oE "'[^']+'" | tr -d "'" | head -1)

if [ -z "$POD_NAME" ]; then
    log_error "Failed to extract pod name from bonfire output"
    log_error "Output was:"
    echo "$DEPLOY_OUTPUT" >&2
    exit 1
fi

log_success "ClowdJobInvocation created successfully"
log_info "Pod: $POD_NAME"

# Verify pod exists
log_info "Waiting for pod to start..."
if ! oc get pod "$POD_NAME" -n "$NAMESPACE" >/dev/null 2>&1; then
    log_error "Pod '$POD_NAME' not found in namespace '$NAMESPACE'"
    exit 1
fi

# Wait for pod to be ready (or running for debug pods)
if [ "$DEBUG_POD" = true ]; then
    log_info "Waiting for debug pod to be running..."
    if oc wait --for=jsonpath='{.status.phase}'=Running pod/$POD_NAME -n $NAMESPACE --timeout=60s >/dev/null 2>&1; then
        log_success "Debug IQE pod is running!"
    else
        log_warning "Pod may not be running yet"
    fi
else
    log_info "Waiting for pod to be ready..."
    if oc wait --for=condition=Ready pod/$POD_NAME -n $NAMESPACE --timeout=60s >/dev/null 2>&1; then
        log_success "IQE pod is ready!"
    else
        log_warning "Pod may not be ready yet (this is normal for test pods)"
    fi
fi

# Display helpful information
log_info "Namespace: $NAMESPACE"
log_info ""
log_info "View logs with:"
log_info "  oc logs -n $NAMESPACE $POD_NAME -f"
log_info ""

if [ "$DEBUG_POD" = true ]; then
    log_info "Access debug shell with:"
    log_info "  oc rsh -n $NAMESPACE $POD_NAME"
    log_info ""
fi

log_info "Check pod status with:"
log_info "  oc get pod $POD_NAME -n $NAMESPACE"
echo "" >&2

# Output pod name to stdout (for script usage)
echo "$POD_NAME"
exit 0
