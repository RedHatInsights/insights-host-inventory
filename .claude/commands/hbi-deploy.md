# /hbi-deploy - Deploy HBI with Kessel to Ephemeral Environment

Deploy Host Inventory with Kessel, RBAC v2, and all dependencies to an ephemeral namespace.

## What This Command Does

1. **Prerequisites Check** - Validates oc, bonfire, kubectl installed
2. **Login to Cluster** - Authenticates to ephemeral cluster
3. **Reserve Namespace** - Creates or uses existing ephemeral namespace
4. **Deploy Services** - Deploys HBI, Kessel, RBAC with bonfire
5. **Setup Demo Data** - Creates connectors, users, and sample hosts
6. **Verify Deployment** - Checks that all pods are running

## Usage

```bash
/hbi-deploy
/hbi-deploy --duration 24h
/hbi-deploy --force
/hbi-deploy --duration 48h --force
```

## Options

- `--duration DURATION` - Namespace reservation duration (default: 335h)
- `--force` - Use existing namespace without prompting
- `--help` - Show help message

## Prerequisites

**Required Tools:**
- `oc` - OpenShift CLI
- `bonfire` - Red Hat's ephemeral environment tool
- `kubectl` - Kubernetes CLI

**Required Configuration:**
- Ephemeral cluster access (token + server URL)
- Podman (optional - for custom unleash image)

**Environment Variables:**
- `EPHEMERAL_TOKEN` - Auth token (or use `oc whoami -t`)
- `EPHEMERAL_SERVER` - Cluster server URL (or use `oc whoami --show-server`)

Get token from: https://oauth-openshift.apps.crc-eph.r9lp.p1.openshiftapps.com/oauth/token/request

## What Gets Deployed

**Core Services:**
- Host Inventory (API + MQ service)
- Kessel Inventory API
- Kessel Relations API (SpiceDB)
- RBAC v2 Service
- Kafka + Zookeeper
- PostgreSQL (3 databases: HBI, RBAC, Kessel)
- Unleash (Feature Flags)

**Demo Data:**
- Test users from rbac_users_data.json
- 10 sample hosts (org_id: 12345)
- Kafka connectors (migration + outbox)
- SpiceDB schema

## Cleanup

When done with the ephemeral environment:

```bash
bonfire namespace release <namespace>
```

## Troubleshooting

**"EPHEMERAL_TOKEN is not set"**
- Login first: `oc login --token=<token> --server=<server>`
- Or export variables manually

**"Failed to reserve namespace"**
- Check bonfire is installed: `bonfire --version`
- Check cluster access: `oc whoami`

**"Deployment failed"**
- Check bonfire namespace: `bonfire namespace describe`
- Check pod logs: `oc logs <pod-name>`
- Release and retry: `bonfire namespace release <namespace>`

## Implementation

This command uses:
- `.claude/deployer/deploy-hbi-and-dependencies.sh` - Main deployment script
- `.claude/deployer/bonfire-deploy.sh` - Bonfire deployment logic
