# /hbi-enable-flags - Enable HBI Feature Flags in Unleash

Enable Kessel-related feature flags in the Unleash feature flag service.

## What This Command Does

1. **Check Availability** - Verifies Unleash is accessible (port 4242)
2. **Login** - Authenticates to Unleash admin API
3. **Create/Enable Flags** - Creates and enables specified feature flags
4. **Verify** - Confirms flags are enabled in both dev and prod environments

## Usage

```bash
# Enable all default Kessel flags
/hbi-enable-flags

# Enable specific flags
/hbi-enable-flags hbi.api.kessel-phase-1

# List all HBI feature flags
/hbi-enable-flags --list

# Verify flags are enabled (without modifying)
/hbi-enable-flags --verify

# Custom Unleash server
/hbi-enable-flags --url http://custom-host:4242
```

## Options

- `--list` - List all HBI feature flags and their status
- `--verify` - Verify flags are enabled (read-only, no changes)
- `--url URL` - Unleash server URL (default: `http://localhost:4242`)
- `--user USER` - Unleash username (default: `admin`)
- `--password PASS` - Unleash password (default: `unleash4all`)
- `--help` - Show help message

## Default Feature Flags

The following flags are enabled by default:

| Flag Name | Purpose |
|-----------|---------|
| `hbi.api.kessel-phase-1` | Enable Kessel Phase 1 integration |
| `hbi.api.kessel-groups` | Enable Kessel Groups (RBAC v2) |
| `hbi.api.kessel-force-single-checks-for-bulk` | Use single checks for bulk operations |

## Prerequisites

**Required:**
- Unleash service running and accessible
- Port forwarding active to Unleash (port 4242)
- `jq` installed (for JSON parsing)

**Setup port forwarding:**
```bash
# If not already set up, run:
/hbi-setup-for-dev

# Or manually:
kubectl port-forward svc/env-<namespace>-featureflags 4242:4242 -n <namespace>
```

## Output

```bash
$ /hbi-enable-flags

======================================================================
  Enable HBI Feature Flags in Unleash
======================================================================

[INFO] Checking Unleash availability at http://localhost:4242...
✓ Unleash is accessible

[INFO] Logging into Unleash as admin...
✓ Logged into Unleash

[INFO] Enabling 3 feature flag(s)...

ℹ️  Processing flag: hbi.api.kessel-phase-1
  ℹ️  Flag already exists
  ✅ Enabled in development
  ✅ Enabled in production

ℹ️  Processing flag: hbi.api.kessel-groups
  ℹ️  Flag created
  ✅ Enabled in development
  ✅ Enabled in production

[INFO] Verifying feature flags...
  ✅ hbi.api.kessel-phase-1: enabled (dev + prod)
  ✅ hbi.api.kessel-groups: enabled (dev + prod)
  ✅ hbi.api.kessel-force-single-checks-for-bulk: enabled (dev + prod)

✓ All feature flags verified

======================================================================
✓ Complete!
======================================================================
```

## Use Cases

### After Deployment
```bash
# Deploy HBI
/hbi-deploy

# Setup local dev environment
/hbi-setup-for-dev

# Enable feature flags for Kessel testing
/hbi-enable-flags
```

### Verify Flags Before Testing
```bash
# Check which flags are enabled
/hbi-enable-flags --list

# Verify specific flags
/hbi-enable-flags --verify
```

### Enable Custom Flags
```bash
# Enable only specific flag
/hbi-enable-flags hbi.api.kessel-phase-1

# Enable multiple custom flags
/hbi-enable-flags hbi.api.custom-flag-1 hbi.api.custom-flag-2
```

### CI/CD Pipeline
```bash
#!/bin/bash
# Wait for deployment
sleep 30

# Enable flags
.claude/scripts/enable-feature-flags.sh --verify || \
  .claude/scripts/enable-feature-flags.sh

# Run tests
pipenv run pytest tests/
```

## Troubleshooting

**"Unleash is not accessible"**
- Check port forwarding: `ps aux | grep "port-forward.*4242"`
- Verify Unleash pod is running: `kubectl get pods | grep featureflags`
- Setup port forwarding: `/hbi-setup-for-dev`
- Manually forward: `kubectl port-forward svc/env-<ns>-featureflags 4242:4242`

**"Failed to login to Unleash"**
- Verify credentials (default: admin / unleash4all)
- Check Unleash is healthy: `curl http://localhost:4242/health`
- Check Unleash logs: `kubectl logs -n <namespace> deployment/<unleash-pod>`

**"Flag not found" after creation**
- Wait a few seconds and retry
- Check Unleash UI: http://localhost:4242
- Verify API response manually: `curl -s http://localhost:4242/api/admin/projects/default/features`

**"Some feature flags are not properly enabled"**
- Check specific environment status in Unleash UI
- Manually enable via UI if needed
- Re-run the script: `/hbi-enable-flags`

## Environment Variables

You can set these environment variables instead of using command-line options:

```bash
export UNLEASH_URL=http://localhost:4242
export UNLEASH_USER=admin
export UNLEASH_PASS=unleash4all

/hbi-enable-flags
```

## Unleash UI

After enabling flags, you can verify in the Unleash web UI:
- **URL**: http://localhost:4242
- **Login**: admin / unleash4all
- **Navigate**: Projects → default → Feature flags
- **Filter**: Search for "hbi.api"

## Related Commands

- `/hbi-setup-for-dev` - Setup port forwarding and local environment
- `/hbi-verify-setup` - Verify entire environment (includes flag check)
- `/hbi-deploy-and-test` - Deploy and test (enables flags automatically)

## Implementation

This command uses:
- `.claude/scripts/enable-feature-flags.sh` - Main script
- Unleash Admin API for flag management
- Cookie-based authentication

## Advanced Usage

### Custom Unleash Server
```bash
# Remote Unleash instance
/hbi-enable-flags --url https://unleash.example.com \
  --user myuser --password mypass
```

### Integration with Tests
```python
# In your test setup
import subprocess

def setup_feature_flags():
    """Enable feature flags before test run"""
    result = subprocess.run([
        '.claude/scripts/enable-feature-flags.sh',
        '--verify'
    ], capture_output=True, text=True)

    if result.returncode != 0:
        # Flags not enabled, enable them
        subprocess.run([
            '.claude/scripts/enable-feature-flags.sh'
        ], check=True)
```

### Disable Flags (Manual)
```bash
# Login to Unleash
curl -X POST http://localhost:4242/auth/simple/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "unleash4all"}' \
  -c /tmp/unleash-cookies.txt

# Disable in development
curl -X POST "http://localhost:4242/api/admin/projects/default/features/hbi.api.kessel-groups/environments/development/off" \
  -b /tmp/unleash-cookies.txt \
  -H "Content-Type: application/json"

# Disable in production
curl -X POST "http://localhost:4242/api/admin/projects/default/features/hbi.api.kessel-groups/environments/production/off" \
  -b /tmp/unleash-cookies.txt \
  -H "Content-Type: application/json"
```
