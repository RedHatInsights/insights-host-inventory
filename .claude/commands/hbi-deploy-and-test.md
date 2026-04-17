# /hbi-deploy-and-test - Deploy HBI and Run Unit Tests

Deploy HBI to ephemeral environment, enable feature flags, and run unit tests.

## What This Command Does

1. **Check Existing Deployment** - Verifies if HBI is already running and healthy
2. **Deploy HBI (if needed)** - Deploys full environment only if not already running
3. **Setup Local Environment** - Configures port forwards and credentials
4. **Verify Deployment** - Runs final verification checks
5. **Enable Feature Flags** - Enables Kessel feature flags in Unleash
6. **Run Unit Tests** - Executes `pytest tests/` against ephemeral environment

**Smart Deployment**: If a healthy deployment already exists, it skips deployment and goes straight to testing, saving ~7 minutes.

## Usage

```bash
/hbi-deploy-and-test
/hbi-deploy-and-test --duration 8h
/hbi-deploy-and-test --force
```

## Options

- `--duration DURATION` - Namespace reservation duration (default: 335h)
- `--force` - Use existing namespace without prompting

## What Gets Tested

**Environment Setup:**
- HBI, Kessel, RBAC v2, Kafka, databases deployed
- All services verified healthy
- Port forwards active
- Feature flags enabled

**Feature Flags Enabled:**
- `hbi.api.kessel-phase-1`
- `hbi.api.kessel-groups`
- `hbi.api.kessel-force-single-checks-for-bulk`

**Tests Executed:**
- All unit tests in `tests/` directory
- Tests run against live ephemeral environment
- Uses actual databases, not mocks

## Prerequisites

- Same as `/hbi-deploy`
- Ephemeral cluster access configured
- All required tools installed (oc, bonfire, kubectl)

## Duration

**With fresh deployment:**
- **Health check**: ~5 seconds
- **Deployment**: ~7 minutes
- **Setup**: ~10 seconds
- **Verification**: ~10 seconds
- **Flag configuration**: ~5 seconds
- **Unit tests**: ~5-15 minutes (varies by test suite)
- **Total**: ~15-25 minutes

**With existing healthy deployment:**
- **Health check**: ~5 seconds (detects existing deployment)
- **Skips deployment**: Saves ~7 minutes!
- **Setup**: ~10 seconds
- **Flag configuration**: ~5 seconds
- **Unit tests**: ~5-15 minutes
- **Total**: ~8-18 minutes

## Output

**When existing deployment is healthy:**
```
Step 1: Checking for existing deployment
ℹ️  Found existing namespace: ephemeral-abc123
ℹ️  Verifying deployment health...
✅ Existing deployment is healthy
ℹ️  Skipping deployment, will use existing environment

Step 2: Skipping deployment (using existing environment)
ℹ️  Namespace: ephemeral-abc123

Step 3: Setting up local development environment
✅ Local setup successful

Step 4: Skipping verification (already verified)

Step 5: Enabling Kessel feature flags
✅ All feature flags enabled

Step 6: Running unit tests
🧪 Running: pipenv run pytest tests/
...
✅ All tests passed!
```

**When fresh deployment is needed:**
```
Step 1: Checking for existing deployment
ℹ️  No existing namespace found
ℹ️  Will deploy fresh environment

Step 2: Deploying HBI to ephemeral environment
✅ Deployment successful

Step 3: Setting up local development environment
✅ Local setup successful

Step 4: Verifying deployment
✅ Verification successful

Step 5: Enabling Kessel feature flags
✅ All feature flags enabled

Step 6: Running unit tests
🧪 Running: pipenv run pytest tests/
...
✅ All tests passed!

═══════════════════════════════════════════════════════════
  Test Summary
═══════════════════════════════════════════════════════════

Namespace:      ephemeral-abc123
Duration:       4h
Test Result:    ✅ PASSED
```

## After Tests Complete

**If tests passed:**
```bash
# Cleanup environment
.claude/scripts/remove-ephemeral-namespace.sh <namespace>
```

**If tests failed:**
```bash
# Investigate
kubectl get pods -n <namespace>
kubectl logs -n <namespace> deployment/host-inventory-service

# Cleanup
.claude/scripts/remove-ephemeral-namespace.sh <namespace> --force
```

## Use Cases

### Pre-Commit Validation
```bash
# Before committing code changes
/hbi-deploy-and-test --duration 2h
```

### Pull Request Testing
```bash
# Validate PR changes work in real environment
/hbi-deploy-and-test --duration 4h
```

### Daily Integration Testing
```bash
# Daily automated testing
/hbi-deploy-and-test --duration 8h --force
```

## Differences from Local Testing

**Local Tests (make test):**
- Uses local containers or mocks
- Fast (~2-5 minutes)
- Limited integration testing

**Ephemeral Tests (this command):**
- Uses real services in Kubernetes
- Slower (~15-25 minutes)
- Full integration with Kessel, RBAC v2, Kafka
- Tests against actual deployment configuration

## Troubleshooting

**"Deployment failed"**
- Check cluster access: `oc whoami`
- Check bonfire: `bonfire --version`
- Review deployment logs in output

**"Verification failed"**
- Some pods may still be starting
- Check pod status: `kubectl get pods -n <namespace>`
- Wait and retry verification manually

**"Tests failed"**
- Check test output for specific failures
- Review service logs: `kubectl logs -n <namespace> <pod>`
- Verify feature flags are enabled
- Check database connectivity

**"Feature flags failed to enable"**
- Unleash may not be ready yet
- Port forward to Unleash (4242) may be down
- Check: `curl http://localhost:4242/health`

## Related Commands

- `/hbi-deploy` - Deploy only (no tests)
- `/hbi-verify-setup` - Verify only
- `/hbi-cleanup` - Cleanup environment

## Implementation

This command uses: `.claude/scripts/deploy-and-unit-test.sh`

## Automation Usage

For CI/CD pipelines:

```bash
#!/bin/bash
set -e

# Deploy and test
if .claude/scripts/deploy-and-unit-test.sh --duration 2h --force; then
    echo "✅ All tests passed"
    exit 0
else
    echo "❌ Tests failed"
    # Cleanup happens in script
    exit 1
fi
```
