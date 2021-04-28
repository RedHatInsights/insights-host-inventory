#!/bin/bash

set -exv

IMAGE="quay.io/thearifismail/insights-inventory"
IMAGE_TAG="arifstest"

if [[ -z "$QUAY_USER" || -z "$QUAY_TOKEN" ]]; then
    echo "QUAY_USER and QUAY_TOKEN must be set"
    exit 1
fi

DOCKER_CONF="$PWD/.docker"
mkdir -p "$DOCKER_CONF"
podman --config="$DOCKER_CONF" login -u="$QUAY_USER" -p="$QUAY_TOKEN" quay.io
podman --config="$DOCKER_CONF" login -u="$RH_REGISTRY_USER" -p="$RH_REGISTRY_TOKEN" registry.redhat.io
podman --config="$DOCKER_CONF" build -f rhel8.dockerfile -t "${IMAGE}:${IMAGE_TAG}" .
podman --config="$DOCKER_CONF" push "${IMAGE}:${IMAGE_TAG}"
