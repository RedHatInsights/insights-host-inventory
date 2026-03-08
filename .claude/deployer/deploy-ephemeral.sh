#!/bin/bash

#############################################################################
# Auto-Deploy Script for Host Inventory Ephemeral Environment
#############################################################################
# This script automates the following workflow:
# 1. Login to Ephemeral cluster
# 2. Reserve a new namespace
# 3. Deploy host-inventory with its dependencies (Kessel, RBAC)
# 4. Setup port-forwarding for services
# 5. Retrieve database credentials
# 6. Update .env file with new database credentials
# 7. Update /etc/hosts with Kafka bootstrap server
# 8. Save outputs to tmp directory
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

# Function to setup port forwarding
setup_port_forwarding() {
    log "Setting up port-forwarding for services..."

    cd "$HBI_DIR" || {
        log_error "Failed to change to HBI directory: $HBI_DIR"
        exit 1
    }

    # Create tmp directory if it doesn't exist
    mkdir -p "$TMP_DIR"

    # Run port-forwarding script
    local port_forward_output="$TMP_DIR/ephemeral_ports_${TIMESTAMP}.log"

    if bash ./docs/set_hbi_rbac_ports.sh "$PROJECT_NAMESPACE" | tee "$port_forward_output"; then
        log_success "Port-forwarding setup completed"
        log_success "Port-forwarding log saved to: $port_forward_output"
    else
        log_error "Port-forwarding setup failed"
        exit 1
    fi
}

# Function to get database credentials
get_db_credentials() {
    log "Retrieving database credentials..."

    cd "$HBI_DIR" || {
        log_error "Failed to change to HBI directory: $HBI_DIR"
        exit 1
    }

    # Create tmp directory if it doesn't exist
    mkdir -p "$TMP_DIR"

    # Run credentials script
    local creds_output="$TMP_DIR/ephemeral_db_credentials_${TIMESTAMP}.log"

    if bash ./docs/get_hbi_rbac_db_creds.sh "$PROJECT_NAMESPACE" | tee "$creds_output"; then
        log_success "Database credentials retrieved"
        log_success "Credentials saved to: $creds_output"
    else
        log_error "Failed to retrieve database credentials"
        exit 1
    fi
}

# Function to update .env file with database credentials
update_env_file() {
    log "Updating .env file with database credentials..."

    local env_file="$HBI_DIR/.env"
    local creds_file="$TMP_DIR/ephemeral_db_credentials_${TIMESTAMP}.log"

    # Check if credentials file exists
    if [[ ! -f "$creds_file" ]]; then
        log_error "Credentials file not found: $creds_file"
        return 1
    fi

    # Check if .env file exists
    if [[ ! -f "$env_file" ]]; then
        log_error ".env file not found: $env_file"
        return 1
    fi

    # Extract credentials from log file
    local db_user=$(grep "INVENTORY_DB_USER:" "$creds_file" | awk '{print $2}')
    local db_pass=$(grep "INVENTORY_DB_PASS:" "$creds_file" | awk '{print $2}')
    local db_name=$(grep "INVENTORY_DB_NAME:" "$creds_file" | awk '{print $2}')

    # Validate that we got all the values
    if [[ -z "$db_user" || -z "$db_pass" || -z "$db_name" ]]; then
        log_error "Failed to extract all database credentials from $creds_file"
        log_error "  INVENTORY_DB_USER: ${db_user:-NOT FOUND}"
        log_error "  INVENTORY_DB_PASS: ${db_pass:-NOT FOUND}"
        log_error "  INVENTORY_DB_NAME: ${db_name:-NOT FOUND}"
        return 1
    fi

    log "Found credentials:"
    log "  INVENTORY_DB_USER: $db_user"
    log "  INVENTORY_DB_PASS: $db_pass"
    log "  INVENTORY_DB_NAME: $db_name"

    # Create a backup of the .env file
    cp "$env_file" "$env_file.backup_${TIMESTAMP}"
    log "Created backup: $env_file.backup_${TIMESTAMP}"

    # Update the .env file using sed (cross-platform compatible)
    sed_inplace "s/^INVENTORY_DB_USER=.*/INVENTORY_DB_USER=$db_user/" "$env_file"
    sed_inplace "s/^INVENTORY_DB_PASS=.*/INVENTORY_DB_PASS=$db_pass/" "$env_file"
    sed_inplace "s/^INVENTORY_DB_NAME=.*/INVENTORY_DB_NAME=$db_name/" "$env_file"

    log_success ".env file updated successfully"
    log "Updated values in $env_file:"
    log "  INVENTORY_DB_USER=$db_user"
    log "  INVENTORY_DB_PASS=$db_pass"
    log "  INVENTORY_DB_NAME=$db_name"
}

