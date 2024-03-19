#!/bin/bash

cd $APP_ROOT

# pre-commit -- run using container image built for PR, mount workspace as volume so it has access to .git
echo '===================================='
echo '===      Running Pre-commit     ===='
echo '===================================='
# copy workspace directory and chown it to match podman user namespace
podman unshare rm -fr ./workspace_copy
echo 'Running rsync ...'
rsync -Rr . ./workspace_copy
echo 'Running unshare ...'
podman unshare chown -R 1001:1001 workspace_copy
set +e
# run pre-commit with the copied workspace mounted as a volume
echo 'Running pre-commit...'
podman run -u 1001:1001 -t -v ./workspace_copy:/workspace:Z --workdir /workspace --env HOME=/workspace $IMAGE:$IMAGE_TAG pre-commit run --all-files
echo 'Done running pre-commit run!!!'
TEST_RESULT=$?
set -e
# remove copy of the workspace
echo 'Running podman unshare...'
podman unshare rm -rf workspace_copy
echo 'Running podman Done!!!'
if [ $TEST_RESULT -ne 0 ]; then
	echo '====================================='
	echo '====  ✖ ERROR: PRECOMMIT FAILED  ===='
	echo '====================================='
	exit 1
fi

# run unit tests in containers
DB_CONTAINER_NAME="inventory-db-${IMAGE_TAG}"
NETWORK="inventory-test-${IMAGE_TAG}"
POSTGRES_IMAGE="quay.io/cloudservices/postgresql-rds:cyndi-13-1"

function teardown_docker {
	docker rm -f $DB_CONTAINER_ID || true
	docker rm -f $TEST_CONTAINER_ID || true
	docker network rm $NETWORK || true
}

trap "teardown_docker" EXIT SIGINT SIGTERM

docker network create --driver bridge $NETWORK

DB_CONTAINER_ID=$(docker run -d \
	--name "${DB_CONTAINER_NAME}" \
	--network "${NETWORK}" \
	-e POSTGRESQL_USER="inventory-test" \
	-e POSTGRESQL_PASSWORD="inventory-test" \
	-e POSTGRESQL_DATABASE="inventory-test" \
	${POSTGRES_IMAGE} || echo "0")

if [[ "$DB_CONTAINER_ID" == "0" ]]; then
	echo "Failed to start DB container"
	exit 1
fi

DB_IP_ADDR=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $DB_CONTAINER_ID)

# Do tests
TEST_CONTAINER_ID=$(docker run -d \
	--network ${NETWORK} \
	-e INVENTORY_DB_NAME="inventory-test" \
	-e INVENTORY_DB_HOST="${DB_IP_ADDR}" \
	-e INVENTORY_DB_PORT="5432" \
	-e INVENTORY_DB_USER="inventory-test" \
	-e INVENTORY_DB_PASS="inventory-test" \
	$IMAGE:$IMAGE_TAG \
	/bin/bash -c 'sleep infinity' || echo "0")

if [[ "$TEST_CONTAINER_ID" == "0" ]]; then
	echo "Failed to start test container"
	exit 1
fi

ARTIFACTS_DIR="$WORKSPACE/artifacts"
mkdir -p $ARTIFACTS_DIR

# pip install
echo '===================================='
echo '=== Installing Pip Dependencies ===='
echo '===================================='
set +e
docker exec $TEST_CONTAINER_ID /bin/bash -c 'pipenv install --system --dev'
TEST_RESULT=$?
set -e
if [ $TEST_RESULT -ne 0 ]; then
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
docker exec $TEST_CONTAINER_ID /bin/bash -c 'FLASK_APP=manage.py flask db upgrade && pytest --cov=. --junitxml=junit-unittest.xml --cov-report html -sv'
TEST_RESULT=$?
set -e

# Copy junit report
docker cp $TEST_CONTAINER_ID:junit-unittest.xml $WORKSPACE/artifacts

if [ $TEST_RESULT -ne 0 ]; then
	echo '====================================='
	echo '====    ✖ ERROR: TEST FAILED     ===='
	echo '====================================='
	exit 1
fi

echo '====================================='
echo '====   ✔ SUCCESS: PASSED TESTS   ===='
echo '====================================='

teardown_docker
