# PR 5: Automated Testing Infrastructure

**Part 5 of 7** in the HBI Deployment Infrastructure Series

This PR adds automated testing infrastructure for running unit tests and IQE integration tests against ephemeral HBI deployments.

## What This PR Does

Provides automated testing workflows that:
- Deploy ephemeral environment and run unit tests
- Deploy IQE test pods via ClowdJobInvocation
- Run IQE integration tests against deployed HBI
- Handle test retry logic for transient failures
- Generate test reports and logs
- Enable `/hbi-deploy-and-test` and `/hbi-deploy-iqe-pod` slash commands

## Why This Matters

Before this PR, developers had to:
- Manually deploy ephemeral namespace
- Manually setup local environment
- Manually run pytest tests
- Manually create IQE test pods
- Remember complex bonfire and iqe commands
- Debug test failures without structured logging

After this PR, developers can:
- Run `/hbi-deploy-and-test` for full deployment + unit tests
- Run `/hbi-deploy-iqe-pod` for IQE integration tests
- Automatic retry logic handles transient failures
- Structured test reports for debugging
- Consistent testing workflow across team

## Files Added (5 files, 1,079 lines)

### Testing Scripts
- **`.claude/scripts/deploy-and-unit-test.sh`** (214 lines)
  - Orchestrates deployment + unit test workflow
  - Calls deploy-ephemeral.sh
  - Calls setup-for-dev.sh
  - Runs pytest with coverage
  - Generates test report
  - Handles cleanup on failure

- **`.claude/scripts/hbi-deploy-iqe-pod.sh`** (389 lines)
  - Deploys IQE test pod via ClowdJobInvocation
  - Waits for pod to be ready
  - Monitors test execution
  - Retrieves test results
  - Handles cleanup (deletes ClowdJobInvocation)
  - Supports custom IQE markers and filters

### Documentation
- **`.claude/commands/hbi-deploy-and-test.md`** (242 lines)
  - `/hbi-deploy-and-test` command documentation
  - Full workflow explanation
  - Usage examples
  - Output interpretation
  - Troubleshooting guide

- **`.claude/commands/hbi-deploy-iqe-pod.md`** (173 lines)
  - `/hbi-deploy-iqe-pod` command documentation
  - IQE marker reference
  - Test filtering examples
  - ClowdJobInvocation lifecycle
  - Debugging failed tests

- **`.claude/scripts/README-IQE.md`** (61 lines)
  - IQE testing overview
  - Common test markers
  - Test organization
  - Running tests locally vs ephemeral

## Commands Enabled

### `/hbi-deploy-and-test`

Deploys HBI to ephemeral namespace and runs unit tests.

**Usage:**
```bash
/hbi-deploy-and-test
/hbi-deploy-and-test --duration 24h
/hbi-deploy-and-test --skip-tests
```

**What it does:**
1. Creates ephemeral namespace (default: 335h duration)
2. Deploys HBI, Kessel, RBAC via bonfire
3. Seeds RBAC test users
4. Validates deployment
5. Sets up port-forwards
6. Extracts credentials to `.env`
7. Runs `pipenv run pytest tests/` with coverage
8. Generates test report in `tmp/test-report.txt`
9. Reports pass/fail counts

**Example output:**
```
========================================
Deployment and Testing Complete
========================================
Namespace: ephemeral-abc123
Duration: 335h (14 days)
Tests: 2160 passed, 0 failed, 4 skipped
Coverage: 87%
Report: tmp/test-report.txt
========================================
```

### `/hbi-deploy-iqe-pod`

Deploys IQE test pod and runs integration tests.

**Usage:**
```bash
# Run all ephemeral tests
/hbi-deploy-iqe-pod

# Run specific marker
/hbi-deploy-iqe-pod --marker "groups"

# Run specific test
/hbi-deploy-iqe-pod --filter "test_create_group"

# Run with custom IQE options
/hbi-deploy-iqe-pod --iqe-opts "-k test_hosts and not resilience"

# Specify namespace
/hbi-deploy-iqe-pod --namespace ephemeral-abc123
```

**What it does:**
1. Detects active namespace
2. Creates ClowdJobInvocation resource
3. Waits for IQE pod to start
4. Monitors test execution (streams logs)
5. Retrieves test results
6. Deletes ClowdJobInvocation (cleanup)
7. Outputs test summary

**IQE Markers Supported:**
- `@pytest.mark.ephemeral` - All ephemeral-safe tests
- `@pytest.mark.groups` - Group management tests
- `@pytest.mark.hosts` - Host management tests
- `@pytest.mark.tags` - Tag tests
- `@pytest.mark.system_profile` - System profile tests
- `@pytest.mark.rbac` - RBAC permission tests

