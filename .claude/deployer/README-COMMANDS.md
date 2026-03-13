# HBI Ephemeral Environment Commands

Complete guide to deploying, verifying, testing, and cleaning up HBI ephemeral environments.

## Quick Start

```bash
# Deploy environment
/hbi-deploy

# Verify it's working
/hbi-verify-setup

# Run tests (optional)
/hbi-test-iqe smoke

# Cleanup when done
/hbi-cleanup
```

## Available Commands

| Command | Purpose | Duration |
|---------|---------|----------|
| `/hbi-deploy` | 🚀 Deploy ephemeral environment | ~7 minutes |
| `/hbi-verify-setup` | ✅ Verify environment health | ~10 seconds |
| `/hbi-test-iqe` | 🧪 Run IQE tests | ~15-60 minutes |
| `/hbi-cleanup` | 🧹 Delete environment | ~30 seconds |

---

## 1. /hbi-deploy

Deploy complete HBI environment with Kessel, RBAC v2, and all dependencies.

### What Gets Deployed

**Services (50+ pods):**
- Host Inventory (API + MQ services)
- Kessel Inventory API
- Kessel Relations API (SpiceDB)
- RBAC v2 Service
- Kafka + Zookeeper
- PostgreSQL (3 databases)
- Unleash (Feature Flags)

**Demo Data:**
- 10 sample hosts
- 7 workspaces
- Test users
- Kafka connectors
- SpiceDB schema

**Local Access (12 port forwards):**
- HBI API: http://localhost:8000
- RBAC v2: http://localhost:8111
- Kessel Inventory: http://localhost:8222
- Kessel Relations: http://localhost:8333
- Databases: localhost:5432, 5433, 5434
- Kafka: localhost:9092, 29092
- Unleash: http://localhost:4242

### Usage

```bash
# Default (335 hour reservation)
/hbi-deploy

# Custom duration
/hbi-deploy --duration 24h

# Reuse existing namespace
/hbi-deploy --force
```

### Files Modified

- `.env` - Database credentials updated (backup created)
- `/etc/hosts` - Kafka bootstrap server added
- `tmp/ephemeral_ports_*.log` - Port forward PIDs
- `tmp/ephemeral_db_credentials_*.log` - DB credentials

### Implementation

Script: `.claude/deployer/deploy-ephemeral.sh`

---

## 2. /hbi-verify-setup

Verify ephemeral environment is properly configured and running.

### What Gets Checked (7 checks)

1. **Namespace** - Exists, owned by you, ready status
2. **Pods** - All running, key services healthy
3. **Port Forwards** - All 12 active on correct ports
4. **API Health** - HBI API responding (HTTP 200)
5. **Databases** - All 3 connected with data counts
6. **Configuration** - `.env` and log files present
7. **Feature Flags** - Unleash flags configured

### Sample Output

```
✅ Namespace: ephemeral-abc123
✅ 51 running pods (out of 53 total)
✅ 12 port forwards active
✅ HBI API: Healthy (HTTP 200)
✅ HBI Database: Connected - 10 hosts
✅ RBAC Database: Connected - 7 workspaces
✅ Kessel Database: Connected - 10 resources
✅ .env file exists
✅ hbi.api.kessel-phase-1: enabled
```

### Usage

```bash
/hbi-verify-setup
```

### When to Use

- After `/hbi-deploy` to confirm deployment
- Before running tests to ensure environment ready
- Troubleshooting deployment issues
- Daily health check of long-running environment

### Implementation

Script: `.claude/scripts/verify-ephemeral-setup.sh`

---

## 3. /hbi-test-iqe

Run IQE tests against the ephemeral environment.

### Test Suites

**Smoke Tests (~81 tests, ~15-25 minutes):**
```bash
/hbi-test-iqe smoke
```

**Full Backend Tests (~1+ hour):**
```bash
/hbi-test-iqe backend
```

**Custom Markers:**
```bash
/hbi-test-iqe "backend and groups"
```

### What Gets Tested

- Host creation via Kafka and upload
- Group creation and management
- API endpoints (GET/POST/PATCH/DELETE)
- Tags, filtering, pagination
- Database operations
- MQ events and notifications
- Staleness and culling

### How It Works

1. Creates ClowdJobInvocation in ephemeral namespace
2. Deploys IQE pod with test environment
3. Runs pytest with specified markers
4. Outputs pod name for log viewing

