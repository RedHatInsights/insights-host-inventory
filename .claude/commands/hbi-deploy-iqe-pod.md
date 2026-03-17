# /hbi-deploy-iqe-pod - Deploy IQE Pod with Cleanup

Deploy a fresh IQE pod by cleaning up any existing ClowdJobInvocation and creating a new one.

## What This Command Does

1. **Check for existing IQE pods** - Finds any running/failed IQE pods
2. **Cleanup old ClowdJobInvocations** - Deletes stale CJI resources if needed
3. **Create new ClowdJobInvocation** - Deploys fresh IQE pod
4. **Wait for pod ready** - Ensures pod is running and healthy
5. **Return pod name** - Outputs pod name for log viewing

## Usage

```bash
/hbi-deploy-iqe-pod
/hbi-deploy-iqe-pod -m "smoke"
/hbi-deploy-iqe-pod -k "test_cache_invalidation or test_rbac"
/hbi-deploy-iqe-pod -m "backend and groups"
```

## Options

**Test Selection:**
- `-m "markers"` - Use pytest markers (default: "backend and not resilience and not cert_auth and not rbac_dependent")
- `-k "filter"` - Use test name filter for specific tests

**Namespace:**
- Auto-detected from your active namespaces
- Or specify: `/hbi-deploy-iqe-pod -m "smoke" ephemeral-abc123`

## Examples

**Deploy with default smoke markers:**
```bash
/hbi-deploy-iqe-pod
```

**Run specific tests by name:**
```bash
/hbi-deploy-iqe-pod -k "test_notifications_e2e_delete_by_id or test_rbac_groups_write_permission"
```

**Run custom markers:**
```bash
/hbi-deploy-iqe-pod -m "backend and groups and not rbac_dependent"
```

**With specific namespace:**
```bash
/hbi-deploy-iqe-pod -m "smoke" ephemeral-abc123
```

## What Gets Cleaned Up

Before deploying new pod, the command:
- Lists all IQE-related ClowdJobInvocations in the namespace
- Deletes any existing `iqe-host-inventory-*` CJI resources
- Ensures clean slate for new deployment

## Output

Returns:
- Pod name (for scripting/logging)
- Namespace information
- Command to view live logs

Example:
```
[INFO] Found existing CJI: iqe-host-inventory-12345
[INFO] Deleting old ClowdJobInvocation...
[SUCCESS] Cleanup complete
[INFO] Creating new ClowdJobInvocation...
[SUCCESS] IQE pod deployed: iqe-host-inventory-67890
Pod: iqe-host-inventory-67890
Namespace: ephemeral-abc123

View logs with:
  oc logs -n ephemeral-abc123 iqe-host-inventory-67890 -f
```

## View Test Results

```bash
# Follow logs in real-time
oc logs -n <namespace> <pod-name> -f

# View final results
oc logs -n <namespace> <pod-name> | tail -100

# Check pod status
oc get pod <pod-name> -n <namespace>
```

## Difference from /hbi-test-iqe

**`/hbi-deploy-iqe-pod`**:
- Always creates fresh pod (cleanup first)
- Supports both `-m` (markers) and `-k` (test names)
- Useful when previous pod failed/stuck
- Returns pod name for automation

**`/hbi-test-iqe`**:
- Simpler, no cleanup
- Only supports `-m` markers
- Faster if no cleanup needed

## Prerequisites

- Active ephemeral namespace (via `/hbi-deploy`)
- `oc` logged in to OpenShift cluster
- Bonfire CLI installed

## Common Use Cases

**Retry failed tests:**
```bash
/hbi-deploy-iqe-pod -k "test_that_failed"
```

**Fresh smoke test run:**
```bash
/hbi-deploy-iqe-pod -m "smoke"
```

**Debug specific test:**
```bash
/hbi-deploy-iqe-pod --debug-pod -k "test_cache_invalidation"
```

## Implementation

Uses: `.claude/scripts/hbi-deploy-iqe-pod.sh`

## Related Commands

- `/hbi-test-iqe` - Simple test deployment (no cleanup)
- `/hbi-verify-setup` - Verify environment health
- `/hbi-cleanup` - Full environment cleanup
