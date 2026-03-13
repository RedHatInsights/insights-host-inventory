#!/bin/bash
# Deploy IQE Test Pod using ClowdJobInvocation
# This script creates an IQE pod in an ephemeral namespace for running tests
#
# Usage:
#   ./deploy-iqe-pod.sh [NAMESPACE] [TEST_MARKERS]
#
# Arguments:
#   NAMESPACE      - Ephemeral namespace (optional, auto-detected if not provided)
#   TEST_MARKERS   - Pytest markers for test selection (optional, default: "backend and smoke and not resilience and not cert_auth and not rbac_dependent")
#
# Returns:
#   Outputs pod name to stdout on success
#   Returns exit code 0 on success, non-zero on failure
#
# Examples:
#   ./deploy-iqe-pod.sh
#   ./deploy-iqe-pod.sh ephemeral-abc123
#   ./deploy-iqe-pod.sh ephemeral-abc123 "backend and smoke"
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

# Parse arguments
NAMESPACE="${1:-}"
TEST_MARKERS="${2:-$DEFAULT_MARKERS}"

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
log_info "Test markers: $TEST_MARKERS"

# Run bonfire deploy-iqe-cji and capture output
DEPLOY_OUTPUT=$(bonfire deploy-iqe-cji host-inventory \
    -m "$TEST_MARKERS" \
    -n "$NAMESPACE" 2>&1)

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
