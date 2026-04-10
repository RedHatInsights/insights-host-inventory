# HBI Ephemeral Environment Deployment Guide

This guide helps you deploy Host-Based Inventory (HBI) to an ephemeral Kubernetes environment for development and testing.

## Table of Contents

- [Quick Start](#quick-start)
- [Prerequisites](#prerequisites)
- [Deployment Workflow](#deployment-workflow)
- [Available Commands](#available-commands)
- [Step-by-Step Instructions](#step-by-step-instructions)
- [Verification](#verification)
- [Common Tasks](#common-tasks)
- [Troubleshooting](#troubleshooting)
- [Cleanup](#cleanup)

## Quick Start

```bash
# 1. Deploy HBI to ephemeral environment
/hbi-deploy --duration 24h

# 2. Setup local development environment
/hbi-setup-for-dev

# 3. Enable Kessel feature flags
/hbi-enable-flags

# 4. Verify everything is working
/hbi-verify-setup

# 5. Run tests
pipenv run pytest tests/
```

## Prerequisites

### Required Tools

Install these tools before starting:

| Tool | Purpose | Installation |
|------|---------|--------------|
| `oc` | OpenShift CLI | [Install Guide](https://docs.openshift.com/container-platform/latest/cli_reference/openshift_cli/getting-started-cli.html) |
| `bonfire` | Deployment tool | `pip install crc-bonfire` |
| `kubectl` | Kubernetes CLI | [Install Guide](https://kubernetes.io/docs/tasks/tools/) |
| `jq` | JSON processor | `brew install jq` (macOS) or `apt-get install jq` (Linux) |
| `pipenv` | Python environment | `pip install pipenv` |

### Cluster Access

1. **Get ephemeral cluster token**:
   - Visit: https://oauth-openshift.apps.crc-eph.r9lp.p1.openshiftapps.com/oauth/token/request
   - Copy the token

2. **Login to cluster**:
   ```bash
   oc login --token=<your-token> --server=https://api.crc-eph.r9lp.p1.openshiftapps.com:6443
   ```

### Passwordless Sudo (Optional but Recommended)

For automatic `/etc/hosts` updates:

```bash
# Add to /etc/sudoers (use visudo)
yourusername ALL=(ALL) NOPASSWD: /bin/sed, /bin/cp, /bin/grep
```

If you don't configure this, you'll need to manually update `/etc/hosts`.

## Deployment Workflow

The deployment is split into three separate commands for flexibility:

```
┌─────────────────┐
│  /hbi-deploy    │  ← Deploy services to Kubernetes
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│/hbi-setup-for-  │  ← Setup local dev environment
│      dev        │     (port-forwards, credentials, etc.)
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│/hbi-enable-flags│  ← Enable feature flags in Unleash
└─────────────────┘
```

### Why Three Commands?

- **Flexibility**: Deploy once, setup on multiple machines
- **Speed**: Re-run setup without re-deploying
- **Clarity**: Each command has a single, clear purpose
- **CI/CD**: Can deploy without local setup in automated pipelines

## Available Commands

### Core Commands

| Command | Purpose | Duration |
|---------|---------|----------|
| `/hbi-deploy` | Deploy HBI to ephemeral environment | ~7 minutes |
| `/hbi-setup-for-dev` | Setup local development environment | ~30 seconds |
| `/hbi-enable-flags` | Enable Kessel feature flags | ~5 seconds |
| `/hbi-verify-setup` | Verify deployment is healthy | ~10 seconds |
| `/hbi-cleanup` | Remove ephemeral namespace | ~30 seconds |

### Helper Commands

| Command | Purpose |
|---------|---------|
| `/hbi-deploy-and-test` | Deploy + setup + run tests (all-in-one) |
| `/hbi-doctor` | Health check development environment |
| `/hbi-api-groups` | Query groups API |
| `/hbi-api-hosts` | Query hosts API |

## Step-by-Step Instructions

### Step 1: Deploy HBI Services

Deploy HBI and all dependencies (Kessel, RBAC v2, Kafka, databases) to ephemeral environment:

```bash
/hbi-deploy --duration 24h
```

**What this does:**
- ✅ Checks prerequisites (oc, bonfire, kubectl)
- ✅ Logs into ephemeral cluster
- ✅ Reserves a new namespace (or uses existing)
- ✅ Deploys HBI, Kessel, RBAC v2, Kafka, databases
- ✅ Creates demo data (users, hosts, connectors)
- ✅ Verifies all pods are running

**Expected output:**
```
✓ Deployment completed successfully!

Namespace: ephemeral-abc123

Services Deployed:
  - Host Inventory (API + MQ service)
  - Kessel Inventory API
  - Kessel Relations API (SpiceDB)
  - RBAC v2 Service
  - Kafka + Zookeeper
  - PostgreSQL (HBI, RBAC, Kessel databases)
  - Unleash (Feature Flags)

Next Steps:
  Run '/hbi-setup-for-dev' to configure local development environment
```

**Duration options:**
- `--duration 4h` - Short testing session
- `--duration 24h` - Full day of development
- `--duration 335h` - Default (2 weeks)

### Step 2: Setup Local Development Environment

Configure port-forwarding, database credentials, and local files:

```bash
/hbi-setup-for-dev
```

**What this does:**
- ✅ Verifies namespace exists and is healthy
- ✅ Checks all required pods are running
- ✅ Sets up port-forwarding (12 services)
- ✅ Retrieves database credentials from Kubernetes secrets
- ✅ Updates `.env` file with credentials
- ✅ Updates `/etc/hosts` with Kafka bootstrap server

**Expected output:**
```
✓ Development Environment Setup Complete!

Namespace: ephemeral-abc123

Port Forwards Active:
  - Host Inventory API:     http://localhost:8000
  - RBAC Service:           http://localhost:8111
  - Kessel Inventory API:   http://localhost:8222
  - Kessel Relations API:   http://localhost:8333
  - Kafka Bootstrap:        localhost:9092, localhost:29092
  - Feature Flags:          http://localhost:4242
  - HBI Database:           localhost:5432
  - RBAC Database:          localhost:5433
  - Kessel Database:        localhost:5434

Updated Files:
  - .env (database credentials)
  - /etc/hosts (Kafka bootstrap server)
```

**Important**: Keep the terminal with port-forwards running. They will stop if you close the terminal.

### Step 3: Enable Feature Flags

Enable Kessel-related feature flags in Unleash:

```bash
/hbi-enable-flags
```

**What this does:**
- ✅ Connects to Unleash (localhost:4242)
- ✅ Logs in as admin
- ✅ Creates/enables 6 Kessel feature flags
- ✅ Verifies flags are active in dev + prod environments

**Flags enabled:**
1. `hbi.api.kessel-phase-1` - Kessel Phase 1 integration
2. `hbi.api.kessel-groups` - RBAC v2 Groups support
3. `hbi.api.kessel-force-single-checks-for-bulk` - Bulk operation optimization
4. `hbi.api.kessel-workspace-migration` - Workspace migration
5. `hbi.kessel-migration` - General Kessel migration
6. `hbi.api.kessel-host-migration` - Host migration

**To verify flags:**
```bash
/hbi-enable-flags --list
```

### Step 4: Verify Setup

Confirm everything is working:

```bash
/hbi-verify-setup
```

**This checks:**
- ✅ Namespace exists
- ✅ Pods are running
- ✅ Port forwards are active
- ✅ APIs are responding (HTTP health checks)
- ✅ Database connectivity
- ✅ Feature flags are enabled

**Expected result:**
```
✅ All checks passed!
Your ephemeral environment is fully functional.
```

### Step 5: Run Tests

Your environment is now ready for testing:

```bash
# Run all tests
pipenv run pytest tests/

# Run specific test file
pipenv run pytest tests/test_api_groups.py -v

# Run tests matching pattern
pipenv run pytest -k "test_kessel" -v

# Run with coverage
pipenv run pytest --cov=. tests/
```

## Verification

### Check Namespace Status

```bash
# View namespace details
bonfire namespace describe

# List all pods
kubectl get pods -n <namespace>

# Check specific service
kubectl logs -n <namespace> deployment/host-inventory-service
```

### Test API Endpoints

```bash
# HBI Health
curl http://localhost:8000/health

# Get hosts
curl http://localhost:8000/api/inventory/v1/hosts

# Get groups
curl http://localhost:8000/api/inventory/v1/groups
```

### Access Web UIs

| Service | URL | Credentials |
|---------|-----|-------------|
| Unleash | http://localhost:4242 | admin / unleash4all |
| OpenShift Console | Check bonfire output | SSO login |

### View Database

```bash
# HBI Database
export $(cat .env | grep INVENTORY_DB | xargs)
psql -h localhost -p 5432 -U $INVENTORY_DB_USER -d $INVENTORY_DB_NAME

# RBAC Database
psql -h localhost -p 5433 -U <user> -d rbac

# Kessel Database
psql -h localhost -p 5434 -U <user> -d kessel-inventory
```

Credentials are in `tmp/ephemeral_db_credentials_<timestamp>.log`.

## Common Tasks

### Re-setup on Different Machine

If you deployed on machine A but want to develop on machine B:

```bash
# On Machine B:
# 1. Login to cluster
oc login --token=<token> --server=<server>

# 2. Switch to the namespace
oc project ephemeral-abc123

# 3. Setup local environment
/hbi-setup-for-dev --namespace ephemeral-abc123
```

### Restart Port Forwards

If port forwards die:

```bash
# Kill existing forwards
pkill -f "kubectl port-forward"

# Re-run setup
/hbi-setup-for-dev
```

### Update Code and Test

```bash
# Make code changes
vim api/group.py

# Run tests
pipenv run pytest tests/test_api_groups.py -v

# The hbi-web container auto-reloads code changes!
```

### Check Feature Flag Status

```bash
# List all flags
/hbi-enable-flags --list

# Verify specific flags
/hbi-enable-flags --verify

# Re-enable all flags
/hbi-enable-flags
```

### Extend Namespace Duration

```bash
# Add 12 more hours
bonfire namespace extend --duration 12h
```

## Troubleshooting

### "No active namespace found"

**Problem**: `/hbi-setup-for-dev` can't find namespace

**Solution**:
```bash
# Check if you're logged in
oc whoami

# List your namespaces
bonfire namespace list

# Switch to namespace
oc project ephemeral-<id>
```

### "Port already in use"

**Problem**: Port forwarding fails because port is busy

**Solution**:
```bash
# Find what's using the port
lsof -i :8000

# Kill the process
kill -9 <PID>

# Or use different ports (edit scripts)
```

### "Pods are not running"

**Problem**: Some pods are in CrashLoopBackOff or Pending

**Solution**:
```bash
# Check pod status
kubectl get pods -n <namespace>

# Check pod logs
kubectl logs -n <namespace> <pod-name>

# Describe pod for events
kubectl describe pod -n <namespace> <pod-name>

# If persistent, redeploy
/hbi-cleanup
/hbi-deploy
```

### "Database connection failed"

**Problem**: Can't connect to database

**Solution**:
```bash
# Check port forward is running
ps aux | grep "port-forward.*5432"

# Check .env file has credentials
cat .env | grep INVENTORY_DB

# Re-get credentials
/hbi-setup-for-dev
```

### "Unleash is not accessible"

**Problem**: Feature flag commands fail

**Solution**:
```bash
# Check port forward
ps aux | grep "port-forward.*4242"

# Test Unleash health
curl http://localhost:4242/health

# Re-setup if needed
/hbi-setup-for-dev
```

### "Tests fail with 403 Forbidden"

**Problem**: Tests return permission errors

**Solution**:
```bash
# Feature flags might not be enabled
/hbi-enable-flags

# Check namespace has RBAC properly configured
kubectl get secret rbac-db -n <namespace>

# Try running test without --skip-data-setup
pipenv run pytest tests/test_api_groups.py -v
```

## Cleanup

### Release Namespace When Done

```bash
# Cleanup command (recommended)
/hbi-cleanup

# Or manually
bonfire namespace release <namespace>

# Force cleanup if stuck
bonfire namespace release <namespace> --force
```

### Kill Port Forwards

```bash
# Kill all kubectl port-forwards
pkill -f "kubectl port-forward"

# Or find and kill specific ones
ps aux | grep "kubectl port-forward"
kill <PID>
```

### Clean Local Files

```bash
# Remove credentials logs
rm -f tmp/ephemeral_db_credentials_*.log
rm -f tmp/ephemeral_ports_*.log

# Backup .env
mv .env .env.backup

# Note: Don't commit .env or tmp/ directory!
```

## Best Practices

### 1. Namespace Naming

Bonfire automatically generates namespace names like `ephemeral-abc123`. Note it down for reference.

### 2. Resource Conservation

- Use `--duration 4h` for quick testing
- Release namespace when done: `/hbi-cleanup`
- Don't leave namespaces running overnight

### 3. Git Workflow

```bash
# Never commit these files:
.env
tmp/
*.log

# They are already in .gitignore
```

### 4. Collaboration

If sharing a namespace with teammates:

```bash
# Share the namespace name
echo $NAMESPACE

# Each person runs their own /hbi-setup-for-dev
# But deployment happens only once
```

### 5. Testing

```bash
# Run linters before committing
make style

# Run tests before pushing
pipenv run pytest tests/

# Check coverage
pipenv run pytest --cov=. tests/
```

## Architecture Overview

### Services Deployed

```
┌─────────────────────────────────────────────────┐
│           Ephemeral Namespace                   │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌─────────────┐  ┌──────────────┐            │
│  │ HBI Service │  │ HBI MQ       │            │
│  │ (API)       │  │ (Workers)    │            │
│  └──────┬──────┘  └──────┬───────┘            │
│         │                │                     │
│         ↓                ↓                     │
│  ┌──────────────────────────┐                 │
│  │  PostgreSQL (HBI DB)     │                 │
│  └──────────────────────────┘                 │
│                                                │
│  ┌─────────────┐  ┌──────────────┐            │
│  │ Kessel      │  │ Kessel       │            │
│  │ Inventory   │  │ Relations    │            │
│  │ API         │  │ (SpiceDB)    │            │
│  └──────┬──────┘  └──────┬───────┘            │
│         │                │                     │
│         ↓                ↓                     │
│  ┌──────────────┐ ┌─────────────┐             │
│  │ Kessel DB    │ │ SpiceDB     │             │
│  └──────────────┘ └─────────────┘             │
│                                                │
│  ┌─────────────┐  ┌──────────────┐            │
│  │ RBAC v2     │  │ PostgreSQL   │            │
│  │ Service     │──│ (RBAC DB)    │            │
│  └─────────────┘  └──────────────┘            │
│                                                │
│  ┌─────────────┐  ┌──────────────┐            │
│  │ Kafka +     │  │ Unleash      │            │
│  │ Zookeeper   │  │ (Feat Flags) │            │
│  └─────────────┘  └──────────────┘            │
└─────────────────────────────────────────────────┘
         ↑                    ↑
         │ Port Forwards      │
         └────────────────────┘
              localhost
```

### Port Mapping

| Service | Remote Port | Local Port |
|---------|-------------|------------|
| HBI API | 8000 | 8000 |
| RBAC Service | 8000 | 8111 |
| Kessel Inventory | 8000 | 8222 |
| Kessel Relations | 9000 | 9000 |
| SpiceDB gRPC | 8000 | 8333 |
| Kafka | 9092 | 9092, 29092 |
| Kafka Connect | 8083 | 8083 |
| Unleash | 4242 | 4242 |
| HBI Database | 5432 | 5432 |
| RBAC Database | 5432 | 5433 |
| Kessel Database | 5432 | 5434 |

## Additional Resources

### Documentation

- [CLAUDE.md](../CLAUDE.md) - Project overview and conventions
- [CLAUDE.local.md](../CLAUDE.local.md) - Session-specific work logs
- [README.md](../README.md) - General project README

### Command Documentation

- `.claude/commands/hbi-deploy.md` - Deploy command details
- `.claude/commands/hbi-setup-for-dev.md` - Setup command details
- `.claude/commands/hbi-enable-flags.md` - Feature flags command details
- `.claude/commands/hbi-verify-setup.md` - Verification command details

### Scripts

- `.claude/deployer/deploy-ephemeral.sh` - Main deployment script
- `.claude/deployer/setup-for-dev.sh` - Local setup script
- `.claude/scripts/enable-feature-flags.sh` - Feature flag management
- `docs/set_hbi_rbac_ports.sh` - Port forwarding setup
- `docs/get_hbi_rbac_db_creds.sh` - Credential retrieval

## Getting Help

### Claude Code Skills

If you're using Claude Code, these skills are available:

```bash
/hbi-deploy          # Deploy HBI
/hbi-setup-for-dev   # Setup local environment
/hbi-enable-flags    # Enable feature flags
/hbi-verify-setup    # Verify deployment
/hbi-cleanup         # Cleanup namespace
/hbi-doctor          # Health check
```

Type `/help` in Claude Code for full list.

### Manual Script Execution

You can also run scripts directly:

```bash
# Deploy
.claude/deployer/deploy-ephemeral.sh --duration 24h

# Setup for dev
.claude/deployer/setup-for-dev.sh

# Enable flags
.claude/scripts/enable-feature-flags.sh

# Verify
.claude/scripts/verify-ephemeral-setup.sh
```

### Support

- **Slack**: #insights-host-inventory
- **Issues**: https://github.com/RedHatInsights/insights-host-inventory/issues
- **Docs**: https://consoledot.pages.redhat.com/docs/dev/services/inventory.html

---

**Happy Developing! 🚀**
