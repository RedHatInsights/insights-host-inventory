# /hbi-test-iqe - Run IQE Tests in Ephemeral Environment

Deploy an IQE test pod to run tests against the ephemeral HBI deployment.

## What This Command Does

1. **Auto-detect Namespace** - Finds your active ephemeral namespace
2. **Deploy IQE Pod** - Creates ClowdJobInvocation to run tests
3. **Wait for Ready** - Ensures pod is running
4. **Stream Logs** - Shows live test execution (optional)

## Usage

```bash
/hbi-test-iqe
/hbi-test-iqe smoke
/hbi-test-iqe "backend and not resilience"
```

## Test Presets

**Smoke Tests (default):**
```bash
/hbi-test-iqe smoke
```
Runs ~81 critical tests (~15-25 minutes)

**Full Backend Tests:**
```bash
/hbi-test-iqe backend
```
Runs all backend tests (~1+ hour)

**Custom Markers:**
```bash
/hbi-test-iqe "backend and groups"
```
Runs tests matching your pytest markers

## What Gets Tested

The IQE pod runs tests against your ephemeral environment:
- Host creation via Kafka and upload
- Group creation and management
- API endpoints (GET/POST/PATCH/DELETE)
- Tags, filtering, pagination
- Database operations
- MQ events and notifications

## Prerequisites

- Active ephemeral deployment (via `/hbi-deploy`)
- All services running and healthy
- Port forwards not required (pod runs inside cluster)

## Output

Provides:
- Pod name for log viewing
- Namespace information
- Command to view live logs
- Test execution status

## Test Results

**View live logs:**
```bash
oc logs -n <namespace> <pod-name> -f
```

**Check test status:**
```bash
oc get pod <pod-name> -n <namespace>
```

**View final results:**
```bash
oc logs -n <namespace> <pod-name> | tail -100
```

## Common Test Markers

- `smoke` - Critical smoke tests (~81 tests)
- `backend` - All backend/API tests
- `ephemeral` - Ephemeral-only tests
- `groups` - Group-related tests
- `rbac_dependent` - RBAC permission tests (usually skipped)
- `cert_auth` - Certificate auth tests (usually skipped)
- `resilience` - Graceful shutdown tests (usually skipped)

## Example Combinations

**Just group tests:**
```bash
/hbi-test-iqe "backend and groups and not rbac_dependent"
```

**Smoke + groups:**
```bash
/hbi-test-iqe "smoke or (backend and groups)"
```

**Single test:**
```bash
/hbi-test-iqe "test_create_host"
```

## Related Commands

- `/hbi-deploy` - Deploy ephemeral environment
- `/hbi-verify-setup` - Verify environment is ready
- `/hbi-doctor` - Health check your dev environment

## Implementation

This command uses: `.claude/scripts/deploy-iqe-pod.sh`

## Automation Usage

For scripts and automation:

```bash
# Deploy pod and capture name
POD=$(.claude/scripts/deploy-iqe-pod.sh ephemeral-abc123 "smoke")

# Stream logs
oc logs -n ephemeral-abc123 $POD -f

# Wait for completion
oc wait --for=condition=Complete job -l job-name=$POD -n ephemeral-abc123
```
