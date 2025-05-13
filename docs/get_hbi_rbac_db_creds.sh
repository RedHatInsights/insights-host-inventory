#!/bin/bash
# this scripts helps with quickly getting credentials for accessing k8s resources.

PROJECT_NAME=$1

if [ -z "$PROJECT_NAME" ]; then
  echo "openshift project or Kubernetes namespace required as input argument."
  exit 1
fi

echo -e "Using namespace $PROJECT_NAME\n"

# host inventory
HBI_DATABASE_SECRET_NAME="host-inventory-db"
HAS_INVENTORY_SECRET=$(kubectl get secrets -o json -n $PROJECT_NAME | jq ".items[] | select(.metadata.name==\"$HBI_DATABASE_SECRET_NAME\")")
if [ -n "$HAS_INVENTORY_SECRET" ]; then
  INVENTORY_DB_USER=$(kubectl -n "$PROJECT_NAME" get secret/"$HBI_DATABASE_SECRET_NAME" -o custom-columns=:data.username | base64 -d)
  INVENTORY_DB_PASS=$(kubectl -n "$PROJECT_NAME" get secret/"$HBI_DATABASE_SECRET_NAME" -o custom-columns=:data.password | base64 -d)
  INVENTORY_DB_NAME=$(kubectl -n "$PROJECT_NAME" get secret/"$HBI_DATABASE_SECRET_NAME" -o custom-columns=:data.name | base64 -d)
  INVENTORY_DB_HOST=$(kubectl -n "$PROJECT_NAME" get secret/"$HBI_DATABASE_SECRET_NAME" -o custom-columns=:data.hostname | base64 -d)
  echo "INVENTORY_DB_USER: $INVENTORY_DB_USER"
  echo "INVENTORY_DB_PASS: $INVENTORY_DB_PASS"
  echo "INVENTORY_DB_NAME: $INVENTORY_DB_NAME"
  echo "INVENTORY_DB_HOST: $INVENTORY_DB_HOST"
  echo -e ""
  export INVENTORY_DB_USER
  export INVENTORY_DB_PASS
  export INVENTORY_DB_NAME
  export INVENTORY_DB_HOST
else
  echo "$HBI_DATABASE_SECRET_NAME secret not found"
fi

# RBAC
RBAC_SECRET_NAME="rbac-db"
HAS_RBAC_SECRET=$(kubectl get secrets -o json  -n $PROJECT_NAME | jq ".items[] | select(.metadata.name==\"$RBAC_SECRET_NAME\")")
if [ -n "$HAS_RBAC_SECRET" ]; then
  RBAC_USER=$(kubectl -n "$PROJECT_NAME" get secret/"$RBAC_SECRET_NAME" -o custom-columns=:data.username | base64 -d)
  RBAC_PASSWORD=$(kubectl -n "$PROJECT_NAME" get secret/"$RBAC_SECRET_NAME" -o custom-columns=:data.password | base64 -d)
  RBAC_NAME=$(kubectl -n "$PROJECT_NAME" get secret/"$RBAC_SECRET_NAME" -o custom-columns=:data.name | base64 -d)
  RBAC_HOSTNAME=$(kubectl -n "$PROJECT_NAME" get secret/"$RBAC_SECRET_NAME" -o custom-columns=:data.hostname | base64 -d)
  echo "RBAC_USER: $RBAC_USER"
  echo "RBAC_PASSWORD: $RBAC_PASSWORD"
  echo "RBAC_NAME: $RBAC_NAME"
  echo "RBAC_HOSTNAME: $RBAC_HOSTNAME"
  echo -e ""
  export RBAC_USER
  export RBAC_PASSWORD
  export RBAC_NAME
  export RBAC_HOSTNAME
fi
