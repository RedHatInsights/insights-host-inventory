# PR 6: Namespace Cleanup Utilities

**Part 6 of 7** in the HBI Deployment Infrastructure Series

This PR adds automated cleanup utilities for managing ephemeral namespace lifecycle, including graceful cleanup and forced removal.

## What This PR Does

Provides automated cleanup tools that:
- Stop all local port-forwards
- Clean up local development state
- Remove ephemeral namespaces via bonfire
- Force-delete stuck namespaces when needed
- Provide command reference documentation
- Enable the `/hbi-cleanup` slash command

## Why This Matters

Before this PR, developers had to:
- Manually kill port-forward processes
- Remember bonfire namespace commands
- Debug stuck namespace deletions
- Manually clean up local `.env` files
- Look up namespace deletion procedures

After this PR, developers can:
- Run `/hbi-cleanup` to clean up gracefully
- Force-remove stuck namespaces when needed
- Automatic port-forward cleanup
- Clear local state for fresh starts
- Consistent cleanup workflow across team

## Files Added (4 files, 1,056 lines)

### Cleanup Scripts
- **`.claude/scripts/cleanup-ephemeral.sh`** (287 lines)
  - Graceful cleanup workflow
  - Stops all kubectl port-forwards
  - Removes namespace via bonfire
  - Cleans up local `.env` if requested
  - Reports cleanup status
  - Error handling for stuck deletions

- **`.claude/scripts/remove-ephemeral-namespace.sh`** (351 lines)
  - Force-removes stuck namespaces
  - Deletes K8s namespace directly
  - Bypasses bonfire if stuck
  - Handles finalizers
  - Validates deletion completed
  - Fallback strategies for edge cases

### Documentation
- **`.claude/commands/hbi-cleanup.md`** (231 lines)
  - `/hbi-cleanup` command documentation
  - Usage examples
  - Cleanup workflow explanation
  - Troubleshooting stuck deletions
  - Force removal guide

- **`.claude/deployer/README-COMMANDS.md`** (187 lines)
  - Complete command reference
  - All 7 slash commands documented
  - Workflow diagrams
  - Common usage patterns
  - Quick reference table

## Commands Enabled

### `/hbi-cleanup`

Cleans up ephemeral namespace and local development state.

**Usage:**
```bash
# Clean up detected namespace
/hbi-cleanup

# Clean up specific namespace
/hbi-cleanup --namespace ephemeral-abc123

# Clean up and remove .env file
/hbi-cleanup --clean-env

# Force removal if stuck
/hbi-cleanup --force

# Dry run (show what would be cleaned)
/hbi-cleanup --dry-run
```

**What it does:**

**Graceful cleanup (default):**
1. Detects active namespace
2. Stops all kubectl port-forwards
3. Removes namespace via bonfire
4. Validates namespace deleted
5. Optionally cleans `.env` file
6. Reports cleanup status

**Force removal (--force):**
1. Stops port-forwards
2. Attempts bonfire namespace remove
3. If stuck, deletes K8s namespace directly
4. Removes finalizers if needed
5. Validates deletion completed
6. Reports status

**Example output:**
```
========================================
Cleaning up Ephemeral Environment
========================================
Namespace: ephemeral-abc123

[1/4] Stopping port-forwards...
✓ Killed 12 port-forward processes

[2/4] Removing namespace via bonfire...
✓ Namespace removal initiated

[3/4] Waiting for namespace deletion...
✓ Namespace ephemeral-abc123 deleted

[4/4] Cleaning up local state...
✓ Stopped all background processes

========================================
Cleanup Complete ✓
========================================
```

## Dependencies

**Standalone** - Can merge independently after PR 1.

This PR provides cleanup for environments created by any PR, but doesn't require other PRs.

## What's Next

After this PR is merged:
- **PR 7**: Configuration examples (final PR)

## Testing

To test this PR locally:

```bash
# Checkout this branch
git checkout pr6-eens-cleanup-utilities

# Create test namespace first
.claude/deployer/deploy-ephemeral.sh
.claude/deployer/setup-for-dev.sh

# Test graceful cleanup
.claude/scripts/cleanup-ephemeral.sh

# Verify namespace deleted
bonfire namespace list | grep $(whoami)

# Test force removal (create another namespace first)
.claude/deployer/deploy-ephemeral.sh
.claude/scripts/remove-ephemeral-namespace.sh --namespace <name>

# Test dry run
.claude/scripts/cleanup-ephemeral.sh --dry-run
```

Expected result:
- Graceful cleanup removes namespace via bonfire
- Force removal deletes stuck namespaces
- Port-forwards stopped
- Local state cleaned

## Technical Details

### Port-Forward Cleanup

