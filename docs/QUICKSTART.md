# HBI Ephemeral Deployment - Quick Start

Get HBI running in an ephemeral environment in 5 minutes.

## Prerequisites

```bash
# Install tools (one time)
pip install crc-bonfire
brew install jq  # or apt-get install jq on Linux

# Login to ephemeral cluster
oc login --token=<get-from-oauth-url> --server=https://api.crc-eph.r9lp.p1.openshiftapps.com:6443
```

Get token from: https://oauth-openshift.apps.crc-eph.r9lp.p1.openshiftapps.com/oauth/token/request

## Three Commands to Deploy

```bash
# 1. Deploy services (~7 minutes)
/hbi-deploy --duration 24h

# 2. Setup local environment (~30 seconds)
/hbi-setup-for-dev

# 3. Enable feature flags (~5 seconds)
/hbi-enable-flags
```

## Verify It Works

```bash
# Check health
curl http://localhost:8000/health

# Run tests
pipenv run pytest tests/test_api_groups.py -v
```

## When You're Done

```bash
# Cleanup
/hbi-cleanup
```

## What You Get

| Service | URL |
|---------|-----|
| HBI API | http://localhost:8000 |
| RBAC Service | http://localhost:8111 |
| Kessel Inventory | http://localhost:8222 |
| Unleash UI | http://localhost:4242 (admin/unleash4all) |
| Databases | localhost:5432 (HBI), 5433 (RBAC), 5434 (Kessel) |

## Common Issues

**"No namespace found"**
```bash
bonfire namespace list  # Check your namespaces
oc project ephemeral-<id>  # Switch to namespace
```

**"Port forwarding failed"**
```bash
pkill -f "kubectl port-forward"  # Kill old forwards
/hbi-setup-for-dev  # Re-run setup
```

**"Tests fail"**
```bash
/hbi-enable-flags --verify  # Check feature flags
/hbi-verify-setup  # Full health check
```

## Full Documentation

See [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) for complete documentation.

---

**Questions?** Check Slack #insights-host-inventory
