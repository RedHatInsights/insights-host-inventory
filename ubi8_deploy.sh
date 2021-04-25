#!/bin/bash

set -exv

IMAGE="insights-inventory"
IMAGE_TAG=$(git rev-parse --short=7 HEAD)

docker build -f ubi8.dockerfile -t "${IMAGE}:${IMAGE_TAG}" .

# SMOKE_TEST_TAG="latest"

# if [[ -z "$QUAY_USER" || -z "$QUAY_TOKEN" ]]; then
#     echo "QUAY_USER and QUAY_TOKEN must be set"
#     exit 1
# fi

# DOCKER_CONF="$PWD/.docker"
# mkdir -p "$DOCKER_CONF"
# docker --config="$DOCKER_CONF" login -u="$QUAY_USER" -p="$QUAY_TOKEN" quay.io
# docker --config="$DOCKER_CONF" login -u="$RH_REGISTRY_USER" -p="$RH_REGISTRY_TOKEN" registry.redhat.io
# docker --config="$DOCKER_CONF" build -f dev.dockerfile -t "${IMAGE}:${IMAGE_TAG}" .
# docker --config="$DOCKER_CONF" push "${IMAGE}:${IMAGE_TAG}"

# # To enable backwards compatibility with ci, qa, and smoke, always push latest and qa tags
# docker --config="$DOCKER_CONF" tag "${IMAGE}:${IMAGE_TAG}" "${IMAGE}:latest"
# docker --config="$DOCKER_CONF" push "${IMAGE}:latest"
# docker --config="$DOCKER_CONF" tag "${IMAGE}:${IMAGE_TAG}" "${IMAGE}:qa"
# docker --config="$DOCKER_CONF" push "${IMAGE}:qa"