## Dependencies

**Requires:**
- **PR 1** - Core deployment infrastructure
- **PR 2** - Local development setup (for unit tests)
- **PR 3** - Environment verification (optional but recommended)

This PR builds on the deployment and setup infrastructure from PR 1 and PR 2.

## What's Next

After this PR is merged, subsequent PRs will add:
- **PR 6**: Cleanup utilities
- **PR 7**: Configuration examples

## Testing

To test this PR locally:

```bash
# Checkout this branch
git checkout pr5-eens-testing-infrastructure

# Test deploy-and-test workflow
.claude/scripts/deploy-and-unit-test.sh

# Test IQE pod deployment (requires existing namespace)
.claude/deployer/deploy-ephemeral.sh
.claude/scripts/hbi-deploy-iqe-pod.sh

# Test with specific marker
.claude/scripts/hbi-deploy-iqe-pod.sh --marker groups

# Verify cleanup
kubectl get cji -n <namespace>  # Should be empty after test
```

Expected result:
- Unit tests run successfully with pytest
- IQE pod deploys and runs tests
- ClowdJobInvocation cleaned up after test

## Technical Details

### Deploy-and-Test Workflow

```
deploy-and-unit-test.sh
  ├── deploy-ephemeral.sh (PR 1)
  │   ├── bonfire deploy
  │   └── RBAC user seeding
  ├── setup-for-dev.sh (PR 2)
  │   ├── Port-forwards
  │   └── .env generation
  ├── verify-ephemeral-setup.sh (PR 3, optional)
  └── pipenv run pytest tests/
      └── Generate test-report.txt
```

### IQE ClowdJobInvocation

Creates K8s custom resource for IQE testing:
```yaml
apiVersion: cloud.redhat.com/v1alpha1
kind: ClowdJobInvocation
metadata:
  name: iqe-host-inventory-test-<timestamp>
spec:
  appName: host-inventory
  testing:
    iqePlugin: host_inventory
    iqeMarker: "ephemeral and not resilience"
```

**Lifecycle:**
1. Create ClowdJobInvocation
2. Clowder operator creates Job
3. Job creates Pod with IQE container
4. Monitor pod logs for test execution
5. Parse test results from logs
6. Delete ClowdJobInvocation (deletes Job and Pod)

### Test Result Parsing

Extracts pytest output:
```bash
# Parse test counts
passed=$(grep "passed" pod_logs.txt | sed 's/.*\([0-9]\+\) passed.*/\1/')
failed=$(grep "failed" pod_logs.txt | sed 's/.*\([0-9]\+\) failed.*/\1/')

# Extract failed test names
grep "FAILED" pod_logs.txt | awk '{print $1}'
```

### Retry Logic for Transient Failures

**Host creation retries:**
```python
# In IQE tests
max_retries = 10
for attempt in range(max_retries):
    hosts = kafka.create_random_hosts(3)
    if len(hosts) == 3:
        break
    sleep(0.5)
```

### Test Report Generation

Creates structured report in `tmp/test-report.txt`:
```
========================================
HBI Unit Test Report
========================================
Date: 2026-04-05 14:32:15
Namespace: ephemeral-abc123
Duration: 127.34s

Tests Passed: 2160
Tests Failed: 0
Tests Skipped: 4
Coverage: 87%

Failed Tests:
(none)

Test Log: tmp/pytest-output.log
========================================
```

### Cleanup on Failure

If deployment or tests fail:
```bash
trap cleanup EXIT

cleanup() {
  echo "Cleaning up..."
  # Delete ClowdJobInvocation
  kubectl delete cji -n $NAMESPACE --all
  # Stop port-forwards
  pkill -f "kubectl port-forward"
}
```

## Rollback Plan

If issues are found after merge:
1. This PR only adds new files, doesn't modify existing code
2. Safe to revert without impacting other functionality
3. All changes are in `.claude/` directory (not production code)
4. Testing scripts don't modify HBI code, only run tests

## Related Work

- Depends on PR 1 (deployment infrastructure)
- Depends on PR 2 (local setup for unit tests)
- Uses PR 3 (verification) if available
- Integrates with existing IQE test suite
- Related to CI/CD pipeline patterns

## Questions for Reviewers

1. Should we add timeout values for test execution?
2. Should IQE pod cleanup be optional (--keep-pod flag)?
3. Should we add test result upload to external reporting system?

---

**Merge Sequence**: Can merge **after PR 1 and PR 2** (requires deployment and local setup)
**Size**: 5 files, 1,079 lines (603 lines scripts, 476 lines documentation)
**Risk**: Low - testing infrastructure, doesn't modify HBI production code
