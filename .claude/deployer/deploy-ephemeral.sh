#!/bin/bash

#############################################################################
# Deploy Script for Host Inventory Ephemeral Environment
#############################################################################
# This script automates the following workflow:
# 1. Login to Ephemeral cluster
# 2. Reserve a new namespace
# 3. Deploy host-inventory with its dependencies (Kessel, RBAC)
# 4. Verify deployment is successful
#
# For local development setup (port-forwarding, credentials, etc.),
# run setup-for-dev.sh after this completes.
#############################################################################

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HBI_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEPLOYER_DIR="$SCRIPT_DIR"
TMP_DIR="$HBI_DIR/tmp"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

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

log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] ⚠${NC} $1"
}

# Portable sed in-place editing for macOS and Linux
sed_inplace() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS requires empty string after -i
        sed -i '' "$@"
    else
        # Linux uses -i without argument
        sed -i "$@"
    fi
}

# Function to check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."

    local missing_deps=()

    command -v oc >/dev/null 2>&1 || missing_deps+=("oc")
    command -v bonfire >/dev/null 2>&1 || missing_deps+=("bonfire")
    command -v kubectl >/dev/null 2>&1 || missing_deps+=("kubectl")
    command -v jq >/dev/null 2>&1 || missing_deps+=("jq")

    if [ ${#missing_deps[@]} -ne 0 ]; then
        log_error "Missing required dependencies: ${missing_deps[*]}"
        log_error "Please install the missing dependencies and try again."
        exit 1
    fi

    # Try to get token and server from current oc session first
    if [[ -z "${EPHEMERAL_TOKEN}" ]]; then
        log "EPHEMERAL_TOKEN not set, attempting to get from current oc session..."
        EPHEMERAL_TOKEN=$(oc whoami -t 2>/dev/null || true)
        if [[ -n "${EPHEMERAL_TOKEN}" ]]; then
            log_success "Got EPHEMERAL_TOKEN from current oc session"
            export EPHEMERAL_TOKEN
        fi
    fi

    if [[ -z "${EPHEMERAL_SERVER}" ]]; then
        log "EPHEMERAL_SERVER not set, attempting to get from current oc session..."
        EPHEMERAL_SERVER=$(oc whoami --show-server 2>/dev/null || true)
        if [[ -n "${EPHEMERAL_SERVER}" ]]; then
            log_success "Got EPHEMERAL_SERVER from current oc session"
            export EPHEMERAL_SERVER
        fi
    fi

    # Final validation
    if [[ -z "${EPHEMERAL_TOKEN}" ]]; then
        log_error "EPHEMERAL_TOKEN is not set and could not be retrieved from oc session"
        log "Please login to the cluster first, or set EPHEMERAL_TOKEN manually"
        log "Get token from: https://oauth-openshift.apps.crc-eph.r9lp.p1.openshiftapps.com/oauth/token/request"
        exit 1
    fi

    if [[ -z "${EPHEMERAL_SERVER}" ]]; then
        log_error "EPHEMERAL_SERVER is not set and could not be retrieved from oc session"
        log "Please login to the cluster first, or set EPHEMERAL_SERVER manually"
        log "Usually: https://api.crc-eph.r9lp.p1.openshiftapps.com:6443"
        exit 1
    fi

    log_success "All prerequisites satisfied"
    log "Using server: $EPHEMERAL_SERVER"
}

# Function to login to ephemeral cluster
login_to_cluster() {
    log "Logging into Ephemeral cluster..."

    # Check if already logged in
    user="$(oc whoami 2>/dev/null || true)"
    if [[ -n "$user" ]]; then
        log_warning "Already logged in as user: $user"
        return 0
    fi

    if oc login --token="${EPHEMERAL_TOKEN}" --server="${EPHEMERAL_SERVER}"; then
        log_success "Successfully logged into Ephemeral cluster"
    else
        log_error "Failed to login to Ephemeral cluster"
        exit 1
    fi
}

# Function to reserve namespace
reserve_namespace() {
    log "Checking current namespace..."

    NAMESPACE=$(oc project -q 2>/dev/null || true)

    if [[ -z "$NAMESPACE" || "$NAMESPACE" == "default" ]]; then
        log "No bonfire namespace set or using 'default', reserving a new namespace..."

        # Parse duration argument
        DURATION="${1:-10h}"
        log "Reserving namespace for duration: $DURATION"

        if bonfire namespace reserve --duration "$DURATION"; then
            NAMESPACE=$(oc project -q)
            log_success "Reserved namespace: $NAMESPACE"
        else
            log_error "Failed to reserve namespace"
            exit 1
        fi
    else
        log_warning "Using existing namespace: $NAMESPACE"

        # Check if force flag is set
        if [[ "$FORCE_USE_EXISTING" == "true" ]]; then
            log_success "Force flag set, continuing with existing namespace"
        else
            read -p "Do you want to continue with this namespace? (y/n) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                log "Aborting deployment"
                exit 0
            fi
        fi
    fi

    # Export namespace for use in other functions
    export PROJECT_NAMESPACE="$NAMESPACE"
}

# Function to deploy services
deploy_services() {
    log "Starting deployment of host-inventory and dependencies..."

    cd "$DEPLOYER_DIR" || {
        log_error "Failed to change to deployer directory: $DEPLOYER_DIR"
        exit 1
    }

    # Run bonfire deployment script
    log "Running bonfire deployment..."

    if bash ./bonfire-deploy.sh "$@"; then
        log_success "Deployment completed successfully"

        # Re-read namespace after deployment (bonfire may have switched to a different namespace)
        NAMESPACE=$(oc project -q)
        export PROJECT_NAMESPACE="$NAMESPACE"
        log "Using namespace: $PROJECT_NAMESPACE"
    else
        log_error "Deployment failed"
        exit 1
    fi
}

# Function to display summary
display_summary() {
    echo ""
    echo "========================================================================"
    echo -e "${GREEN}Deployment Complete!${NC}"
    echo "========================================================================"
    echo ""
    echo "Namespace: $PROJECT_NAMESPACE"
    echo ""
    echo "Services Deployed:"
    echo "  - Host Inventory (API + MQ service)"
    echo "  - Kessel Inventory API"
    echo "  - Kessel Relations API (SpiceDB)"
    echo "  - RBAC v2 Service"
    echo "  - Kafka + Zookeeper"
    echo "  - PostgreSQL (HBI, RBAC, Kessel databases)"
    echo "  - Unleash (Feature Flags)"
    echo ""
    echo "View deployment status:"
    echo "  bonfire namespace describe"
    echo "  kubectl get pods -n $PROJECT_NAMESPACE"
    echo ""
    echo "View namespace in console:"
    bonfire namespace describe | grep "console url" || true
    echo ""
    echo "To release namespace when done:"
    echo "  bonfire namespace release $PROJECT_NAMESPACE"
    echo ""
    echo "========================================================================"
}

# Function to handle cleanup on error
cleanup_on_error() {
    log_error "Script failed. Cleaning up..."
    # Add any cleanup logic here if needed
    exit 1
}

# Trap errors
trap cleanup_on_error ERR

# Main execution
main() {
    echo ""
    echo "========================================================================"
    echo "  Auto-Deploy Script for Host Inventory Ephemeral Environment"
    echo "========================================================================"
    echo ""

    # Parse command-line arguments
    NAMESPACE_DURATION="335h"
    FORCE_USE_EXISTING="false"
    DEPLOY_ARGS=()

    while [[ $# -gt 0 ]]; do
        case $1 in
            --duration)
                NAMESPACE_DURATION="$2"
                shift 2
                ;;
            --force)
                FORCE_USE_EXISTING="true"
                shift
                ;;
            --help)
                echo "Usage: $0 [OPTIONS] [DEPLOY_ARGS...]"
                echo ""
                echo "Options:"
                echo "  --duration DURATION    Namespace reservation duration (default: 335h)"
                echo "  --force                Use existing namespace without prompting"
                echo "  --help                 Show this help message"
                echo ""
                echo "Deploy Arguments (passed to bonfire-deploy.sh):"
                echo "  [template_ref]         Git ref for host-inventory deploy template"
                echo "  [image]                Custom host-inventory image"
                echo "  [tag]                  Custom image tag"
                echo "  [schema_file]          Path to local SpiceDB schema file"
                echo ""
                echo "Examples:"
                echo "  $0"
                echo "  $0 --force"
                echo "  $0 --duration 8h"
                echo "  $0 --force main quay.io/myrepo/inventory v1.0"
                echo ""
                exit 0
                ;;
            *)
                DEPLOY_ARGS+=("$1")
                shift
                ;;
        esac
    done

    # Export force flag for use in reserve_namespace function
    export FORCE_USE_EXISTING

    # Execute workflow
    check_prerequisites
    login_to_cluster
    reserve_namespace "$NAMESPACE_DURATION"
    deploy_services "${DEPLOY_ARGS[@]}"
    display_summary

    log_success "Deployment completed successfully!"
    echo ""
    echo "Next Steps:"
    echo "  Run '/hbi-setup-for-dev' or './claude/deployer/setup-for-dev.sh'"
    echo "  to configure local development environment (port-forwards, .env, etc.)"
    echo ""
}

# Run main function
main "$@"
