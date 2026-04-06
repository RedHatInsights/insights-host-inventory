# PR 1: Core HBI Ephemeral Infrastructure

**Part 1 of 7** in the HBI Deployment Infrastructure Series

This PR adds the foundational infrastructure for deploying HBI (Host-Based Inventory) with Kessel integration to ephemeral Kubernetes environments.

## What This PR Does

Provides automated deployment scripts that:
- Deploy HBI to ephemeral namespaces via Bonfire
- Configure Kessel integration (inventory and relations APIs)
- Seed RBAC users for testing
- Handle deployment retries and validation
- Enable the `/hbi-deploy` slash command

## Why This Matters

Before this PR, developers had to:
- Manually deploy using complex bonfire commands
- Manually configure Kessel services
- Manually seed test users in RBAC
- Remember specific deployment parameters

After this PR, developers can:
- Run `/hbi-deploy` to get a fully configured environment
- Automatic retry logic handles transient failures
- Consistent deployment configuration across team

## Files Added (10 files, 2,204 lines)

### Core Deployment Scripts
- **`.claude/deployer/bonfire-deploy.sh`** (342 lines)
  - Bonfire deployment automation with retry logic
  - Kessel app configuration and health checks
  - RBAC user seeding orchestration
  - Deployment validation

- **`.claude/deployer/deploy-ephemeral.sh`** (311 lines)
  - Main deployment orchestration script
  - Namespace creation and configuration
  - Component deployment sequencing
  - Status reporting

### RBAC User Management
- **`.claude/deployer/data/rbac_users_data.json`** (261 lines)
  - Test user definitions (insights-inventory-qe, insights-qa, etc.)
  - Org IDs and account numbers
  - User role configurations

- **`.claude/deployer/scripts/rbac_load_users.sh`** (115 lines)
  - Loads users into Keycloak
  - User authentication setup

- **`.claude/deployer/scripts/rbac_seed_users.sh`** (87 lines)
  - Seeds users to RBAC service
  - Permission assignment

### Documentation
- **`docs/DEPLOYMENT_GUIDE.md`** (699 lines)
  - Comprehensive deployment guide
  - Architecture diagrams
  - Troubleshooting tips
  - Configuration reference

- **`.claude/deployer/README.md`** (254 lines)
  - Deployer directory overview
  - Script descriptions
  - Usage examples

- **`.claude/commands/hbi-deploy.md`** (118 lines)
  - `/hbi-deploy` command documentation
  - Options and examples
  - Expected output

### Configuration
- **`.claude/deployer/.gitignore`** (7 lines)
  - Ignore local logs and credentials

- **`.gitignore`** (10 lines added)
  - Ignore deployment artifacts

## Commands Enabled

### `/hbi-deploy`

Deploys HBI with Kessel to a new ephemeral namespace.

**Usage:**
```bash
/hbi-deploy
/hbi-deploy --duration 24h
/hbi-deploy --duration 10h --force
```

**What it does:**
1. Creates ephemeral namespace (default: 335h duration)
2. Deploys HBI, Kessel inventory, Kessel relations, RBAC
3. Seeds test users to RBAC
4. Validates all pods are running
5. Outputs namespace name and credentials

## Dependencies

**None** - This PR must be merged first as it provides the foundation for all subsequent PRs.

## What's Next

After this PR is merged, subsequent PRs will add:
- **PR 2**: Local development setup (port forwards, .env configuration)
- **PR 3**: Environment verification tools
- **PR 4**: Feature flag management
- **PR 5**: Testing infrastructure
- **PR 6**: Cleanup utilities
- **PR 7**: Configuration examples

## Testing

To test this PR locally:

```bash
# Checkout this branch
git checkout pr1-eens-core-infrastructure

# Run the deployment
.claude/deployer/deploy-ephemeral.sh

# Verify namespace was created
bonfire namespace list | grep $(whoami)

# Check deployed pods
kubectl get pods -n <namespace>
```

Expected result: Ephemeral namespace with all HBI and Kessel services running.

## Technical Details

### Deployment Architecture

```
deploy-ephemeral.sh (main orchestrator)
    ├── bonfire-deploy.sh (bonfire wrapper)
    │   ├── bonfire deploy (Kubernetes resources)
    │   ├── Health checks (wait for pods)
    │   └── rbac_seed_users.sh (RBAC setup)
    │       └── rbac_load_users.sh (Keycloak)
    └── Status reporting
```

### Key Features

**Retry Logic**: Automatically retries failed deployments (up to 3 attempts)

**Health Checks**: Validates all pods reach Running state before completing

**Kessel Integration**: Configures both inventory and relations APIs

**RBAC Seeding**: Pre-loads test users for immediate testing

**Logging**: Comprehensive logging to `tmp/` directory

### Configuration Options

- `--duration`: Namespace lifetime (default: 335h ≈ 14 days)
- `--force`: Skip confirmation prompts
- `--namespace`: Use existing namespace instead of creating new one

## Rollback Plan

If issues are found after merge:
1. This PR only adds new files, doesn't modify existing code
2. Safe to revert without impacting other functionality
3. All changes are in `.claude/` directory (not production code)

## Related Work

- Based on patterns from `insights-service-deployer`
- Integrates with existing `bonfire` deployment tooling
- Compatible with current HBI deployment processes

## Questions for Reviewers

1. Is the retry logic sufficient for transient failures?
2. Should default namespace duration be configurable via environment variable?
3. Are the RBAC test users appropriate for all environments?

---

**Merge Sequence**: Must be merged **first** before PR 2-7
**Size**: 10 files, 2,204 lines (majority is documentation)
**Risk**: Low - additive only, no existing code modified
