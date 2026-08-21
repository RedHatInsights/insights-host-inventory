# Copyright iqe-core authors
# SPDX-License-Identifier: MIT
#
# Universal IQE image build.
# Identical file in iqe-core and every plugin repo.
#
# Consumes the shared OS foundation (UBI9-minimal, Python, uv, oc, Red Hat
# certs, env vars) built from iqe-core's Dockerfile.base and published as
# iqe-base (IQE-4191). The digest is bumped by Renovate.
FROM quay.io/redhat-user-workloads/insights-management-tenant/iqe-core/iqe-base@sha256:f36d8ef8a28d406c149cb89e426cc2b3f6b21cd02aaf54e242d71767732b33a7

# === Layer 1: Dependencies from lockfile (changes only when uv.lock changes) ===
# iqe-core passes --build-arg UV_SYNC_ARGS="--group image-plugins" to pull
# bundled plugins; plugin repos use the default (empty).
ARG UV_SYNC_ARGS=""
WORKDIR /build
COPY uv.lock pyproject.toml /build/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv --clear "$UV_PROJECT_ENVIRONMENT" && \
    uv sync --frozen --no-install-project ${UV_SYNC_ARGS}

# === Layer 2: Project wheel + dumb-init ===
COPY uv.lock /iqe_venv/

# In a normal clone (CI), setuptools-scm resolves the version from .git.
# In a worktree, .git is a file with a host-absolute gitdir path that won't
# resolve inside the container — pass a PEP 440 version from the host:
#   --build-arg SETUPTOOLS_SCM_PRETEND_VERSION="$(uvx setuptools-scm)"
ARG SETUPTOOLS_SCM_PRETEND_VERSION=""
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,target=/tmp/src \
    if [ -n "${SETUPTOOLS_SCM_PRETEND_VERSION}" ]; then \
      export SETUPTOOLS_SCM_PRETEND_VERSION="${SETUPTOOLS_SCM_PRETEND_VERSION}"; \
    fi && \
    uv build --wheel --out-dir /tmp/dist /tmp/src && \
    uv pip install /tmp/dist/*.whl dumb-init

# hadolint ignore=SC2086
RUN chgrp -R 0 ${IQE_VENV} && \
    chmod -R g+rwX ${IQE_VENV}

USER 1001
WORKDIR ${IQE_VENV}
ENTRYPOINT ["/iqe_venv/bin/dumb-init", "/iqe_venv/bin/iqe_container_entrypoint"]
