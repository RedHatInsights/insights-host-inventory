#!/bin/bash

set -exv

IMAGE="quay.io/cloudservices/insights-inventory"
IMAGE_TAG=$(git rev-parse --short=7 HEAD)
SMOKE_TEST_TAG="latest"
SECURITY_COMPLIANCE_TAG="sc-$(date +%Y%m%d)-$(git rev-parse --short=7 HEAD)"

if [[ -z "$QUAY_USER" || -z "$QUAY_TOKEN" ]]; then
    echo "QUAY_USER and QUAY_TOKEN must be set"
    exit 1
fi

# Create tmp dir to store data in during job run (do NOT store in $WORKSPACE)
export TMP_JOB_DIR=$(mktemp -d -p "$HOME" -t "jenkins-${JOB_NAME}-${BUILD_NUMBER}-XXXXXX")
echo "job tmp dir location: $TMP_JOB_DIR"

function job_cleanup() {
    echo "cleaning up job tmp dir: $TMP_JOB_DIR"
    rm -fr $TMP_JOB_DIR
}

trap job_cleanup EXIT ERR SIGINT SIGTERM

# Set up podman cfg
AUTH_CONF_DIR="${TMP_JOB_DIR}/.podman"
mkdir -p $AUTH_CONF_DIR
export REGISTRY_AUTH_FILE="$AUTH_CONF_DIR/auth.json"


podman login -u="$QUAY_USER" -p="$QUAY_TOKEN" quay.io
podman login -u="$RH_REGISTRY_USER" -p="$RH_REGISTRY_TOKEN" registry.redhat.io

# Build main image
podman build --pull=true -f Dockerfile -t "${IMAGE}:${IMAGE_TAG}" .

if [[ "$GIT_BRANCH" == "origin/security-compliance" ]]; then
    podman tag "${IMAGE}:${IMAGE_TAG}" "${IMAGE}:${SECURITY_COMPLIANCE_TAG}"
    podman push "${IMAGE}:${SECURITY_COMPLIANCE_TAG}"
else
    # push main image
    podman push "${IMAGE}:${IMAGE_TAG}"

    # To enable backwards compatibility with ci, qa, and smoke, always push latest and qa tags
    podman tag "${IMAGE}:${IMAGE_TAG}" "${IMAGE}:latest"
    podman push "${IMAGE}:latest"
    podman tag "${IMAGE}:${IMAGE_TAG}" "${IMAGE}:qa"
    podman push "${IMAGE}:qa"
fi
