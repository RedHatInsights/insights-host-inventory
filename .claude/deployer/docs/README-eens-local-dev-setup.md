# PR 2: Local Development Environment Setup

**Part 2 of 7** in the HBI Deployment Infrastructure Series

This PR adds automated local development setup scripts that configure port-forwarding and environment variables for working with ephemeral HBI deployments.

## What This PR Does

Provides automated local setup that:
- Establishes port-forwards for all 12 services (HBI, RBAC, Kessel, DBs, Kafka, Unleash)
- Generates `.env` file with database credentials and Unleash tokens
- Validates port-forward health
- Provides quick reference documentation
- Enables the `/hbi-setup-for-dev` slash command

## Why This Matters

Before this PR, developers had to:
- Manually run 12 separate `kubectl port-forward` commands
- Manually extract database credentials from secrets
- Remember which ports map to which services
- Recreate `.env` file for each deployment

After this PR, developers can:
- Run `/hbi-setup-for-dev` to configure everything automatically
- Get validated port-forwards with health checks
- Automatically updated `.env` with correct credentials
- Quick reference for all service ports

## Files Added (4 files, 867 lines)

### Setup Script
- **`.claude/deployer/setup-for-dev.sh`** (566 lines)
  - Port-forward automation for 12 services
  - Database credential extraction from K8s secrets
  - Unleash token extraction and configuration
  - `.env` file generation and updates
  - Port-forward health validation
  - Automatic retry logic for failed forwards

### Documentation
- **`.claude/commands/hbi-setup-for-dev.md`** (138 lines)
  - `/hbi-setup-for-dev` command documentation
  - Usage examples and options
  - Port mapping reference
  - Troubleshooting guide

- **`.claude/deployer/QUICK-REFERENCE.md`** (102 lines)
  - Port-to-service mapping table
  - Database connection details
  - Common kubectl commands
  - Quick troubleshooting tips

- **`.claude/SETTINGS_LOCAL.md`** (61 lines)
  - Local development configuration guide
  - Environment variable reference
  - VSCode/Cursor integration tips

## Commands Enabled

### `/hbi-setup-for-dev`

Sets up local development environment for an ephemeral namespace.

**Usage:**
```bash
/hbi-setup-for-dev
/hbi-setup-for-dev --namespace ephemeral-abc123
```

**What it does:**
1. Detects active namespace (or uses provided one)
2. Kills existing port-forwards for clean slate
3. Starts 12 port-forwards to K8s services
4. Extracts database credentials from secrets
5. Extracts Unleash token from secret
6. Updates `.env` file with all credentials
7. Validates port-forward health
8. Outputs connection details

**Port Forwards Established:**
- `8000` - HBI API
- `8111` - RBAC service
- `8222` - Kessel inventory API
- `8333` - Kessel relations API
- `9000` - Kessel inventory gRPC
- `5432` - HBI PostgreSQL database
- `5433` - RBAC PostgreSQL database
- `5434` - Kessel inventory PostgreSQL database
- `9092` - Kafka broker
- `29092` - Kafka broker (alternate)
- `8083` - Kafka Connect API
- `4242` - Unleash feature flags

## Dependencies

**Requires PR 1** - Core infrastructure must be deployed first.

This PR works with ephemeral namespaces created by PR 1's deployment scripts.

## What's Next

After this PR is merged, subsequent PRs will add:
- **PR 3**: Environment verification tools
- **PR 4**: Feature flag management
- **PR 5**: Testing infrastructure
- **PR 6**: Cleanup utilities
- **PR 7**: Configuration examples

## Testing

To test this PR locally:

```bash
# Checkout this branch
git checkout pr2-eens-local-dev-setup

# Deploy an ephemeral namespace first (using PR 1)
.claude/deployer/deploy-ephemeral.sh

# Run the local setup
.claude/deployer/setup-for-dev.sh

# Verify port-forwards are running
kubectl get pods -n <namespace>
lsof -i :8000,8111,8222,8333,5432,5433,5434,9092,4242

# Check .env file was created/updated
cat .env | grep -E "INVENTORY_DB|UNLEASH"
```

Expected result: 12 port-forwards running, `.env` file populated with credentials.

## Technical Details

### Port-Forward Management

The script uses background processes with automatic PID tracking:
```bash
kubectl port-forward svc/host-inventory-service 8000:8000 -n $NAMESPACE &
```

### Credential Extraction

Database credentials are extracted from K8s secrets:
```bash
kubectl get secret host-inventory-db -n $NAMESPACE \
  -o jsonpath='{.data.db\.user}' | base64 -d
```

Unleash token extraction:
```bash
kubectl get secret unleash-proxy -n $NAMESPACE \
  -o jsonpath='{.data.cdappconfig\.json}' | base64 -d | \
  python3 -c "import sys, json; print(json.load(sys.stdin)['featureFlags']['clientAccessToken'])"
```

### Environment File Updates

The script intelligently updates `.env`:
- Creates file if it doesn't exist
- Updates existing values if they've changed
- Preserves other environment variables
- Uses `sed` for in-place updates on both macOS and Linux

### Health Validation

After starting port-forwards, validates connectivity:
```bash
# Wait for processes to initialize
sleep 3

# Check processes are running
ps aux | grep "kubectl port-forward"

# Validate specific ports
lsof -i :8000 >/dev/null 2>&1 && echo "✓ HBI API ready"
```

### Key Features

**Smart Namespace Detection**: Auto-detects active namespace or accepts explicit parameter

**Clean Slate**: Kills existing port-forwards before starting new ones

**Retry Logic**: Automatically retries failed port-forwards

**Unleash Integration**: Extracts namespace-specific Unleash token (critical for feature flags)

**Cross-Platform**: Works on macOS and Linux (different `sed` syntax handling)

## Rollback Plan

If issues are found after merge:
1. This PR only adds new files, doesn't modify existing code
2. Safe to revert without impacting other functionality
3. All changes are in `.claude/` directory (not production code)

## Related Work

- Depends on PR 1 (core deployment infrastructure)
- Enables PR 3 (verification tools need port-forwards)
- Enables PR 5 (testing needs local environment setup)
- Integrates with existing `bonfire` deployment tooling

## Questions for Reviewers

1. Is the port-forward retry logic sufficient for transient failures?
2. Should we add health check endpoints (HTTP GET) to validate services are responding?
3. Are the default port numbers (8000, 8111, etc.) acceptable or should they be configurable?

---

**Merge Sequence**: Can merge **after PR 1** (requires deployed namespace to exist)
**Size**: 4 files, 867 lines (majority is documentation and comments)
**Risk**: Low - additive only, no existing code modified
