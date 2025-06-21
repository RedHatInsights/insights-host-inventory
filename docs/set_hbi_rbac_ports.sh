#!/bin/bash

pkill -f "kubectl port-forward"

PROJECT_NAME=$1

if [ -z "$PROJECT_NAME" ]; then
  echo "openshift project or Kubernetes namespace required as input argument."
  exit 1
fi

echo "Using namespace $PROJECT_NAME"

# kafka
ENV_EPHEM_KAFKA_NAME=$(kubectl get kafka -o custom-columns=:metadata.name -n "$PROJECT_NAME" | grep env-ephem |xargs)
ENV_EPHEM_KAFKA_SVC="svc/$ENV_EPHEM_KAFKA_NAME-kafka-bootstrap"
RBAC_KAFKA_NAME=$(kubectl get kafka -o custom-columns=:metadata.name -n "$PROJECT_NAME" | grep rbac |xargs)
RBAC_EPHEM_KAFKA_SVC="svc/$ENV_EPHEM_KAFKA_NAME-kafka-bootstrap"
ENV_EPHEM_CONNECT_NAME=$(kubectl get kafkaconnect -o custom-columns=:metadata.name -n "$PROJECT_NAME" | grep env-ephem | xargs)
ENV_EPHEM_CONNECT_SVC="svc/$ENV_EPHEM_CONNECT_NAME-connect-api"
ENV_EPHEM_FEATURE_FLAG_SVC="svc/$ENV_EPHEM_CONNECT_NAME-connect-api"

# host-inventory
HBI_DB_SVC="svc/host-inventory-db"
HBI_SVC="svc/host-inventory-service"

# rbac
RBAC_DB_SVC="svc/rbac-db"
RBAC_SVC="svc/rbac-service"

# feature flag
FEATURE_FLAG_SVC="svc/env-${PROJECT_NAME}-featureflags"

kubectl port-forward "$ENV_EPHEM_CONNECT_SVC" 8083:8083 -n "$PROJECT_NAME" >/dev/null 2>&1 &
kubectl port-forward "$ENV_EPHEM_KAFKA_SVC" 9092:9092 -n "$PROJECT_NAME" >/dev/null 2>&1 &
kubectl port-forward "$ENV_EPHEM_KAFKA_SVC" 29092:9092 -n "$PROJECT_NAME" >/dev/null 2>&1 &

kubectl port-forward "$RBAC_DB_SVC" 5433:5432 -n "$PROJECT_NAME" >/dev/null 2>&1 &
kubectl port-forward "$RBAC_SVC" 8111:8000 -n "$PROJECT_NAME" >/dev/null 2>&1 &

kubectl port-forward "$HBI_DB_SVC" 5432:5432 -n "$PROJECT_NAME" >/dev/null 2>&1 &
kubectl port-forward "$HBI_SVC" 8000:8000 -n "$PROJECT_NAME" >/dev/null 2>&1 &

kubectl port-forward "$FEATURE_FLAG_SVC" 4242:4242 -n "$PROJECT_NAME" >/dev/null 2>&1 &

pgrep -fla "kubectl port-forward"
