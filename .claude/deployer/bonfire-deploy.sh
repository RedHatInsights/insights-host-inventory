#!/bin/bash

#############################################################################
# Bonfire Deployment Script
#############################################################################
# Extracted from insights-service-deployer/deploy.sh
# Handles the bonfire deployment, demo data setup, and Kessel configuration
#############################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Deploy HBI with all dependencies using bonfire
# Parameters: $1: deploy template branch; $2: custom image; $3: custom image tag; $4: local schema file path
deploy() {
  echo "Deploying Host Inventory with Kessel and RBAC..."

  NAMESPACE=$(oc project -q)

  HBI_CUSTOM_IMAGE="quay.io/redhat-services-prod/insights-management-tenant/insights-host-inventory/insights-host-inventory"
  HBI_CUSTOM_IMAGE_TAG=latest
  HBI_CUSTOM_IMAGE_PARAMETER=""
  LOCAL_SCHEMA_FILE=""

  if [ -n "$1" ]; then
    HBI_DEPLOYMENT_TEMPLATE_REF="$1"
  else
    HOST_GIT_COMMIT=$(git ls-remote https://github.com/RedHatInsights/insights-host-inventory HEAD | awk '{print $1}')
    HBI_DEPLOYMENT_TEMPLATE_REF="$HOST_GIT_COMMIT"
  fi
  if [ -n "$2" ]; then
    HBI_CUSTOM_IMAGE="$2"
    HBI_CUSTOM_IMAGE_PARAMETER="-p host-inventory/IMAGE=${HBI_CUSTOM_IMAGE}"
  fi
  if [ -n "$3" ]; then
    HBI_CUSTOM_IMAGE_TAG="$3"
  fi
  if [ -n "$4" ]; then
    LOCAL_SCHEMA_FILE="$4"
  fi

  # Fetch frontend commit with fallback to 'latest' if git fails
  HOST_FRONTEND_GIT_COMMIT=$(git ls-remote https://github.com/RedHatInsights/insights-inventory-frontend HEAD 2>/dev/null | awk '{print $1}' | cut -c1-7)
  if [ -z "$HOST_FRONTEND_GIT_COMMIT" ]; then
    echo "⚠️  WARNING: Failed to fetch frontend commit, using 'latest' instead"
    HOST_FRONTEND_GIT_COMMIT="latest"
  fi

  echo "Deployment parameters:"
  echo "  Template ref: $HBI_DEPLOYMENT_TEMPLATE_REF"
  echo "  Image: $HBI_CUSTOM_IMAGE"
  echo "  Tag: $HBI_CUSTOM_IMAGE_TAG"
  echo "  Frontend commit: $HOST_FRONTEND_GIT_COMMIT"
  echo "  Schema file: ${LOCAL_SCHEMA_FILE:-Download from rbac-config}"

  bonfire deploy host-inventory -F true \
    -p host-inventory/RBAC_V2_FORCE_ORG_ADMIN=true \
    -p host-inventory/URLLIB3_LOG_LEVEL=WARN \
    --ref-env insights-stage \
    --set-template-ref host-inventory="$HBI_DEPLOYMENT_TEMPLATE_REF" \
    -p rbac/MEMORY_LIMIT=512Mi \
    -p rbac/MEMORY_REQUEST=256Mi \
    -p rbac/RBAC_KAFKA_CONSUMER_REPLICAS=0 \
    -p rbac/V2_APIS_ENABLED=True \
    -p rbac/V2_READ_ONLY_API_MODE=False \
    -p rbac/V2_BOOTSTRAP_TENANT=True \
    -p rbac/REPLICATION_TO_RELATION_ENABLED=True \
    -p rbac/KAFKA_ENABLED=False \
    -p rbac/NOTIFICATONS_ENABLED=False \
    -p rbac/NOTIFICATIONS_RH_ENABLED=False \
    -p rbac/ROLE_CREATE_ALLOW_LIST="remediations,\
inventory,\
policies,\
advisor,\
vulnerability,\
compliance,\
automation-analytics,\
notifications,\
patch,\
integrations,\
ros,\
staleness,\
config-manager,\
idmsvc" \
    ${HBI_CUSTOM_IMAGE_PARAMETER} \
    -p rbac/V2_MIGRATION_APP_EXCLUDE_LIST="approval" \
    -p rbac/V2_MIGRATION_RESOURCE_EXCLUDE_LIST="empty-exclude-list" \
    -p host-inventory/KESSEL_TARGET_URL=kessel-inventory-api.$NAMESPACE.svc.cluster.local:9000 \
    --set-image-tag "${HBI_CUSTOM_IMAGE}=${HBI_CUSTOM_IMAGE_TAG}" \
    --set-image-tag quay.io/redhat-services-prod/rh-platform-experien-tenant/service-accounts="e187df2" \
    --set-image-tag quay.io/redhat-services-prod/insights-management-tenant/insights-host-inventory/host-inventory-frontend="${HOST_FRONTEND_GIT_COMMIT}" \
    --set-image-tag quay.io/cloudservices/unleash-proxy=latest \
    --set-image-tag quay.io/redhat-services-prod/hcc-platex-services/chrome-service=latest \
    --set-image-tag quay.io/redhat-services-prod/hcc-accessmanagement-tenant/insights-rbac=latest \
    --set-image-tag quay.io/redhat-services-prod/rh-platform-experien-tenant/insights-rbac-ui=latest \
    -p host-inventory/BYPASS_RBAC=false \
    -p host-inventory/BYPASS_KESSEL=false

  # Wait for deployment to complete - check for running pods
  echo "Waiting for deployments to be ready..."
  local max_wait=300
  local wait_time=0
  while [ $wait_time -lt $max_wait ]; do
    if oc get pods -l pod=host-inventory-service-reads --field-selector=status.phase==Running --no-headers 2>/dev/null | grep -q .; then
      echo "✓ Host Inventory pods are running"
      break
    fi
    echo "Waiting for pods to be ready... ($wait_time/$max_wait seconds)"
    sleep 5
    wait_time=$((wait_time + 5))
  done

  setup_kessel
  setup_rbac_consumer
}

# Setup Kessel Inventory and Relations
setup_kessel() {
  echo "Setting up Kessel inventory..."
  bonfire deploy kessel \
    -C kessel-inventory \
    -C kessel-relations \
    --set-image-tag quay.io/redhat-services-prod/project-kessel-tenant/kessel-inventory/inventory-api=latest \
    -p kessel-relations/SPICEDB_QUANTIZATION_INTERVAL=2.5s \
    -p kessel-relations/SPICEDB_QUANTIZATION_STALENESS_PERCENT=0
}

# Setup RBAC Consumer (Kafka consumer for relations replication)
setup_rbac_consumer() {
  echo "Setting up RBAC consumer..."
  NAMESPACE=$(oc project -q)

  bonfire process rbac \
    --source=appsre \
    --set-parameter rbac/RBAC_KAFKA_CONSUMER_TOPIC=outbox.event.relations-replication-event \
    --set-parameter rbac/RBAC_KAFKA_CONSUMER_GROUP_ID=connect-relations-sink-connector \
    -p rbac/MEMORY_LIMIT=512Mi \
    -p rbac/MEMORY_REQUEST=256Mi \
    -p rbac/RBAC_KAFKA_CONSUMER_REPLICAS=1 \
    -p rbac/V2_APIS_ENABLED=True \
    -p rbac/V2_READ_ONLY_API_MODE=False \
    -p rbac/V2_BOOTSTRAP_TENANT=True \
    -p rbac/REPLICATION_TO_RELATION_ENABLED=True \
    -p rbac/KAFKA_ENABLED=True \
    -p rbac/NOTIFICATONS_ENABLED=False \
    -p rbac/NOTIFICATIONS_RH_ENABLED=False \
    -p rbac/ROLE_CREATE_ALLOW_LIST="remediations,\
inventory,\
policies,\
advisor,\
vulnerability,\
compliance,\
automation-analytics,\
notifications,\
patch,\
integrations,\
ros,\
staleness,\
config-manager,\
idmsvc" \
    -p rbac/V2_MIGRATION_APP_EXCLUDE_LIST="approval" \
    -p rbac/V2_MIGRATION_RESOURCE_EXCLUDE_LIST="empty-exclude-list" \
    --namespace $NAMESPACE | oc apply -f - -n $NAMESPACE
}

# Apply SpiceDB schema to Kessel Relations
apply_schema() {
  local LOCAL_SCHEMA_FILE="$1"
  local SCHEMA_FILE="$SCRIPT_DIR/schema.zed"

  if [ -n "$LOCAL_SCHEMA_FILE" ]; then
    # Use local schema file
    if [ ! -f "$LOCAL_SCHEMA_FILE" ]; then
      echo "❌ ERROR: Local schema file not found: $LOCAL_SCHEMA_FILE"
      exit 1
    fi
    echo "Applying local SpiceDB schema from: $LOCAL_SCHEMA_FILE"
    cp "$LOCAL_SCHEMA_FILE" "$SCHEMA_FILE"
  else
    # Download latest schema from rbac-config (default behavior)
    echo "Applying latest SpiceDB schema from rbac-config"
    curl -H 'Cache-Control: no-cache' -o "$SCHEMA_FILE" \
      https://raw.githubusercontent.com/RedHatInsights/rbac-config/refs/heads/master/configs/stage/schemas/schema.zed
    if [ $? -ne 0 ]; then
      echo "❌ ERROR: Failed to download schema from rbac-config"
      exit 1
    fi
  fi

  # Delete the schema that was created already
  oc delete configmap spicedb-schema --ignore-not-found=true
  # Apply the schema
  oc create configmap spicedb-schema --from-file="$SCHEMA_FILE" -o yaml --dry-run=client | oc apply -f -
  # Ensure the pods are using the new schema
  oc rollout restart deployment/kessel-relations-api

  echo "✓ SpiceDB schema applied successfully"
}

# Setup Kessel Inventory Consumer
setup_kessel_inventory_consumer() {
  echo "Setting up Kessel Inventory Consumer..."
  bonfire deploy kessel \
    -C kessel-inventory-consumer \
    -p kessel-relations/SPICEDB_QUANTIZATION_INTERVAL=2.5s \
    -p kessel-relations/SPICEDB_QUANTIZATION_STALENESS_PERCENT=0
}

# Create HBI Kafka connectors for Kessel
create_hbi_connectors() {
  echo "Creating HBI debezium connectors..."
  NAMESPACE=env-$(oc project -q)

  # Migration connector
  oc process -f https://raw.githubusercontent.com/project-kessel/kessel-kafka-connect/refs/heads/main/deploy/sp-connectors/hbi-hosts-migration-connector.yml \
    -p KAFKA_CONNECT_INSTANCE="kessel-kafka-connect" \
    -p ENV_NAME="$NAMESPACE" \
    -p BOOTSTRAP_SERVERS="${NAMESPACE}-kafka-bootstrap:9092" \
    -p DB_SECRET_NAME="host-inventory-db" | oc apply -f -

  # Outbox connector
  oc process -f https://raw.githubusercontent.com/project-kessel/kessel-kafka-connect/refs/heads/main/deploy/sp-connectors/hbi-outbox-connector.yml \
    -p KAFKA_CONNECT_INSTANCE="kessel-kafka-connect" \
    -p DB_SECRET_NAME="host-inventory-db" | oc apply -f -

  echo "✓ Connectors created successfully"
}

# Add test users to Keycloak and RBAC
add_users() {
  echo "Importing users from rbac_users_data.json into Keycloak..."

  # Run the scripts from the deployer directory
  cd "$SCRIPT_DIR" || exit 1

  if [ -f "scripts/rbac_load_users.sh" ]; then
    bash scripts/rbac_load_users.sh
  else
    echo "⚠️ WARNING: scripts/rbac_load_users.sh not found, skipping user loading"
  fi

  echo "Seeding users to RBAC..."
  if [ -f "scripts/rbac_seed_users.sh" ]; then
    bash scripts/rbac_seed_users.sh
  else
    echo "⚠️ WARNING: scripts/rbac_seed_users.sh not found, skipping user seeding"
  fi
}

# Add demo hosts to HBI
add_hosts_to_hbi() {
  # Optional arguments: $1: org_id, $2: number of hosts to add
  ORG_ID=12345
  NUM_HOSTS=10

  if [ -n "$1" ]; then
    ORG_ID="$1"
    if [ -n "$2" ]; then
      NUM_HOSTS="$2"
    fi
  fi

  echo "Adding $NUM_HOSTS demo hosts to HBI (org_id: $ORG_ID)..."

  HOST_INVENTORY_READ_POD=$(oc get pods -l pod=host-inventory-service-reads --no-headers -o custom-columns=":metadata.name" --field-selector=status.phase==Running | head -1)
  HOST_INVENTORY_DB_POD=$(oc get pods -l app=host-inventory,service=db,sub=local_db --no-headers -o custom-columns=":metadata.name" --field-selector=status.phase==Running | head -1)
  HBI_BOOTSTRAP_SERVERS=$(oc get svc -o json | jq -r '.items[] | select(.metadata.name | test("^env-ephemeral.*-kafka-bootstrap")) | "\(.metadata.name).\(.metadata.namespace).svc"')

  BEFORE_COUNT=$(oc exec "$HOST_INVENTORY_DB_POD" -- /bin/bash -c "psql -d host-inventory -c \"select count(*) from hbi.hosts;\"" | head -3 | tail -1 | tr -d '[:space:]')
  TARGET_COUNT=$((BEFORE_COUNT + NUM_HOSTS))
  AFTER_COUNT=$BEFORE_COUNT

  echo "Sending ${NUM_HOSTS} hosts to HBI using kafka producer..."
  oc exec -c host-inventory-service-reads "$HOST_INVENTORY_READ_POD" -- /bin/bash -c \
    'NUM_HOSTS="$1" INVENTORY_HOST_ACCOUNT="$2" KAFKA_BOOTSTRAP_SERVERS="$3" python3 utils/kafka_producer.py' \
    _ "$NUM_HOSTS" "$ORG_ID" "$HBI_BOOTSTRAP_SERVERS"

  # Wait for hosts to sync to database
  local max_wait=60
  local wait_time=0
  until [ "$AFTER_COUNT" == "$TARGET_COUNT" ] || [ $wait_time -ge $max_wait ]; do
    echo "Waiting for ${NUM_HOSTS} hosts added via kafka to sync to the hbi db... [AFTER_COUNT: ${AFTER_COUNT}, TARGET_COUNT: ${TARGET_COUNT}]"
    sleep 2
    wait_time=$((wait_time + 2))
    AFTER_COUNT=$(oc exec "$HOST_INVENTORY_DB_POD" -- /bin/bash -c "psql -d host-inventory -c \"select count(*) from hbi.hosts;\"" | head -3 | tail -1 | tr -d '[:space:]')
  done

  AFTER_COUNT=$(oc exec "$HOST_INVENTORY_DB_POD" -- /bin/bash -c "psql -d host-inventory -c \"select count(*) from hbi.hosts;\"" | head -3 | tail -1 | tr -d '[:space:]')
  echo "✓ Done. [AFTER_COUNT: ${AFTER_COUNT}, TARGET_COUNT: ${TARGET_COUNT}]"
}

# Build and deploy unleash importer image with feature flags
deploy_unleash_importer_image() {
  echo "Deploying Kessel unleash importer image with feature flags..."

  # For now, just use the pre-built image
  UNLEASH_IMAGE=quay.io/mmclaugh/kessel-unleash-import
  UNLEASH_TAG=latest

  # Ensure clowdjobinvocations from a prior run are deleted, so that new bonfire run resets flags
  oc delete --ignore-not-found=true --wait=true clowdjobinvocation/swatch-unleash-import-1

  # Starts the job that runs the unleash feature flag import
  bonfire deploy rhsm --timeout=1800 --optional-deps-method none \
    --frontends false --no-remove-resources app:rhsm \
    -C rhsm \
    -p rhsm/SWATCH_UNLEASH_IMPORT_IMAGE="$UNLEASH_IMAGE" \
    -p rhsm/SWATCH_UNLEASH_IMPORT_IMAGE_TAG="$UNLEASH_TAG"
}

# Show bonfire namespace details
show_bonfire_namespace() {
  bonfire namespace describe
}

# Main deployment workflow (deploy_with_hbi_demo)
main() {
  echo "Starting full deployment with demo data..."

  deploy_unleash_importer_image
  deploy "$@"
  setup_kessel_inventory_consumer
  create_hbi_connectors

  # Start the outbox connector
  echo "Starting outbox connector..."
  oc patch kafkaconnector "hbi-outbox-connector" --type='merge' -p='{"spec":{"state":"running"}}' || echo "⚠️ Failed to start outbox connector"

  add_users
  add_hosts_to_hbi
  apply_schema "$4"
  show_bonfire_namespace

  echo "✓ Deployment with demo data completed successfully!"
}

# Run main if executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
