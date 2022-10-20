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
IQE_MARKER_EXPRESSION="not resilience and should_fail"
IQE_FILTER_EXPRESSION=""
IQE_CJI_TIMEOUT="3h"

# ---------------------------
# We'll take it from here ...
# ---------------------------

# Get bonfire helper scripts
CICD_URL=https://raw.githubusercontent.com/RedHatInsights/bonfire/master/cicd
curl -s $CICD_URL/bootstrap.sh > .cicd_bootstrap.sh && source .cicd_bootstrap.sh

function check_image () {
  for i in {1..30}
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

# Deploy ephemeral env and run base IQE tests
source $CICD_ROOT/deploy_ephemeral_env.sh
bonfire namespace extend $NAMESPACE --duration 3h
source $CICD_ROOT/cji_smoke_test.sh

# Run resilience (graceful shutdown) tests
IQE_MARKER_EXPRESSION="resilience and not should_fail"
oc_wrapper delete cji $CJI_NAME -n $NAMESPACE
source $CICD_ROOT/cji_smoke_test.sh

source $CICD_ROOT/post_test_results.sh