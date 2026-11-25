# Copyright iqe-core authors
# SPDX-License-Identifier: MIT
#
# Universal IQE image build.
# Identical file in iqe-core and every plugin repo.
#
# Consumes the shared OS foundation (UBI9-minimal, Python, uv, Red Hat
# certs, env vars) built from iqe-core's Dockerfile.base and published as
# iqe-base (IQE-4191). The digest is bumped by Renovate.
# FROM quay.io/redhat-services-prod/insights-management-tenant/iqe-core/iqe-base@sha256:5b79b65196483a4b1d3ebd2da74553232a4f70741c4d50b8b1f5c7b892358d54
FROM quay.io/redhat-services-prod/insights-management-tenant/iqe-core/iqe-base:latest

# Scoped oc CLI exception (IQE-4496): iqe_host_inventory's host-reaper,
# graceful-shutdown, and notification tests/utils (ocdeployer.utils.oc)
# invoke the oc binary directly at test runtime; iqe-base no longer
# bundles it (IQE-4497). Pinned to the openshift-client release iqe-base
# used to install.
ARG OC_VERSION="5.0.1"
ARG OC_SHA256="9be0ad418ece7aa19fbb99a9259a800c4d234d08766c9b782eb321659b9c59e8"
# hadolint ignore=DL3003,DL4006,SC2086
RUN curl -sSfL "https://mirror.openshift.com/pub/openshift-v5/x86_64/clients/ocp/${OC_VERSION}/openshift-client-linux.tar.gz" \
        -o /tmp/oc.tar.gz && \
    echo "${OC_SHA256}  /tmp/oc.tar.gz" | sha256sum -c - && \
    tar -xzf /tmp/oc.tar.gz -C /usr/bin oc && \
    rm -f /tmp/oc.tar.gz


# === Layer 1: Dependencies from lockfile (changes only when uv.lock changes) ===
WORKDIR /build
COPY uv.lock pyproject.toml /build/
# hadolint ignore=SC2086 # allow variable expansion in shell code
RUN --mount=type=cache,target=/iqe_uv_cache \
    uv venv --clear && \
    uv sync --frozen --no-dev --no-install-project

# === Layer 2: Project wheel + dumb-init ===
COPY uv.lock /iqe_venv/
RUN --mount=type=cache,target=/iqe_uv_cache \
    --mount=type=bind,target=/tmp/src \
    uv build --wheel --out-dir /tmp/dist /tmp/src && \
    uv pip install /tmp/dist/*.whl dumb-init

RUN mkdir -p "${UV_CACHE_DIR}" && \
    chgrp -R 0 "${IQE_VENV}" "${UV_CACHE_DIR}" && \
    chmod -R g+rwX "${IQE_VENV}" "${UV_CACHE_DIR}"

USER 1001
WORKDIR ${IQE_VENV}
ENTRYPOINT ["/iqe_venv/bin/dumb-init", "/iqe_venv/bin/iqe_container_entrypoint"]
