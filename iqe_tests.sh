#!/bin/bash

# --------------------------------------------
# Pre-commit checks
# --------------------------------------------
export APP_NAME="host-inventory"  # name of app-sre "application" folder this component lives in
export IMAGE="quay.io/cloudservices/insights-inventory"
export LC_ALL=en_US.utf-8
export LANG=en_US.utf-8
export APP_ROOT=$(pwd)
export WORKSPACE=${WORKSPACE:-$APP_ROOT}  # if running in jenkins, use the build's workspace
export IMAGE_TAG=$(git rev-parse --short=7 HEAD)
export GIT_COMMIT=$(git rev-parse HEAD)
export REF_ENV="insights-stage"

# --------------------------------------------
# Options that must be configured by app owner
# --------------------------------------------
COMPONENT_NAME="host-inventory"  # name of app-sre "resourceTemplate" in deploy.yaml for this component

IQE_PLUGINS="host_inventory"
IQE_MARKER_EXPRESSION="not resilience and not cert_auth and not rbac_dependent"
IQE_FILTER_EXPRESSION=""
IQE_CJI_TIMEOUT="3h"

# ---------------------------
# We'll take it from here ...
# ---------------------------

# Get bonfire helper scripts
CICD_URL=https://raw.githubusercontent.com/RedHatInsights/bonfire/master/cicd
curl -s $CICD_URL/bootstrap.sh > .cicd_bootstrap.sh && source .cicd_bootstrap.sh

