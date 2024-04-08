#!/bin/bash

set -exv

IMAGE="quay.io/cloudservices/insights-inventory"
PG_REPACK_IMAGE="quay.io/cloudservices/insights-inventory-pg-repack"
IMAGE_TAG=$(git rev-parse --short=7 HEAD)
SMOKE_TEST_TAG="latest"
SECURITY_COMPLIANCE_TAG="sc-$(date +%Y%m%d)-$(git rev-parse --short=7 HEAD)"

if [[ -z "$QUAY_USER" || -z "$QUAY_TOKEN" ]]; then
    echo "QUAY_USER and QUAY_TOKEN must be set"
    exit 1
fi


AUTH_CONF_DIR="$(pwd)/.podman"
mkdir -p $AUTH_CONF_DIR
export REGISTRY_AUTH_FILE="$AUTH_CONF_DIR/auth.json"

podman login -u="$QUAY_USER" -p="$QUAY_TOKEN" quay.io
podman login -u="$RH_REGISTRY_USER" -p="$RH_REGISTRY_TOKEN" registry.redhat.io

# Build and push main image
podman build --pull=true -f Dockerfile -t "${IMAGE}:${IMAGE_TAG}" .
podman push "${IMAGE}:${IMAGE_TAG}"

# Build and push pg_repack image
podman build --pull=true -f pg_repack.dockerfile -t "${PG_REPACK_IMAGE}:${IMAGE_TAG}" .
podman push "${PG_REPACK_IMAGE}:${IMAGE_TAG}"

if [[ $GIT_BRANCH == *"security-compliance"* ]]; then
    podman tag "${IMAGE}:${IMAGE_TAG}" "${IMAGE}:${SECURITY_COMPLIANCE_TAG}"
    podman push "${IMAGE}:${SECURITY_COMPLIANCE_TAG}"
else
    # To enable backwards compatibility with ci, qa, and smoke, always push latest and qa tags
    podman tag "${IMAGE}:${IMAGE_TAG}" "${IMAGE}:latest"
    podman push "${IMAGE}:latest"
    podman tag "${IMAGE}:${IMAGE_TAG}" "${IMAGE}:qa"
    podman push "${IMAGE}:qa"

    # Same for the pg_repack image
    podman tag "${PG_REPACK_IMAGE}:${IMAGE_TAG}" "${PG_REPACK_IMAGE}:latest"
    podman push "${PG_REPACK_IMAGE}:latest"
    podman tag "${PG_REPACK_IMAGE}:${IMAGE_TAG}" "${PG_REPACK_IMAGE}:qa"
    podman push "${PG_REPACK_IMAGE}:qa"
fi
