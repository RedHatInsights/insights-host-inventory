# HBI Ephemeral Deployment Automation

Automated deployment of Host Inventory with Kessel to ephemeral environments.

## Overview

This directory contains scripts extracted from `insights-service-deployer` to enable Claude Code to automate ephemeral environment deployments directly from the HBI repository.

## Structure

```
.claude/deployer/
├── deploy-hbi-and-dependencies.sh      # Main orchestration script
├── bonfire-deploy.sh         # Bonfire deployment logic
├── scripts/
│   ├── rbac_load_users.sh   # Load users into Keycloak
│   └── rbac_seed_users.sh   # Seed users to RBAC
├── data/
│   └── rbac_users_data.json # Test user data
└── README.md                 # This file
```

## Usage

### Via Claude Code

```bash
/hbi-deploy
/hbi-deploy --duration 24h --force
```

### Direct Execution

```bash
cd .claude/deployer
./deploy-hbi-and-dependencies.sh --duration 335h
./deploy-hbi-and-dependencies.sh --force
```

## What It Does

1. **Prerequisites Check** - Validates oc, bonfire, kubectl installed
2. **Login to Cluster** - Authenticates to ephemeral cluster
3. **Reserve Namespace** - Creates or uses existing ephemeral namespace
4. **Deploy Services** - Deploys HBI, Kessel, RBAC with bonfire
5. **Setup Demo Data** - Creates connectors, users, and sample hosts

## Prerequisites

**Required Tools:**
- `oc` - OpenShift CLI
- `bonfire` - Red Hat's ephemeral environment tool
- `kubectl` - Kubernetes CLI
- `jq` - JSON processor

**Required Configuration:**
- Ephemeral cluster access (token + server URL)

**Environment Variables:**
- `EPHEMERAL_TOKEN` - Auth token (or use `oc whoami -t`)
- `EPHEMERAL_SERVER` - Cluster server URL (or use `oc whoami --show-server`)

## Components

### deploy-hbi-and-dependencies.sh

Main orchestration script that:
- Manages the deployment workflow
- Handles pre/post deployment tasks
- Updates local configuration files
- Provides colored output and progress tracking

### bonfire-deploy.sh

Bonfire-specific deployment logic:
- Deploys HBI with all parameters
- Sets up Kessel Inventory and Relations
- Configures RBAC v2 with Kafka consumer
- Creates demo data (users, hosts, connectors)
- Applies SpiceDB schema

### scripts/

Supporting scripts from insights-service-deployer:
- `rbac_load_users.sh` - Imports users from JSON into Keycloak
- `rbac_seed_users.sh` - Seeds users into RBAC database

### data/

Test data:
- `rbac_users_data.json` - User definitions for ephemeral testing

## Services Deployed

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

## Options

```bash
--duration DURATION   Namespace reservation duration (default: 335h)
--force               Use existing namespace without prompting
--help                Show help message
```

**Deploy Arguments** (passed to bonfire):
```bash
[template_ref]   Git ref for host-inventory deploy template
[image]          Custom host-inventory image
[tag]            Custom image tag
[schema_file]    Path to local SpiceDB schema file
```

## Examples

**Basic deployment:**
```bash
./deploy-hbi-and-dependencies.sh
```

**With custom duration:**
```bash
./deploy-hbi-and-dependencies.sh --duration 48h
```

**Force use existing namespace:**
```bash
./deploy-hbi-and-dependencies.sh --force
```

**With custom image:**
```bash
./deploy-hbi-and-dependencies.sh --force main quay.io/myrepo/inventory v1.0
```

## Cleanup

When done with the ephemeral environment:

```bash
bonfire namespace release <namespace>
```

## Troubleshooting

**"EPHEMERAL_TOKEN is not set"**
- Login first: `oc login --token=<token> --server=<server>`
- Get token from: https://oauth-openshift.apps.crc-eph.r9lp.p1.openshiftapps.com/oauth/token/request

**"Failed to reserve namespace"**
- Check bonfire is installed: `bonfire --version`
- Check cluster access: `oc whoami`

**"Deployment failed"**
- Check bonfire namespace: `bonfire namespace describe`
- Check pod logs: `oc logs <pod-name>`
- Release and retry: `bonfire namespace release <namespace>`

## Differences from insights-service-deployer

**What's Included:**
- Bonfire deployment logic
- Demo data setup
- User/connector creation
- All essential deployment parameters

**What's Excluded:**
- Unleash image building (uses pre-built image)
- Debezium configuration downloads (uses URLs)
- Optional deployment modes (only deploy_with_hbi_demo)

**Why Self-Contained:**
- No dependency on external insights-service-deployer repo
- Easier to version control with HBI
- Claude Code can manage everything in one place
- Simpler maintenance and updates

## Updating

To update scripts when insights-service-deployer changes:

1. **Compare changes:**
   ```bash
   diff .claude/deployer/bonfire-deploy.sh \
        /path/to/insights-service-deployer/deploy.sh
   ```

2. **Update functions as needed** (manually or with Claude)

3. **Test in ephemeral environment**

## Integration with Claude Code

The `/hbi-deploy` slash command uses these scripts:
- Defined in: `.claude/commands/hbi-deploy.md`
- Executes: `.claude/deployer/deploy-hbi-and-dependencies.sh`
- Provides: Interactive deployment with progress tracking

## Related Documentation

- `/hbi-deploy` command: `.claude/commands/hbi-deploy.md`
- Main project README: `README.md`
