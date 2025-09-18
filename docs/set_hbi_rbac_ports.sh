#!/bin/bash

# Function to check and kill existing kubectl port-forwards
check_and_kill_port_forwards() {
    echo "Checking for existing kubectl port-forwards..."

    # Get all kubectl port-forward processes
    local port_forward_pids=$(pgrep -f "kubectl port-forward" 2>/dev/null)

    if [ -n "$port_forward_pids" ]; then
        echo "Found existing kubectl port-forward processes: $port_forward_pids"
        echo "Killing existing port-forward processes..."

        # Kill each process
        for pid in $port_forward_pids; do
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid"
                echo "Killed process $pid"
            fi
        done

        # Wait a moment for processes to terminate
        sleep 2

        # Force kill any remaining processes
        local remaining_pids=$(pgrep -f "kubectl port-forward" 2>/dev/null)
        if [ -n "$remaining_pids" ]; then
            echo "Force killing remaining processes: $remaining_pids"
            pkill -9 -f "kubectl port-forward"
            sleep 1
        fi

        echo "All existing port-forward processes have been terminated."
    else
        echo "No existing kubectl port-forward processes found."
    fi

    echo "----------------------------------------"
}

# Function to start port-forwarding
start_port_forwards() {
    echo "Starting new kubectl port-forwards..."

    # kafka
    ENV_EPHEM_KAFKA_NAME=$(kubectl get kafka -o custom-columns=:metadata.name -n "$PROJECT_NAME" | grep env-ephem |xargs)
    ENV_EPHEM_KAFKA_SVC="svc/$ENV_EPHEM_KAFKA_NAME-kafka-bootstrap"
    RBAC_KAFKA_NAME=$(kubectl get kafka -o custom-columns=:metadata.name -n "$PROJECT_NAME" | grep rbac |xargs)
    RBAC_EPHEM_KAFKA_SVC="svc/$RBAC_KAFKA_NAME-kafka-bootstrap"
    ENV_EPHEM_CONNECT_NAME=$(kubectl get kafkaconnect -o custom-columns=:metadata.name -n "$PROJECT_NAME" | grep env-ephem | xargs)
    ENV_EPHEM_CONNECT_SVC="svc/$ENV_EPHEM_CONNECT_NAME-connect-api"

    # host-inventory
    HBI_DB_SVC="svc/host-inventory-db"
    HBI_SVC="svc/host-inventory-service"

    # rbac
    RBAC_DB_SVC="svc/rbac-db"
    RBAC_SVC="svc/rbac-service"

    # kessel
    KESSEL_DB_SVC="svc/kessel-inventory-db"
    KESSEL_API_SVC="svc/kessel-inventory-api"
    KESSEL_RELATIONS_SVC="svc/kessel-relations-api"


    # feature flag
    FEATURE_FLAG_SVC="svc/env-${PROJECT_NAME}-featureflags"

    kubectl port-forward "$ENV_EPHEM_CONNECT_SVC" 8083:8083 -n "$PROJECT_NAME" >/dev/null 2>&1 &
    kubectl port-forward "$ENV_EPHEM_KAFKA_SVC" 9092:9092 -n "$PROJECT_NAME" >/dev/null 2>&1 &
    kubectl port-forward "$ENV_EPHEM_KAFKA_SVC" 29092:9092 -n "$PROJECT_NAME" >/dev/null 2>&1 &
    kubectl port-forward "$FEATURE_FLAG_SVC" 4242:4242 -n "$PROJECT_NAME" >/dev/null 2>&1 &
    kubectl port-forward "$HBI_SVC" 8000:8000 -n "$PROJECT_NAME" >/dev/null 2>&1 &
    kubectl port-forward "$KESSEL_API_SVC" 8222:8000 -n "$PROJECT_NAME" >/dev/null 2>&1 &
    kubectl port-forward "$KESSEL_RELATIONS_SVC" 8333:8000 -n "$PROJECT_NAME" >/dev/null 2>&1 &
    kubectl port-forward "$RBAC_SVC" 8111:8000 -n "$PROJECT_NAME" >/dev/null 2>&1 &

    kubectl port-forward "$HBI_DB_SVC" 5432:5432 -n "$PROJECT_NAME" >/dev/null 2>&1 &
    kubectl port-forward "$KESSEL_DB_SVC" 5434:5432 -n "$PROJECT_NAME" >/dev/null 2>&1 &
    kubectl port-forward "$RBAC_DB_SVC" 5433:5432 -n "$PROJECT_NAME" >/dev/null 2>&1 &

    echo "Port-forwarding started. Waiting for processes to initialize..."
    sleep 3

    # Show active port-forward processes
    echo "Active kubectl port-forward processes:"
    pgrep -fla "kubectl port-forward"
}

PROJECT_NAME=$1

if [ -z "$PROJECT_NAME" ]; then
  echo "openshift project or Kubernetes namespace required as input argument."
  exit 1
fi

echo "Using namespace $PROJECT_NAME"
echo "========================================"

# Check and kill existing port-forwards
check_and_kill_port_forwards

# Start new port-forwards
start_port_forwards

echo "========================================"
echo "Port-forwarding setup complete!"