### View Results

```bash
# Live streaming
oc logs -n <namespace> <pod-name> -f

# After completion
oc logs -n <namespace> <pod-name> | tail -100
```

### Implementation

Scripts:
- `.claude/scripts/deploy-iqe-pod.sh` - Deploy test pod
- `.claude/scripts/view-iqe-logs.sh` - View logs

---

## 4. /hbi-cleanup

Cleanup and delete ephemeral environment.

### What Gets Deleted

- ⚠️  All pods and containers (51 pods)
- ⚠️  All databases and data
- ⚠️  All services and deployments
- ⚠️  The entire namespace

### What's Preserved

- ✅ Logs in `tmp/ephemeral_*` (for debugging)
- ✅ `.env` file (credentials remain)
- ✅ Local code and configuration

### Safety Features

**Confirmation Prompt:**
```
Are you sure you want to delete this namespace? (yes/no): _
```

Type `yes` or `y` to confirm, anything else to cancel.

**Skip confirmation:**
```bash
/hbi-cleanup --force
```

### Usage

```bash
# Auto-detect namespace, prompt for confirmation
/hbi-cleanup

# Specific namespace
/hbi-cleanup ephemeral-abc123

# Skip confirmation (automation)
/hbi-cleanup --force
```

### When to Use

- When done testing/developing
- Before deploying fresh environment
- To free up cluster resources
- Namespace approaching expiration

### Implementation

Script: `.claude/scripts/remove-ephemeral-namespace.sh`

---

## Complete Workflow Examples

### Daily Development Workflow

```bash
# Morning: Deploy environment
/hbi-deploy --duration 8h

# Verify it's ready
/hbi-verify-setup

# Develop and test your code locally
# (environment runs in background, accessible via localhost:8000)

# Evening: Cleanup
/hbi-cleanup
```

### Testing Workflow

```bash
# Deploy
/hbi-deploy --duration 4h

# Verify
/hbi-verify-setup

# Run smoke tests
/hbi-test-iqe smoke

# View results
.claude/scripts/view-iqe-logs.sh --follow

# Cleanup
/hbi-cleanup
```

### Troubleshooting Workflow

```bash
# Deploy
/hbi-deploy

# Something's wrong, verify environment
/hbi-verify-setup

# Check specific service
kubectl get pods -n ephemeral-abc123 | grep kessel

# View logs
kubectl logs -n ephemeral-abc123 deployment/kessel-inventory-api

# If needed, cleanup and redeploy
/hbi-cleanup
/hbi-deploy
```

### Long-Running Environment

```bash
# Deploy for a week
/hbi-deploy --duration 168h

# Daily health check
/hbi-verify-setup

# When done
/hbi-cleanup
```

---

## Script Reference

All scripts are located in `.claude/scripts/`:

| Script | Purpose | Can Run Directly |
|--------|---------|------------------|
| `deploy-ephemeral.sh` | Deploy HBI environment | ✅ Yes |
| `verify-ephemeral-setup.sh` | Verify environment | ✅ Yes |
| `remove-ephemeral-namespace.sh` | Cleanup environment | ✅ Yes |
| `deploy-iqe-pod.sh` | Deploy IQE test pod | ✅ Yes |
| `view-iqe-logs.sh` | View IQE test logs | ✅ Yes |

### Direct Script Usage

All scripts support direct execution for automation:

```bash
# Deploy
.claude/deployer/deploy-ephemeral.sh --duration 24h

# Verify
.claude/scripts/verify-ephemeral-setup.sh

# Cleanup
.claude/scripts/remove-ephemeral-namespace.sh --force

# Deploy IQE pod
POD=$(.claude/scripts/deploy-iqe-pod.sh ephemeral-abc123 "smoke")

# View logs
.claude/scripts/view-iqe-logs.sh $POD --follow
```

---

## Prerequisites

### Required Tools