Identifies and kills all kubectl port-forwards:
```bash
# Find all kubectl port-forward processes
ps aux | grep "kubectl port-forward" | grep -v grep

# Kill them
pkill -f "kubectl port-forward"

# Verify stopped
sleep 1
if ! pgrep -f "kubectl port-forward" >/dev/null; then
  echo "✓ All port-forwards stopped"
fi
```

### Graceful Namespace Removal

Uses bonfire CLI:
```bash
# Remove namespace via bonfire
bonfire namespace remove $NAMESPACE

# Wait for deletion (max 60 seconds)
timeout=60
while kubectl get namespace $NAMESPACE >/dev/null 2>&1; do
  sleep 2
  timeout=$((timeout - 2))
  if [ $timeout -le 0 ]; then
    echo "⚠ Timeout waiting for deletion"
    break
  fi
done
```

### Force Removal Strategy

Multi-stage approach for stuck namespaces:

**Stage 1: Try bonfire**
```bash
bonfire namespace remove $NAMESPACE --timeout 30s
```

**Stage 2: Direct kubectl delete**
```bash
kubectl delete namespace $NAMESPACE --timeout=30s
```

**Stage 3: Remove finalizers**
```bash
# Get namespace JSON
kubectl get namespace $NAMESPACE -o json > ns.json

# Remove finalizers
jq '.spec.finalizers = []' ns.json > ns-patched.json

# Apply patch
kubectl replace --raw "/api/v1/namespaces/$NAMESPACE/finalize" \
  -f ns-patched.json
```

**Stage 4: Validate deletion**
```bash
# Verify namespace gone
for i in {1..30}; do
  if ! kubectl get namespace $NAMESPACE >/dev/null 2>&1; then
    echo "✓ Namespace $NAMESPACE deleted"
    exit 0
  fi
  sleep 1
done
```

### Local State Cleanup

Optionally cleans local files:
```bash
# Clean .env file
if [ "$CLEAN_ENV" = true ]; then
  rm -f .env
  echo "✓ Removed .env file"
fi

# Clean logs
rm -f tmp/deployment.log tmp/port-forwards.log
echo "✓ Cleaned log files"
```

### Dry Run Mode

Shows what would be cleaned without taking action:
```bash
if [ "$DRY_RUN" = true ]; then
  echo "Would kill port-forward processes: $(pgrep -f 'kubectl port-forward' | wc -l)"
  echo "Would remove namespace: $NAMESPACE"
  echo "Would clean .env: $CLEAN_ENV"
  exit 0
fi
```

### Error Handling

Handles common failure scenarios:
- Namespace already deleted
- Bonfire timeout
- kubectl unavailable
- Stuck finalizers
- No active port-forwards

### Cleanup Workflow

```
cleanup-ephemeral.sh
  ├── Detect namespace (bonfire namespace list)
  ├── Stop port-forwards (pkill kubectl)
  ├── Remove namespace (bonfire namespace remove)
  ├── If stuck → remove-ephemeral-namespace.sh
  │   ├── kubectl delete namespace
  │   ├── Remove finalizers
  │   └── Validate deletion
  └── Clean local state (.env, logs)
```

## Command Reference

The **README-COMMANDS.md** provides quick reference for all commands:

| Command | Purpose | Prerequisites |
|---------|---------|---------------|
| `/hbi-deploy` | Deploy to ephemeral | None |
| `/hbi-setup-for-dev` | Setup local env | Deployed namespace |
| `/hbi-verify-setup` | Verify environment | Setup complete |
| `/hbi-enable-flags` | Enable Kessel flags | Setup complete |
| `/hbi-deploy-and-test` | Deploy + unit tests | None |
| `/hbi-deploy-iqe-pod` | Run IQE tests | Deployed namespace |
| `/hbi-cleanup` | Clean up namespace | Active namespace |

## Rollback Plan

If issues are found after merge:
1. This PR only adds new files, doesn't modify existing code
2. Safe to revert without impacting other functionality
3. All changes are in `.claude/` directory (not production code)
4. Cleanup scripts are read-only to HBI code

## Related Work

- Works with PR 1 (cleans up deployed namespaces)
- Works with PR 2 (stops port-forwards)
- Standalone utility - can be used independently
- Complements bonfire namespace management

## Questions for Reviewers

1. Should force removal be the default after bonfire timeout?
2. Should we add `--keep-env` flag to preserve `.env` during cleanup?
3. Should we log removed namespaces for audit trail?

---

**Merge Sequence**: Can merge **after PR 1** (needs deployed namespaces to clean up)
**Size**: 4 files, 1,056 lines (638 lines scripts, 418 lines documentation)
**Risk**: Low - cleanup only, doesn't modify HBI code or active deployments
