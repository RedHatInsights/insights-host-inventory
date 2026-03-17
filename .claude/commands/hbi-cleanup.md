# /hbi-cleanup - Cleanup HBI Ephemeral Environment

Tear down and cleanup an HBI ephemeral environment by stopping port forwards and releasing the namespace.

## What This Command Does

1. **Auto-detect Namespace** - Finds your active ephemeral namespace and displays it
2. **Verify Ownership** - Confirms you own the namespace before proceeding
3. **Stop Port Forwards** - Kills all kubectl port-forward processes
4. **Prompt for Confirmation** - Shows which namespace will be deleted and asks for confirmation
5. **Release Namespace** - Deletes the ephemeral namespace and all resources
6. **Verify Cleanup** - Confirms everything was cleaned up successfully

## Usage

```bash
/hbi-cleanup                    # Auto-detect namespace, prompt for confirmation
/hbi-cleanup ephemeral-abc123   # Specific namespace, prompt for confirmation
/hbi-cleanup --force            # Auto-detect namespace, skip confirmation
/hbi-cleanup ephemeral-abc123 --force  # Specific namespace, skip confirmation
```

## What Gets Deleted

**Kubernetes Resources:**
- All pods (HBI, Kessel, RBAC, Kafka, databases, etc.)
- All services and deployments
- All persistent volumes and data
- The entire namespace

**Local Resources:**
- All kubectl port-forward processes (12 processes)
- Temporary Unleash session files

**What's Preserved:**
- Logs in `tmp/ephemeral_*` (kept for debugging)
- Your local `.env` file
- Local code and configuration

## Safety

The script:
- ✅ **Prompts for confirmation** before deleting namespace
- ✅ Confirms namespace ownership before deletion
- ✅ Auto-detects if you have multiple namespaces
- ✅ Verifies cleanup was successful
- ✅ Provides clear feedback at each step
- ⚠️  **Cannot be undone** - all data is permanently deleted

**The command always shows which namespace will be cleaned:**
- If no namespace specified: Auto-detects and displays the namespace
- If namespace specified: Verifies and displays the namespace

**Confirmation Prompt:**
```
⚠️  This will permanently delete:
   • All pods and containers
   • All databases and data
   • All services and deployments
   • The entire namespace: ephemeral-abc123

Are you sure you want to delete this namespace? (yes/no):
```

Type `yes` or `y` to confirm deletion, anything else to cancel.

## Prerequisites

- Active ephemeral namespace (created via `/hbi-deploy`)
- Bonfire CLI installed and configured
- Namespace owned by you

## Output

**Example output showing namespace detection and confirmation:**

```bash
$ /hbi-cleanup

═══════════════════════════════════════════════════════════
  HBI Ephemeral Environment Cleanup
═══════════════════════════════════════════════════════════

ℹ️  No namespace provided, auto-detecting...
ℹ️  Auto-detected namespace: ephemeral-9uu6pk

Verifying namespace...
✅ Namespace verified

1. Stopping port forwards...
✅ No port forwards to stop

2. Releasing namespace: ephemeral-9uu6pk
⚠️  This will permanently delete:
   • All pods and containers
   • All databases and data
   • All services and deployments
   • The entire namespace: ephemeral-9uu6pk

Are you sure you want to delete this namespace? (yes/no): yes

✅ Namespace released successfully

3. Verification...
✅ Namespace no longer exists
✅ Cleanup complete!

═══════════════════════════════════════════════════════════
✓ Complete!
═══════════════════════════════════════════════════════════
```

Provides:
- 📊 Progress updates for each step
- 🔍 **Shows which namespace will be cleaned** (auto-detected or specified)
- ✅ Success confirmations
- ⚠️  Warnings when needed
- 📝 Summary of what was cleaned up

## Examples

**Cleanup auto-detected namespace:**
```bash
/hbi-cleanup
```

**Cleanup specific namespace:**
```bash
/hbi-cleanup ephemeral-abc123
```

**Manual cleanup:**
```bash
# Stop port forwards
pkill -f "kubectl port-forward"

# Release namespace
bonfire namespace release ephemeral-abc123 --force
```

## After Cleanup

Once cleaned up, you can:

**Deploy a new environment:**
```bash
/hbi-deploy
```

**Check for remaining resources:**
```bash
# Check namespaces
bonfire namespace list

# Check port forwards
ps aux | grep "kubectl port-forward"
```

## Troubleshooting

**"No ephemeral namespace found to cleanup"**
- You don't have any active namespaces
- Check manually: `bonfire namespace list`

**"Namespace not found or not owned by you"**
- The namespace doesn't exist or belongs to someone else
- Verify: `bonfire namespace list`

**"Some port forwards may still be running"**
- Some processes didn't stop cleanly
- Kill manually: `pkill -9 -f "kubectl port-forward"`

**"Failed to release namespace"**
- Bonfire encountered an error
- Try manually: `bonfire namespace release <namespace> --force`
- Check namespace status: `bonfire namespace describe <namespace>`

## Related Commands

- `/hbi-deploy` - Deploy ephemeral environment
- `/hbi-verify-setup` - Verify environment setup
- `/hbi-test-iqe` - Run IQE tests

## Implementation

This command uses: `.claude/scripts/cleanup-ephemeral.sh`

## Automation Usage

For scripts and automation:

```bash
# Cleanup specific namespace
.claude/scripts/cleanup-ephemeral.sh ephemeral-abc123

# Cleanup auto-detected namespace
.claude/scripts/cleanup-ephemeral.sh

# Check exit code
if .claude/scripts/cleanup-ephemeral.sh; then
    echo "Cleanup successful"
else
    echo "Cleanup failed"
fi
```

## Important Notes

**Data Loss:**
- ⚠️  All data in the namespace is permanently deleted
- ⚠️  Database data cannot be recovered
- ⚠️  Test results and logs are lost unless saved locally

**Costs:**
- Releasing unused namespaces saves cluster resources
- Recommended to cleanup when done testing

**Multiple Namespaces:**
- If you have multiple namespaces, the script will cleanup the first one found
- To cleanup a specific namespace, provide it as an argument

## Comparison: Deploy vs Cleanup

| Command | What It Does | Duration | Resources |
|---------|-------------|----------|-----------|
| `/hbi-deploy` | Creates environment | ~5-10 min | Creates namespace, deploys 50+ pods |
| `/hbi-cleanup` | Destroys environment | ~30 sec | Deletes namespace, stops 12 port forwards |
