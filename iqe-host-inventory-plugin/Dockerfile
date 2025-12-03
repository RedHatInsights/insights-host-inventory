FROM quay.io/cloudservices/iqe-core:latest

ARG PLUGIN_NAME

USER 0

RUN iqe plugin install --debug ${PLUGIN_NAME} ${PLUGIN_NAME}-frontend && \
    rm -rf ${IQE_VENV}/.cache/pip && \
    chmod -R g+rwX ${IQE_VENV}

USER 1001
