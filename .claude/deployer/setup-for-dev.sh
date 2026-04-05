#!/bin/bash

#############################################################################
# Setup for Development Script - HBI Ephemeral Environment
#############################################################################
# This script sets up local development environment after deployment:
# 1. Setup port-forwarding for services
# 2. Retrieve database credentials
# 3. Update .env file with new database credentials
# 4. Update /etc/hosts with Kafka bootstrap server
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

# Function to get current namespace
get_namespace() {
    local namespace=$(oc project -q 2>/dev/null || kubectl config view --minify -o jsonpath='{..namespace}' 2>/dev/null)

    if [[ -z "$namespace" || "$namespace" == "default" ]]; then
        log_error "No active namespace found"
        log_error "Please deploy HBI first using /hbi-deploy or switch to an ephemeral namespace"
        exit 1
    fi

    echo "$namespace"
}

# Function to verify namespace exists and is accessible
verify_namespace_exists() {
    log "Verifying namespace exists: $PROJECT_NAMESPACE"

    # Check if namespace exists
    if ! kubectl get namespace "$PROJECT_NAMESPACE" >/dev/null 2>&1; then
        log_error "Namespace '$PROJECT_NAMESPACE' does not exist"
        log_error "Please deploy HBI first using /hbi-deploy"
        log ""
        log "Available ephemeral namespaces:"
        kubectl get namespaces | grep ephemeral || log "  No ephemeral namespaces found"
        exit 1
    fi

    # Check if we have access to the namespace
    if ! kubectl get pods -n "$PROJECT_NAMESPACE" >/dev/null 2>&1; then
        log_error "Cannot access namespace '$PROJECT_NAMESPACE'"
        log_error "You may not have permissions or the namespace may be in bad state"
        exit 1
    fi

    log_success "Namespace '$PROJECT_NAMESPACE' exists and is accessible"
}

# Function to check namespace health
check_namespace_health() {
    log "Checking namespace health..."

    # Get all pods in the namespace
    local total_pods=$(kubectl get pods -n "$PROJECT_NAMESPACE" --no-headers 2>/dev/null | wc -l | tr -d ' ')

    if [[ "$total_pods" -eq 0 ]]; then
        log_error "No pods found in namespace '$PROJECT_NAMESPACE'"
        log_error "The namespace appears to be empty. Please deploy HBI first using /hbi-deploy"
        exit 1
    fi

    log "Found $total_pods pods in namespace"

    # Check for required HBI pods
    local required_pods=(
        "host-inventory-service"
        "host-inventory-db"
        "kessel-inventory-api"
        "kessel-relations-api"
        "rbac-service"
    )

    local missing_pods=()
    for pod in "${required_pods[@]}"; do
        if ! kubectl get pods -n "$PROJECT_NAMESPACE" --no-headers 2>/dev/null | grep -q "^$pod"; then
            missing_pods+=("$pod")
        fi
    done

    if [[ ${#missing_pods[@]} -gt 0 ]]; then
        log_error "Required pods are missing:"
        for pod in "${missing_pods[@]}"; do
            log_error "  - $pod"
        done
        log_error "Please deploy HBI first using /hbi-deploy"
        exit 1
    fi

    log_success "All required pods found"

    # Check pod statuses
    log "Checking pod health status..."

    local not_ready_pods=$(kubectl get pods -n "$PROJECT_NAMESPACE" --no-headers 2>/dev/null | grep -v "Running\|Completed" || true)

    if [[ -n "$not_ready_pods" ]]; then
        log_warning "Some pods are not in Running state:"
        echo "$not_ready_pods" | while read -r line; do
            log_warning "  $line"
        done

        read -p "Do you want to continue anyway? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log "Setup aborted by user"
            exit 0
        fi
    else
        log_success "All pods are healthy"
    fi

    # Display pod summary
    log "Pod summary:"
    kubectl get pods -n "$PROJECT_NAMESPACE" --no-headers | awk '{print "  " $1 " -> " $3}' | head -10

    if [[ "$total_pods" -gt 10 ]]; then
        log "  ... and $((total_pods - 10)) more pods"
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

    log_success ".env file updated with database credentials"
    log "Updated values in $env_file:"
    log "  INVENTORY_DB_USER=$db_user"
    log "  INVENTORY_DB_PASS=$db_pass"
    log "  INVENTORY_DB_NAME=$db_name"

    # Extract Unleash credentials from log file
    local unleash_token=$(grep "UNLEASH_TOKEN:" "$creds_file" | awk '{print $2}')
    local unleash_url=$(grep "UNLEASH_URL:" "$creds_file" | awk '{print $2}')

    # Update Unleash configuration if found
    if [[ -n "$unleash_token" && -n "$unleash_url" ]]; then
        log "Found Unleash configuration:"
        log "  UNLEASH_TOKEN: ${unleash_token:0:40}..."
        log "  UNLEASH_URL: $unleash_url"

        sed_inplace "s|^UNLEASH_TOKEN=.*|UNLEASH_TOKEN='$unleash_token'|" "$env_file"
        sed_inplace "s|^UNLEASH_URL=.*|UNLEASH_URL=\"$unleash_url\"|" "$env_file"

        log_success "Unleash configuration updated in .env"
    else
        log_warning "Unleash configuration not found in credentials file"
        log_warning "Feature flags may not work correctly"
    fi
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
    echo -e "${GREEN}Development Environment Setup Complete!${NC}"
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
    echo "Updated Files:"
    echo "  - $HBI_DIR/.env (database credentials, Unleash token)"
    echo "  - /etc/hosts (Kafka bootstrap server)"
    echo ""
    echo "You can now run tests locally with:"
    echo "  pipenv run pytest tests/"
    echo ""
    echo "========================================================================"
}

# Function to handle cleanup on error
cleanup_on_error() {
    log_error "Script failed. Cleaning up..."
    exit 1
}

# Trap errors
trap cleanup_on_error ERR

# Main execution
main() {
    echo ""
    echo "========================================================================"
    echo "  HBI Development Environment Setup"
    echo "========================================================================"
    echo ""

    # Parse command-line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --namespace)
                PROJECT_NAMESPACE="$2"
                shift 2
                ;;
            --help)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --namespace NAMESPACE  Use specific namespace (default: current context)"
                echo "  --help                 Show this help message"
                echo ""
                echo "This script sets up your local development environment by:"
                echo "  1. Setting up port-forwarding to ephemeral services"
                echo "  2. Retrieving database credentials"
                echo "  3. Updating .env file with credentials"
                echo "  4. Updating /etc/hosts with Kafka bootstrap server"
                echo ""
                echo "Prerequisites:"
                echo "  - HBI must be deployed (use /hbi-deploy first)"
                echo "  - Must be logged into ephemeral cluster (oc/kubectl)"
                echo "  - Passwordless sudo configured for /etc/hosts updates"
                echo ""
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
    done

    # Get namespace if not provided
    if [[ -z "$PROJECT_NAMESPACE" ]]; then
        PROJECT_NAMESPACE=$(get_namespace)
    fi

    log "Using namespace: $PROJECT_NAMESPACE"
    export PROJECT_NAMESPACE

    # Verify namespace exists and is healthy before proceeding
    verify_namespace_exists
    check_namespace_health

    # Execute setup workflow
    setup_port_forwarding
    get_db_credentials
    update_env_file
    update_etc_hosts_file
    display_summary

    log_success "All setup tasks completed successfully!"
}

# Run main function
main "$@"
