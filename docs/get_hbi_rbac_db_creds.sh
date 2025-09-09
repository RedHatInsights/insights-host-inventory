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
if kubectl get secret "$HBI_DATABASE_SECRET_NAME" -n "$PROJECT_NAME" &> /dev/null; then
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
RBAC_DATABASE_SECRET_NAME="rbac-db"
if kubectl get secret "$RBAC_DATABASE_SECRET_NAME" -n "$PROJECT_NAME" &> /dev/null; then
  RBAC_USER=$(kubectl -n "$PROJECT_NAME" get secret/"$RBAC_DATABASE_SECRET_NAME" -o custom-columns=:data.username | base64 -d)
  RBAC_PASSWORD=$(kubectl -n "$PROJECT_NAME" get secret/"$RBAC_DATABASE_SECRET_NAME" -o custom-columns=:data.password | base64 -d)
  RBAC_NAME=$(kubectl -n "$PROJECT_NAME" get secret/"$RBAC_DATABASE_SECRET_NAME" -o custom-columns=:data.name | base64 -d)
  RBAC_HOSTNAME=$(kubectl -n "$PROJECT_NAME" get secret/"$RBAC_DATABASE_SECRET_NAME" -o custom-columns=:data.hostname | base64 -d)
  echo "RBAC_USER: $RBAC_USER"
  echo "RBAC_PASSWORD: $RBAC_PASSWORD"
  echo "RBAC_NAME: $RBAC_NAME"
  echo "RBAC_HOSTNAME: $RBAC_HOSTNAME"
  echo -e ""
  export RBAC_USER
  export RBAC_PASSWORD
  export RBAC_NAME
  export RBAC_HOSTNAME
else
  echo "$RBAC_DATABASE_SECRET_NAME secret not found"
fi

# kessel-inventory-db
KESSEL_DATABASE_SECRET_NAME="kessel-inventory-db"
if kubectl get secret "$KESSEL_DATABASE_SECRET_NAME" -n "$PROJECT_NAME" &> /dev/null; then
  KESSEL_USER=$(kubectl -n "$PROJECT_NAME" get secret/"$KESSEL_DATABASE_SECRET_NAME" -o custom-columns=:data.username | base64 -d)
  KESSEL_PASSWORD=$(kubectl -n "$PROJECT_NAME" get secret/"$KESSEL_DATABASE_SECRET_NAME" -o custom-columns=:data.password | base64 -d)
  KESSEL_NAME=$(kubectl -n "$PROJECT_NAME" get secret/"$KESSEL_DATABASE_SECRET_NAME" -o custom-columns=:data.name | base64 -d)
  KESSEL_HOSTNAME=$(kubectl -n "$PROJECT_NAME" get secret/"$KESSEL_DATABASE_SECRET_NAME" -o custom-columns=:data.hostname | base64 -d)
  echo "KESSEL_USER: $KESSEL_USER"
  echo "KESSEL_PASSWORD: $KESSEL_PASSWORD"
  echo "KESSEL_NAME: $KESSEL_NAME"
  echo "KESSEL_HOSTNAME: $KESSEL_HOSTNAME"
  echo -e ""
  export KESSEL_USER
  export KESSEL_PASSWORD
  export KESSEL_NAME
  export KESSEL_HOSTNAME
else
  echo "$KESSEL_DATABASE_SECRET_NAME secret not found"
fi
