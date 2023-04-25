#!/bin/bash

set -exv

IMAGE="quay.io/cloudservices/insights-inventory"
IMAGE_TAG=$(git rev-parse --short=7 HEAD)
SMOKE_TEST_TAG="latest"

if [[ -z "$QUAY_USER" || -z "$QUAY_TOKEN" ]]; then
    echo "QUAY_USER and QUAY_TOKEN must be set"
    exit 1
fi


AUTH_CONF_DIR="$(pwd)/.podman"
mkdir -p $AUTH_CONF_DIR
export REGISTRY_AUTH_FILE="$AUTH_CONF_DIR/auth.json"

podman login -u="$QUAY_USER" -p="$QUAY_TOKEN" quay.io
podman login -u="$RH_REGISTRY_USER" -p="$RH_REGISTRY_TOKEN" registry.redhat.io
podman build --pull=true -f Dockerfile -t "${IMAGE}:${IMAGE_TAG}" .
podman push "${IMAGE}:${IMAGE_TAG}"

if [[ $GIT_BRANCH == *"security-compliance"*]]; then
    podman tag "${IMAGE}:${IMAGE_TAG}" "${IMAGE}:security-compliance"
    podman push "${IMAGE}:security-compliance"
else
    # To enable backwards compatibility with ci, qa, and smoke, always push latest and qa tags
    podman tag "${IMAGE}:${IMAGE_TAG}" "${IMAGE}:latest"
    podman push "${IMAGE}:latest"
    podman tag "${IMAGE}:${IMAGE_TAG}" "${IMAGE}:qa"
    podman push "${IMAGE}:qa"
fi
