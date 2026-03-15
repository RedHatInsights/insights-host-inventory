#!/bin/bash
# Deploy IQE Test Pod using ClowdJobInvocation
# This script creates an IQE pod in an ephemeral namespace for running tests
#
# Usage:
#   ./deploy-iqe-pod.sh [OPTIONS] [NAMESPACE] [TEST_EXPRESSION]
#
# Arguments:
#   NAMESPACE         - Ephemeral namespace (optional, auto-detected if not provided)
#   TEST_EXPRESSION   - Pytest markers (-m) or test filter (-k) expression
#                       Default: "backend and smoke and not resilience and not cert_auth and not rbac_dependent"
#
# Options:
#   -k, --filter      - Use pytest -k filter (test name matching) instead of -m markers
#   -m, --marker      - Use pytest -m markers (default behavior)
#
# Returns:
#   Outputs pod name to stdout on success
#   Returns exit code 0 on success, non-zero on failure
#
# Examples:
#   ./deploy-iqe-pod.sh
#   ./deploy-iqe-pod.sh ephemeral-abc123
#   ./deploy-iqe-pod.sh ephemeral-abc123 "backend and smoke"
#   ./deploy-iqe-pod.sh -k "test_cache_invalidation or test_kessel_repl"
#   ./deploy-iqe-pod.sh -k ephemeral-abc123 "test_rbac_groups"
#   POD=$(./deploy-iqe-pod.sh) && oc logs -f -n $NAMESPACE $POD

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
DEFAULT_MARKERS="backend and smoke and not resilience and not cert_auth and not rbac_dependent"
USE_FILTER=false

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

# Deploy IQE pod using bonfire
log_info "Deploying IQE pod to namespace: $NAMESPACE"
if [ "$USE_FILTER" = true ]; then
    log_info "Test filter (-k): $TEST_EXPRESSION"
else
    log_info "Test markers (-m): $TEST_EXPRESSION"
fi

# Run bonfire deploy-iqe-cji and capture output
if [ "$USE_FILTER" = true ]; then
    DEPLOY_OUTPUT=$(bonfire deploy-iqe-cji host-inventory \
        -k "$TEST_EXPRESSION" \
        -n "$NAMESPACE" 2>&1)
else
    DEPLOY_OUTPUT=$(bonfire deploy-iqe-cji host-inventory \
        -m "$TEST_EXPRESSION" \
        -n "$NAMESPACE" 2>&1)
fi

# Extract pod name from output
POD_NAME=$(echo "$DEPLOY_OUTPUT" | grep -oE "pod '[^']+' related to CJI" | grep -oE "'[^']+'" | tr -d "'" | head -1)

if [ -z "$POD_NAME" ]; then
    log_error "Failed to extract pod name from bonfire output"
    log_error "Output was:"
    echo "$DEPLOY_OUTPUT" >&2
    exit 1
fi

# Verify pod is running
log_info "Waiting for pod to be ready..."
if oc wait --for=condition=Ready pod/$POD_NAME -n $NAMESPACE --timeout=60s >/dev/null 2>&1; then
    log_success "IQE pod deployed successfully!"
    log_info "Pod: $POD_NAME"
    log_info "Namespace: $NAMESPACE"
    log_info ""
    log_info "View logs with:"
    log_info "  oc logs -n $NAMESPACE $POD_NAME -f"
    echo ""

    # Output pod name to stdout (for script usage)
    echo "$POD_NAME"
    exit 0
else
    log_error "Pod failed to become ready"
    oc get pod/$POD_NAME -n $NAMESPACE >&2 || true
    exit 1
fi