function check_image () {
  for i in {1..60}
  do
    echo "Try number $i"
    echo "Checking if image '$IMAGE:$IMAGE_TAG' already exists in quay.io..."
    QUAY_REPO=${IMAGE#"quay.io/"}
    RESPONSE=$( \
        curl -Ls -H "Authorization: Bearer $QUAY_API_TOKEN" \
        "https://quay.io/api/v1/repository/$QUAY_REPO/tag/?specificTag=$IMAGE_TAG" \
    )
    # find all non-expired tags
    VALID_TAGS_LENGTH=$(echo $RESPONSE | jq '[ .tags[] ] | length')
    if [[ "$VALID_TAGS_LENGTH" -gt 0 ]]; then
      echo "Found image '$IMAGE:$IMAGE_TAG'"
      return 0
    fi
    echo "Image '$IMAGE:$IMAGE_TAG' not found, retrying in 30 seconds"
    sleep 30
  done
  return 1
}

check_image
if [[ $? -ne 0 ]]
then
  echo "Image '$IMAGE:$IMAGE_TAG' not found in quay, exiting script"
  exit 1
fi

# Deploy ephemeral env and run IQE tests
source $CICD_ROOT/deploy_ephemeral_env.sh
bonfire namespace extend $NAMESPACE --duration 3h

# source $CICD_ROOT/cji_smoke_test.sh
set -e

: "${IQE_MARKER_EXPRESSION:='""'}"
: "${IQE_FILTER_EXPRESSION:='""'}"
: "${IQE_IMAGE_TAG:='""'}"
: "${IQE_REQUIREMENTS:='""'}"
: "${IQE_REQUIREMENTS_PRIORITY:='""'}"
: "${IQE_TEST_IMPORTANCE:='""'}"
: "${IQE_PLUGINS:='""'}"
: "${IQE_ENV:=clowder_smoke}"
: "${IQE_SELENIUM:=false}"


# minio client is used to fetch test artifacts from minio in the ephemeral ns
MC_IMAGE="quay.io/cloudservices/mc:latest"
echo "Running: docker pull ${MC_IMAGE}"
docker pull ${MC_IMAGE}

CJI_NAME="$COMPONENT_NAME"

# Invoke the CJI using the options set via env vars
set -x
POD=$(
    bonfire deploy-iqe-cji $COMPONENT_NAME \
    --marker "$IQE_MARKER_EXPRESSION" \
    --filter "$IQE_FILTER_EXPRESSION" \
    --image-tag "${IQE_IMAGE_TAG}" \
    --requirements "$IQE_REQUIREMENTS" \
    --requirements-priority "$IQE_REQUIREMENTS_PRIORITY" \
    --test-importance "$IQE_TEST_IMPORTANCE" \
    --plugins "$IQE_PLUGINS" \
    --env "$IQE_ENV" \
    --cji-name $CJI_NAME \
    --namespace $NAMESPACE)
set +x

# Pipe logs to background to keep them rolling in jenkins
CONTAINER=$(oc_wrapper get pod $POD -n $NAMESPACE -o jsonpath="{.status.containerStatuses[0].name}")
oc_wrapper logs -n $NAMESPACE $POD -c $CONTAINER -f &
LOGS_PID=$!
sleep 3600
kill $LOGS_PID
oc_wrapper logs -n $NAMESPACE $POD -c $CONTAINER -f &

# Wait for the job to Complete or Fail before we try to grab artifacts
# condition=complete does trigger when the job fails
set -x
oc_wrapper wait --timeout=$IQE_CJI_TIMEOUT --for=condition=JobInvocationComplete -n $NAMESPACE cji/$CJI_NAME
set +x

# Set up port-forward for minio
set -x
LOCAL_SVC_PORT=$(python -c 'import socket; s=socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()')
oc_wrapper port-forward svc/env-$NAMESPACE-minio $LOCAL_SVC_PORT:9000 -n $NAMESPACE &
set +x
sleep 5
PORT_FORWARD_PID=$!

# Get the secret from the env
set -x
oc_wrapper get secret env-$NAMESPACE-minio -o json -n $NAMESPACE | jq -r '.data' > minio-creds.json
set +x

# Grab the needed creds from the secret
export MINIO_ACCESS=$(jq -r .accessKey < minio-creds.json | base64 -d)
export MINIO_SECRET_KEY=$(jq -r .secretKey < minio-creds.json | base64 -d)
export MINIO_HOST=localhost
export MINIO_PORT=$LOCAL_SVC_PORT

if [ -z "$MINIO_ACCESS" ] || [ -z "$MINIO_SECRET_KEY" ] || [ -z "$MINIO_PORT" ]; then
    echo "Failed to fetch minio connection info when running 'oc' commands"
    exit 1
fi

# Setup the minio client to auth to the local eph minio in the ns
echo "Fetching artifacts from minio..."

CONTAINER_NAME="mc-${JOB_NAME}-${BUILD_NUMBER}"
BUCKET_NAME="${POD}-artifacts"
CMD="mkdir -p /artifacts &&
mc --no-color --quiet alias set minio http://${MINIO_HOST}:${MINIO_PORT} ${MINIO_ACCESS} ${MINIO_SECRET_KEY} &&
mc --no-color --quiet mirror --overwrite minio/${BUCKET_NAME} /artifacts/
"

run_mc () {
    echo "running: docker run -t --net=host --name=$CONTAINER_NAME --entrypoint=\"/bin/sh\" $MC_IMAGE -c \"$CMD\""
    set +e
    docker run -t --net=host --name=$CONTAINER_NAME --entrypoint="/bin/sh" $MC_IMAGE -c "$CMD"
    RET_CODE=$?
    docker cp $CONTAINER_NAME:/artifacts/. $ARTIFACTS_DIR
    docker rm $CONTAINER_NAME
    set -e
    return $RET_CODE
}

# Add retry logic for intermittent minio connection failures
MINIO_SUCCESS=false
for i in $(seq 1 5); do
    if run_mc; then
        MINIO_SUCCESS=true
        break
    else
        if [ "$i" -lt "5" ]; then
            echo "WARNING: minio artifact copy failed, retrying in 5sec..."
            sleep 5
        fi
    fi
done

if [ "$MINIO_SUCCESS" = false ]; then
    echo "ERROR: minio artifact copy failed"
    exit 1
fi

echo "copied artifacts from iqe pod: "
ls -l $ARTIFACTS_DIR

source $CICD_ROOT/post_test_results.sh
