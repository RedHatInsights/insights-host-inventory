# IQE Testing Scripts

Reusable scripts for deploying and managing IQE test pods in ephemeral environments.

## Overview

These scripts automate IQE test execution in ephemeral namespaces:

1. **hbi-deploy-iqe-pod.sh** - Deploy IQE test pod using ClowdJobInvocation
2. **view-iqe-logs.sh** - View logs from IQE test pods

## Quick Start

### Run Smoke Tests

```bash
# Deploy IQE pod with smoke tests
POD=$(.claude/scripts/hbi-deploy-iqe-pod.sh)

# View live logs
.claude/scripts/view-iqe-logs.sh --follow
```

### Run Custom Tests

```bash
# Deploy with custom markers
POD=$(.claude/scripts/hbi-deploy-iqe-pod.sh ephemeral-abc123 "backend and groups")

# View logs later
.claude/scripts/view-iqe-logs.sh $POD
```

## Scripts

### hbi-deploy-iqe-pod.sh

Deploy an IQE test pod to run tests in an ephemeral environment.

**Usage:**
```bash
./hbi-deploy-iqe-pod.sh [NAMESPACE] [TEST_MARKERS]
```

**Arguments:**
- `NAMESPACE` - Ephemeral namespace (optional, auto-detected)
- `TEST_MARKERS` - Pytest markers (optional, defaults to smoke tests)

**Returns:**
- Outputs pod name to stdout (for script usage)
- Logs to stderr
- Exit code 0 on success, non-zero on failure

**Examples:**
```bash
# Auto-detect namespace, run smoke tests
./hbi-deploy-iqe-pod.sh

# Specific namespace, smoke tests
./hbi-deploy-iqe-pod.sh ephemeral-abc123

# Custom test markers
./hbi-deploy-iqe-pod.sh ephemeral-abc123 "backend and not resilience"

# Capture pod name for later use
POD=$(./hbi-deploy-iqe-pod.sh)
echo "Pod: $POD"
```

**Default Test Markers:**
```
backend and smoke and not resilience and not cert_auth and not rbac_dependent
```

This skips:
- `resilience` - Graceful shutdown tests (destructive)
- `cert_auth` - Certificate auth tests (require 3scale gateway)
- `rbac_dependent` - RBAC tests (requires BYPASS_RBAC=false)

### view-iqe-logs.sh

View logs from IQE test pods with auto-detection.

**Usage:**
```bash
./view-iqe-logs.sh [POD_NAME] [NAMESPACE] [--follow]
```

**Arguments:**
- `POD_NAME` - IQE pod name (optional, auto-detected)
- `NAMESPACE` - Ephemeral namespace (optional, auto-detected)
- `--follow` - Stream logs in real-time (optional)

**Examples:**
```bash
# Auto-detect everything, show logs
./view-iqe-logs.sh

# Auto-detect and stream live
./view-iqe-logs.sh --follow

# Specific pod
./view-iqe-logs.sh iqe-abc123-xyz

# Specific pod and namespace
./view-iqe-logs.sh iqe-abc123-xyz ephemeral-test

# Specific pod, streaming
./view-iqe-logs.sh iqe-abc123-xyz --follow
```

## Common Test Markers

**Smoke Tests (~81 tests, ~15-25 minutes):**
```bash
POD=$(./hbi-deploy-iqe-pod.sh "" "backend and smoke and not resilience and not cert_auth and not rbac_dependent")
```

**Full Backend Tests (~1+ hour):**
```bash
POD=$(./hbi-deploy-iqe-pod.sh "" "backend and not resilience and not cert_auth and not rbac_dependent")
```

**Group Tests Only:**
```bash
POD=$(./hbi-deploy-iqe-pod.sh "" "backend and groups and not rbac_dependent")
```

**Single Test:**
```bash
POD=$(./hbi-deploy-iqe-pod.sh "" "test_create_host")
```

## Automation Examples

### Run tests and wait for completion

```bash
#!/bin/bash
NAMESPACE=ephemeral-abc123

# Deploy IQE pod
POD=$(.claude/scripts/hbi-deploy-iqe-pod.sh $NAMESPACE "smoke")

# Stream logs in background
.claude/scripts/view-iqe-logs.sh $POD $NAMESPACE > iqe-logs.txt &

# Wait for pod to complete
oc wait --for=condition=Complete job -l job-name=$POD -n $NAMESPACE --timeout=30m

# Check results
if oc logs -n $NAMESPACE $POD | tail -1 | grep -q "failed"; then
    echo "Tests failed!"
    exit 1
else
    echo "Tests passed!"
    exit 0
fi
```

### Run multiple test suites

```bash
#!/bin/bash
NAMESPACE=$(bonfire namespace list | grep $(whoami) | awk '{print $1}')

# Run smoke tests
echo "Running smoke tests..."
POD_SMOKE=$(.claude/scripts/hbi-deploy-iqe-pod.sh $NAMESPACE "smoke")
oc wait --for=condition=Complete job -l job-name=$POD_SMOKE -n $NAMESPACE --timeout=30m

# Run group tests
echo "Running group tests..."
POD_GROUPS=$(.claude/scripts/hbi-deploy-iqe-pod.sh $NAMESPACE "backend and groups")
oc wait --for=condition=Complete job -l job-name=$POD_GROUPS -n $NAMESPACE --timeout=30m

echo "All tests completed!"
```

### CI/CD Integration

```bash
#!/bin/bash
set -e

# Deploy HBI
NAMESPACE=$(bonfire namespace reserve -d 4)
bonfire deploy host-inventory -n $NAMESPACE

# Run IQE tests
POD=$(.claude/scripts/hbi-deploy-iqe-pod.sh $NAMESPACE "backend and smoke")

# Wait and capture results
oc wait --for=condition=Complete job -l job-name=$POD -n $NAMESPACE --timeout=30m
oc logs -n $NAMESPACE $POD > iqe-results.log

# Check for failures
if grep -q "failed" iqe-results.log; then
    echo "Tests failed, see iqe-results.log"
    exit 1
fi

# Cleanup
bonfire namespace release $NAMESPACE
```

## Integration with Claude Code

### Slash Command

Use `/hbi-deploy-iqe-pod` for interactive testing:

```bash
/hbi-deploy-iqe-pod -m "smoke"
/hbi-deploy-iqe-pod -m "backend and groups"
```

### Direct Script Usage

For automation and scripting:

```bash
# From any script or automation
POD=$(.claude/scripts/hbi-deploy-iqe-pod.sh)
.claude/scripts/view-iqe-logs.sh --follow
```

## Troubleshooting

**"Could not auto-detect namespace"**
- Ensure you have a reserved namespace: `bonfire namespace list`
- Or provide namespace explicitly: `./hbi-deploy-iqe-pod.sh ephemeral-abc123`

**"Pod failed to become ready"**
- Check pod status: `oc get pod -n <namespace>`
- Check pod events: `oc describe pod <pod-name> -n <namespace>`
- Check namespace is healthy: `oc get pods -n <namespace>`

**"No running IQE pod found"**
- The pod may have already completed
- List all pods: `oc get pods -n <namespace> | grep iqe`
- Include completed pods: `oc get pods -n <namespace> --show-all`

## Related Documentation

- [iqe-host-inventory-plugin README](../../iqe-host-inventory-plugin/README.md)
- [Running tests in ephemeral environment](../../iqe-host-inventory-plugin/README.md#running-tests-in-ephemeral-environment)
- [Bonfire documentation](https://internal-consoledot.pages.redhat.com/bonfire/)