# Function to update /etc/hosts with ephemeral environment
# Assuming sudo is configured for the user and does not require a password
update_etc_hosts_file() {
    log "Updating /etc/hosts with ephemeral environment details..."

    # Extract environment ID from namespace (e.g., ephemeral-ijl7bd -> ijl7bd)
    local env_id="${PROJECT_NAMESPACE#ephemeral-}"

    if [[ -z "$env_id" || "$env_id" == "$PROJECT_NAMESPACE" ]]; then
        log_error "Could not extract environment ID from namespace: $PROJECT_NAMESPACE"
        log_error "Expected format: ephemeral-<id>"
        return 1
    fi

    log "Environment ID: $env_id"

    # Check if we can run sudo without password
    if ! sudo -n true 2>/dev/null; then
        log_error "Passwordless sudo is required to update /etc/hosts"
        log_error "Please configure passwordless sudo and try again"
        return 1
    fi

    # Backup /etc/hosts
    local backup_file="/tmp/hosts.backup.$(date +%Y%m%d_%H%M%S)"
    sudo cp /etc/hosts "$backup_file"
    log "Created backup of /etc/hosts: $backup_file"

    # Get the current ephemeral ID from /etc/hosts (if it exists)
    local current_env_id=$(grep -oE 'ephemeral-[a-z0-9]+' /etc/hosts | head -1 | sed 's/ephemeral-//')

    if [[ -n "$current_env_id" && "$current_env_id" != "$env_id" ]]; then
        log "Replacing old environment ID '$current_env_id' with new ID '$env_id'"

        # Replace all occurrences of the old environment ID with the new one (cross-platform)
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sudo sed -i '' "s/$current_env_id/$env_id/g" /etc/hosts
        else
            sudo sed -i "s/$current_env_id/$env_id/g" /etc/hosts
        fi

        log_success "/etc/hosts updated successfully"
        log "Old environment: ephemeral-$current_env_id"
        log "New environment: ephemeral-$env_id"
    else
        log_warning "No existing ephemeral environment found in /etc/hosts or ID matches current namespace"
        log "You may need to manually add ephemeral entries to /etc/hosts"
    fi

    # Display the current ephemeral entries
    log "Current ephemeral entries in /etc/hosts:"
    grep -i "ephemeral" /etc/hosts || log_warning "No ephemeral entries found"
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
    echo "Outputs saved to: $TMP_DIR"
    echo "  - Port forwarding log: ephemeral_ports_${TIMESTAMP}.log"
    echo "  - Database credentials: ephemeral_db_credentials_${TIMESTAMP}.log"
    echo ""
    echo "Port Forwards Active:"
    echo "  - Host Inventory API:     http://localhost:8000"
    echo "  - RBAC Service:           http://localhost:8111"
    echo "  - Kessel Inventory API:   http://localhost:8222"
    echo "  - Kessel Relations API:   http://localhost:8333"
    echo "  - Kafka Bootstrap:        localhost:9092, localhost:29092"
    echo "  - Kafka Connect:          http://localhost:8083"
    echo "  - Feature Flags:          http://localhost:4242"
    echo "  - HBI Database:           localhost:5432"
    echo "  - RBAC Database:          localhost:5433"
    echo "  - Kessel Database:        localhost:5434"
    echo ""
    echo "To view namespace details:"
    echo "  bonfire namespace describe"
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
    setup_port_forwarding
    get_db_credentials
    update_env_file
    update_etc_hosts_file
    display_summary

    log_success "All tasks completed successfully!"
}

# Run main function
main "$@"