- `oc` - OpenShift CLI ([install](https://docs.openshift.com/container-platform/latest/cli_reference/openshift_cli/getting-started-cli.html))
- `bonfire` - Red Hat ephemeral environment tool ([install](https://internal-consoledot.pages.redhat.com/bonfire/))
- `kubectl` - Kubernetes CLI ([install](https://kubernetes.io/docs/tasks/tools/))
- `jq` - JSON processor (optional, for better output)

### Ephemeral Cluster Access

1. **Get token:** https://oauth-openshift.apps.crc-eph.r9lp.p1.openshiftapps.com/oauth/token/request

2. **Login:**
   ```bash
   oc login --token=<your-token> --server=https://api.crc-eph.r9lp.p1.openshiftapps.com:6443
   ```

3. **Verify:**
   ```bash
   oc whoami
   bonfire --version
   ```

### Passwordless Sudo

Required for updating `/etc/hosts`:

```bash
# Test
sudo -n echo "OK" 2>/dev/null && echo "✅ Passwordless sudo works" || echo "❌ Setup required"

# Setup (if needed)
sudo visudo
# Add: your_username ALL=(ALL) NOPASSWD: /usr/bin/tee /etc/hosts
```

---

## Troubleshooting

### Deployment Issues

**"EPHEMERAL_TOKEN is not set"**
```bash
oc login --token=<token> --server=<server>
```

**"Failed to reserve namespace"**
```bash
bonfire --version  # Check bonfire installed
oc whoami          # Check logged in
```

**"Port forwarding failed"**
```bash
kubectl get pods -n <namespace>  # Check pods running
pkill -f "kubectl port-forward"  # Kill existing forwards
```

### Verification Issues

**"No running pods found"**
- Deployment may still be in progress
- Wait 1-2 minutes and retry
- Check: `kubectl get pods -n <namespace>`

**"Database connection failed"**
- Port forwards may not be active
- Check: `ps aux | grep "kubectl port-forward"`
- Restart: `.claude/deployer/deploy-ephemeral.sh --force`

**"Feature flags not found"**
- Expected for fresh deployments
- Enable manually if needed (see session logs)

### Cleanup Issues

**"No ephemeral namespace found"**
- You don't have any active namespaces
- Check: `bonfire namespace list`

**"Some port forwards still running"**
```bash
pkill -9 -f "kubectl port-forward"
```

---

## Tips & Best Practices

### Resource Management

- ✅ Use shortest duration needed (saves cluster resources)
- ✅ Run `/hbi-cleanup` when done (don't leave idle)
- ✅ Default 335h (2 weeks) is for long-term testing only

### Development Workflow

- ✅ Use `/hbi-verify-setup` after deploy (catch issues early)
- ✅ Keep ephemeral logs in `tmp/` (helpful for debugging)
- ✅ Backup `.env` before deploy (auto-backed up as `.env.backup_*`)

### Testing Workflow

- ✅ Run smoke tests first (faster, catches major issues)
- ✅ Full test suite for comprehensive validation
- ✅ Save IQE logs: `oc logs <pod> > results.log`

### Automation

- ✅ Use `--force` flag to skip prompts
- ✅ Check exit codes (0 = success, non-zero = failure)
- ✅ Capture pod names for log viewing

---

## CI/CD Integration

### Example Pipeline

```bash
#!/bin/bash
set -e

# Deploy environment
NAMESPACE=$(.claude/deployer/deploy-ephemeral.sh --duration 4h | grep "Namespace:" | awk '{print $2}')

# Verify deployment
if ! .claude/scripts/verify-ephemeral-setup.sh; then
    echo "❌ Deployment verification failed"
    exit 1
fi

# Run smoke tests
POD=$(.claude/scripts/deploy-iqe-pod.sh $NAMESPACE "backend and smoke")

# Wait for completion
oc wait --for=condition=Complete job -l job-name=$POD -n $NAMESPACE --timeout=30m

# Get results
oc logs -n $NAMESPACE $POD > iqe-results.log

# Check for failures
if grep -q "failed" iqe-results.log; then
    echo "❌ Tests failed"
    .claude/scripts/remove-ephemeral-namespace.sh $NAMESPACE --force
    exit 1
fi

# Cleanup
.claude/scripts/remove-ephemeral-namespace.sh $NAMESPACE --force

echo "✅ All tests passed"
```

---

## Related Documentation

- [Deployment Scripts](.claude/deployer/README.md)
- [IQE Testing](../../iqe-host-inventory-plugin/README.md)
- [Bonfire Documentation](https://internal-consoledot.pages.redhat.com/bonfire/)
- [Main Project README](../../README.md)

---

## Support

For issues or questions:
- Check troubleshooting section above
- Review individual command documentation in `.claude/commands/`
- Check script source code in `.claude/scripts/`
- Review session logs in `CLAUDE.local.md`
