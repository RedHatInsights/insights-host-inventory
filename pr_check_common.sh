#!/bin/bash

export APP_NAME="host-inventory"  # name of app-sre "application" folder this component lives in
export IMAGE="quay.io/cloudservices/insights-inventory"
export LC_ALL=en_US.utf-8
export LANG=en_US.utf-8
export APP_ROOT=$(pwd)
export WORKSPACE=${WORKSPACE:-$APP_ROOT}  # if running in jenkins, use the build's workspace
export IMAGE_TAG=$(git rev-parse --short=7 HEAD)
export GIT_COMMIT=$(git rev-parse HEAD)
export QUAY_EXPIRE_TIME="40d"
cat /etc/redhat-release

export COMPONENT_NAME="host-inventory"  # name of app-sre "resourceTemplate" in deploy.yaml for this component
export COMPONENTS_W_RESOURCES="host-inventory"  # this gives us resources defined in app-sre, otherwise we run low on memory
export IQE_PLUGINS="host_inventory"

# Get bonfire helper scripts
CICD_URL=https://raw.githubusercontent.com/RedHatInsights/bonfire/master/cicd
curl -s $CICD_URL/bootstrap.sh > .cicd_bootstrap.sh && source .cicd_bootstrap.sh

# Function for waiting until the PR image is built
function check_image () {
  for i in {1..60}
  do
    echo "Attempt number $i"
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
