#!/bin/bash

set -x
cd "$APP_ROOT"

# pre-commit -- run using container image built for PR, mount workspace as volume so it has access to .git
echo '===================================='
echo '===      Running Pre-commit     ===='
echo '===================================='
# copy workspace directory and chown it to match podman user namespace
podman unshare rm -fr ./workspace_copy
rsync -Rr . ./workspace_copy
set +e
# run pre-commit with the copied workspace mounted as a volume
podman run -u 0:0 -t -v ./workspace_copy:/workspace:Z \
    --workdir /workspace --env HOME=/workspace "${IMAGE}:${IMAGE_TAG}" \
    "pipenv install --system --dev && pre-commit run --all-files --verbose"
TEST_RESULT=$?
set -e
# remove copy of the workspace
podman unshare rm -rf workspace_copy
if [[ "$TEST_RESULT" -ne 0 ]]; then
    echo '====================================='
    echo '====  ✖ ERROR: PRECOMMIT FAILED  ===='
    echo '====================================='
    exit 1
fi

# run unit tests in containers
DB_CONTAINER_NAME="inventory-db-${IMAGE_TAG}"
NETWORK="inventory-test-${IMAGE_TAG}"
POSTGRES_IMAGE="quay.io/cloudservices/postgresql-rds:cyndi-16"

function teardown_podman {
    podman rm -f "$DB_CONTAINER_ID" || true
    podman rm -f "$TEST_CONTAINER_ID" || true
    podman network rm "$NETWORK" || true
}

trap "teardown_podman" EXIT SIGINT SIGTERM

podman network create --driver bridge "$NETWORK"

echo "wal_level = logical" > 99-wal-level.conf

DB_CONTAINER_ID=$(podman run -d \
    --name "$DB_CONTAINER_NAME" \
    --network "$NETWORK" \
    -e POSTGRESQL_USER="inventory-test" \
    -e POSTGRESQL_PASSWORD="inventory-test" \
    -e POSTGRESQL_DATABASE="inventory-test" \
    -v ./99-wal-level.conf:/etc/postgresql/conf.d/99-wal-level.conf:Z \
    "$POSTGRES_IMAGE" || echo "0")

if [[ "$DB_CONTAINER_ID" == "0" ]]; then
    echo "Failed to start DB container"
    exit 1
fi

DB_IP_ADDR=$(podman inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$DB_CONTAINER_ID")

# --- ADDED: Wait for the database to be ready ---
echo "Waiting for PostgreSQL to become available at ${DB_IP_ADDR}:5432..."
MAX_ATTEMPTS=20
ATTEMPT=0
until podman exec "$DB_CONTAINER_ID" pg_isready -h "$DB_IP_ADDR" -p 5432 -U inventory-test || [ $ATTEMPT -ge $MAX_ATTEMPTS ]; do
    echo "PostgreSQL not ready yet, waiting 2 seconds (attempt $((ATTEMPT+1))/$MAX_ATTEMPTS)..."
    sleep 2
    ATTEMPT=$((ATTEMPT+1))
done

if [ $ATTEMPT -ge $MAX_ATTEMPTS ]; then
    echo "Error: PostgreSQL did not become ready after $MAX_ATTEMPTS attempts."
    exit 1
fi
echo "PostgreSQL is ready!"
# --- END ADDED ---


# Do tests
TEST_CONTAINER_ID=$(podman run -d \
    --network "$NETWORK" \
    -u 0:0 \
    -e INVENTORY_DB_NAME="inventory-test" \
    -e INVENTORY_DB_HOST="$DB_IP_ADDR" \
    -e INVENTORY_DB_PORT="5432" \
    -e INVENTORY_DB_USER="inventory-test" \
    -e INVENTORY_DB_PASS="inventory-test" \
    "${IMAGE}:${IMAGE_TAG}" \
    sleep infinity || echo "0")

if [[ "$TEST_CONTAINER_ID" == "0" ]]; then
    echo "Failed to start test container"
    exit 1
fi

ARTIFACTS_DIR="$WORKSPACE/artifacts"
mkdir -p "$ARTIFACTS_DIR"

# pip install
echo '===================================='
echo '=== Installing Pip Dependencies ===='
echo '===================================='
set +e
podman exec -u 0:0 "$TEST_CONTAINER_ID" pipenv install --system --dev
TEST_RESULT=$?
set -e
if [[ "$TEST_RESULT" -ne 0 ]]; then
    echo '====================================='
    echo '==== ✖ ERROR: PIP INSTALL FAILED ===='
    echo '====================================='
    exit 1
fi

# pytest
echo '===================================='
echo '====        Running Tests       ===='
echo '===================================='
set +e
podman exec -u 0:0  -e FLASK_APP=manage.py "$TEST_CONTAINER_ID" \
    bash -c 'flask db upgrade && pytest --cov=. --junitxml=junit-unittest.xml --cov-report html -sv'
TEST_RESULT=$?
set -e

# Copy junit report
podman cp "${TEST_CONTAINER_ID}:junit-unittest.xml" "${WORKSPACE}/artifacts"

if [[ "$TEST_RESULT" -ne 0 ]]; then
    echo '====================================='
    echo '====    ✖ ERROR: TEST FAILED     ===='
    echo '====================================='
    exit 1
fi

echo '====================================='
echo '====   ✔ SUCCESS: PASSED TESTS   ===='
echo '====================================='

teardown_podman
