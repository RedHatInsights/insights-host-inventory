#!/bin/bash

# This script runs CJI smoke tests with the local IQE plugin
# It combines the deployment, local plugin installation, and test execution

set -e

echo "========================================================"
echo "Running CJI tests with local IQE plugin"
echo "========================================================"

# Check if we have the namespace
if [ -z "$NAMESPACE" ]; then
    echo "ERROR: NAMESPACE variable is not set"
    exit 1
fi

# Set default values for IQE test configuration
IQE_MARKER_EXPRESSION="${IQE_MARKER_EXPRESSION:-backend and smoke}"
IQE_FILTER_EXPRESSION="${IQE_FILTER_EXPRESSION:-}"
IQE_ENV="${IQE_ENV:-clowder_smoke}"
IQE_PLUGINS="${IQE_PLUGINS:-host_inventory}"
IQE_CJI_TIMEOUT="${IQE_CJI_TIMEOUT:-30m}"

echo "Deploying CJI pod with --debug-pod option..."
# Deploy the CJI pod with --debug-pod to prevent auto-execution
POD=$(bonfire deploy-iqe-cji $COMPONENT_NAME \
    --debug-pod \
    --marker "$IQE_MARKER_EXPRESSION" \
    ${IQE_FILTER_EXPRESSION:+--filter "$IQE_FILTER_EXPRESSION"} \
    --env "$IQE_ENV" \
    --cji-name "iqe-local-${IMAGE_TAG}" \
    ${IQE_PLUGINS:+--plugins "$IQE_PLUGINS"} \
    ${IQE_IMAGE_TAG:+--image-tag "$IQE_IMAGE_TAG"} \
    -n "$NAMESPACE")

if [ -z "$POD" ]; then
    echo "ERROR: Failed to deploy the IQE CJI pod"
    exit 1
fi

echo "CJI Pod: $POD"
export IQE_POD_NAME="$POD"

# Wait for the pod to be ready
echo "Waiting for pod to be ready..."
oc wait --for=condition=Ready pod/$POD -n $NAMESPACE --timeout=300s || {
    echo "WARNING: Pod did not become ready in time, but continuing..."
}

echo "Installing setuptools_scm..."
oc exec -n $NAMESPACE $POD -- pip install -i https://pypi.python.org/simple setuptools_scm || {
    echo "WARNING: Failed to install setuptools_scm, continuing anyway..."
}

echo "Copying local IQE plugin (Source: $IQE_LOCAL_PLUGIN_PATH) to pod..."

# Copy the local plugin directory to the pod (relative path, as per IQE README)
oc cp -n $NAMESPACE "$IQE_LOCAL_PLUGIN_PATH" "$POD:iqe-host-inventory-plugin"

echo "Installing local IQE plugin in the pod..."
oc exec -n $NAMESPACE $POD -- bash -c "cd iqe-host-inventory-plugin && pip install -i https://pypi.python.org/simple -e ."

echo "Verifying plugin installation..."
oc exec -n $NAMESPACE $POD -- iqe plugin list | grep -i host_inventory

echo "========================================================"
echo "Running tests with local plugin..."
echo "========================================================"

# Build the IQE test command
IQE_CMD="iqe tests plugin host_inventory -vvv -m \"$IQE_MARKER_EXPRESSION\""
if [ -n "$IQE_FILTER_EXPRESSION" ]; then
    IQE_CMD="$IQE_CMD -k \"$IQE_FILTER_EXPRESSION\""
fi
IQE_CMD="$IQE_CMD --junitxml=/iqe_venv/iqe-junit-report.xml -o junit_suite_name=iqe"

echo "Running: $IQE_CMD"

# Run tests in the pod and stream the output
oc exec -n $NAMESPACE $POD -- bash -c "$IQE_CMD" &
TEST_PID=$!

# Also tail the logs in parallel
oc logs -f $POD -n $NAMESPACE &
LOG_PID=$!

# Wait for tests to complete
# Use conditional to capture exit code and prevent ERR trap from firing
wait $TEST_PID && TEST_EXIT_CODE=0 || TEST_EXIT_CODE=$?

# Stop tailing logs
kill $LOG_PID 2>/dev/null || true

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "========================================================"
    echo "Tests PASSED"
    echo "========================================================"
else
    echo "========================================================"
    echo "Tests FAILED with exit code: $TEST_EXIT_CODE"
    echo "========================================================"
fi

# Copy test artifacts from the pod
echo "Copying test artifacts..."
ARTIFACTS_DIR="${ARTIFACTS_DIR:-$WORKSPACE/artifacts}"
mkdir -p "$ARTIFACTS_DIR"

oc cp -n $NAMESPACE "$POD:/iqe_venv/iqe-junit-report.xml" "$ARTIFACTS_DIR/junit-iqe.xml" 2>/dev/null || {
    echo "WARNING: Could not copy junit report from pod"
}

echo "Test artifacts saved to: $ARTIFACTS_DIR"
