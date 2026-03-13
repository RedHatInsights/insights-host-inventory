# /hbi-deploy-and-test - Deploy HBI and Run Unit Tests

Deploy HBI to ephemeral environment, enable feature flags, and run unit tests.

## What This Command Does

1. **Deploy HBI** - Deploys full environment to ephemeral namespace
2. **Verify Deployment** - Runs verification checks
3. **Enable Feature Flags** - Enables Kessel feature flags in Unleash
4. **Run Unit Tests** - Executes `pytest tests/` against ephemeral environment

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

The script typically takes:
- **Deployment**: ~7 minutes
- **Verification**: ~10 seconds
- **Flag configuration**: ~5 seconds
- **Unit tests**: ~5-15 minutes (varies by test suite)
- **Total**: ~15-25 minutes

## Output

```
Step 1: Deploying HBI to ephemeral environment
✅ Deployment successful

Step 2: Verifying deployment
✅ Verification successful

Step 3: Enabling Kessel feature flags
✅ All feature flags enabled

Step 4: Running unit tests
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
