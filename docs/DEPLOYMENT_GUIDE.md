# HBI Ephemeral Environment Deployment Guide

This guide helps you deploy Host-Based Inventory (HBI) to an ephemeral Kubernetes environment for development and testing.

## Table of Contents

- [Quick Start](#quick-start)
- [Prerequisites](#prerequisites)
- [Deployment](#deployment)
- [Verification](#verification)
- [Common Tasks](#common-tasks)
- [Troubleshooting](#troubleshooting)
- [Cleanup](#cleanup)

## Quick Start

```bash
# Deploy HBI to ephemeral environment
/hbi-deploy --duration 24h
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

### Cluster Access

1. **Get ephemeral cluster token**:
   - Visit: https://oauth-openshift.apps.crc-eph.r9lp.p1.openshiftapps.com/oauth/token/request
   - Copy the token

2. **Log in to cluster**:
   ```bash
   oc login --token=<your-token> --server=https://api.crc-eph.r9lp.p1.openshiftapps.com:6443
   ```

## Deployment

### Deploy HBI Services

Deploy HBI and all dependencies (Kessel, RBAC v2, Kafka, databases) to ephemeral environment:

```bash
/hbi-deploy --duration 24h
```

**What this does:**
- Checks prerequisites (oc, bonfire, kubectl)
- Logs into ephemeral cluster
- Reserves a new namespace (or uses existing)
- Deploys HBI, Kessel, RBAC v2, Kafka, databases
- Creates demo data (users, hosts, connectors)
- Verifies all pods are running

**Duration options:**
- `--duration 4h` - Short testing session
- `--duration 24h` - Full day of development
- `--duration 335h` - Default (2 weeks)

**Options:**
- `--force` - Use existing namespace without prompting
- `--help` - Show all options

### Services Deployed

| Service | Description |
|---------|-------------|
| Host Inventory | API + MQ service |
| Kessel Inventory API | Inventory resource management |
| Kessel Relations API | SpiceDB authorization |
| RBAC v2 Service | Role-based access control |
| Kafka + Zookeeper | Message streaming |
| PostgreSQL | HBI, RBAC, Kessel databases |
| Unleash | Feature flags |

### Demo Data

- Test users from `rbac_users_data.json`
- 10 sample hosts (org_id: 12345)
- Kafka connectors (migration + outbox)
- SpiceDB schema

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

## Common Tasks

### Extend Namespace Duration

```bash
bonfire namespace extend --duration 12h
```

### Run Tests

```bash
# Run all tests
pipenv run pytest tests/

# Run specific test file
pipenv run pytest tests/test_api_groups.py -v

# Run with coverage
pipenv run pytest --cov=. tests/
```

## Troubleshooting

### "EPHEMERAL_TOKEN is not set"

**Solution**:
```bash
oc login --token=<token> --server=<server>
```

Or get token from: https://oauth-openshift.apps.crc-eph.r9lp.p1.openshiftapps.com/oauth/token/request

### "Failed to reserve namespace"

**Solution**:
```bash
bonfire --version    # Check bonfire is installed
oc whoami            # Check cluster access
```

### "Pods are not running"

**Solution**:
```bash
# Check pod status
kubectl get pods -n <namespace>

# Check pod logs
kubectl logs -n <namespace> <pod-name>

# Describe pod for events
kubectl describe pod -n <namespace> <pod-name>

# If persistent, release and redeploy
bonfire namespace release <namespace>
/hbi-deploy
```

### "Deployment failed"

**Solution**:
```bash
bonfire namespace describe
kubectl logs -n <namespace> <pod-name>
bonfire namespace release <namespace>
```

## Cleanup

### Release Namespace

```bash
bonfire namespace release <namespace>

# Force cleanup if stuck
bonfire namespace release <namespace> --force
```

## Architecture Overview

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
```

## Additional Resources

- [CLAUDE.md](../CLAUDE.md) - Project overview and conventions
- [README.md](../README.md) - General project README
- `.claude/commands/hbi-deploy.md` - Deploy command details
- `.claude/deployer/deploy-hbi-and-dependencies.sh` - Main deployment script
- `.claude/deployer/bonfire-deploy.sh` - Bonfire deployment logic

## Getting Help

- **Slack**: #insights-host-inventory
- **Issues**: https://github.com/RedHatInsights/insights-host-inventory/issues
- **Docs**: https://consoledot.pages.redhat.com/docs/dev/services/inventory.html
