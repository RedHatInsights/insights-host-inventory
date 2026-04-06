# PR 3: Environment Verification Tools

**Part 3 of 7** in the HBI Deployment Infrastructure Series

This PR adds automated verification tools that validate ephemeral environment health, service availability, and configuration correctness.

## What This PR Does

Provides automated verification that:
- Checks all K8s pods are running
- Validates port-forwards are active and responsive
- Tests database connectivity
- Verifies Kafka broker availability
- Checks Unleash feature flag service
- Tests RBAC and Kessel API endpoints
- Generates detailed health report
- Enables the `/hbi-verify-setup` slash command

## Why This Matters

Before this PR, developers had to:
- Manually check pod status with kubectl
- Test each service endpoint individually
- Guess why services weren't responding
- Debug port-forward issues without clear diagnostics

After this PR, developers can:
- Run `/hbi-verify-setup` to validate entire environment
- Get comprehensive health report in seconds
- Identify specific service failures quickly
- Verify deployment before starting development

## Files Added (2 files, 345 lines)

### Verification Script
- **`.claude/scripts/verify-ephemeral-setup.sh`** (213 lines)
  - Pod status checks (all deployments)
  - Port-forward validation (12 services)
  - Database connection tests
  - Kafka broker health checks
  - HTTP endpoint tests (HBI, RBAC, Kessel)
  - Unleash feature flag service test
  - Color-coded output (✓ green, ✗ red)
  - Detailed failure diagnostics

### Documentation
- **`.claude/commands/hbi-verify-setup.md`** (132 lines)
  - `/hbi-verify-setup` command documentation
  - Usage examples
  - Output interpretation guide
  - Troubleshooting common failures
  - Expected vs actual state comparison

## Commands Enabled

### `/hbi-verify-setup`

Verifies ephemeral environment is fully operational.

**Usage:**
```bash
/hbi-verify-setup
/hbi-verify-setup --namespace ephemeral-abc123
/hbi-verify-setup --verbose
```

**What it checks:**

1. **Kubernetes Pods** (10+ pods)
   - host-inventory-service
   - host-inventory-mq
   - host-inventory-db
   - rbac-service
   - rbac-db
   - kessel-inventory-api
   - kessel-inventory-db
   - kessel-relations-api
   - kafka-0
   - env-*-featureflags (Unleash)

2. **Port Forwards** (12 ports)
   - Validates processes are running
   - Tests actual connectivity
   - Reports missing forwards

3. **Database Connections** (3 databases)
   - HBI database (5432)
   - RBAC database (5433)
   - Kessel inventory database (5434)
   - Tests with credentials from `.env`

4. **Service Endpoints**
   - GET http://localhost:8000/health (HBI API)
   - GET http://localhost:8111/api/rbac/v1/status/ (RBAC)
   - GET http://localhost:8222/api/inventory/v1beta1/resources/rhel-hosts (Kessel inventory)
   - GET http://localhost:8333/readyz (Kessel relations)
   - GET http://localhost:4242/api/client/features (Unleash)

5. **Kafka Broker**
   - Connects to localhost:9092
   - Lists topics
   - Validates broker metadata

**Output format:**
```
========================================
Verifying Ephemeral Environment: ephemeral-abc123
========================================

[1/6] Checking Kubernetes pods...
✓ host-inventory-service (Running)
✓ host-inventory-mq (Running)
✓ host-inventory-db (Running)
✓ rbac-service (Running)
...

[2/6] Checking port-forwards...
✓ Port 8000 (HBI API)
✓ Port 8111 (RBAC)
✓ Port 5432 (HBI DB)
...

[3/6] Testing database connections...
✓ HBI database (host-inventory)
✓ RBAC database (rbac)
✓ Kessel inventory database (kessel-inventory)

[4/6] Testing service endpoints...
✓ HBI API health endpoint
✓ RBAC status endpoint
✓ Kessel inventory API
✓ Kessel relations API

[5/6] Testing Unleash feature flags...
✓ Unleash service responding

[6/6] Testing Kafka broker...
✓ Kafka broker available
✓ Topics: platform.inventory.events, platform.notifications.ingress

========================================
Environment Status: HEALTHY ✓
========================================
All services are operational and ready for development.
```

## Dependencies

**Requires:**
- **PR 1** - Ephemeral namespace must be deployed
- **PR 2** - Port-forwards must be established

This PR verifies the environment created by PR 1 and configured by PR 2.

## What's Next

After this PR is merged, subsequent PRs will add:
- **PR 4**: Feature flag management
- **PR 5**: Testing infrastructure
- **PR 6**: Cleanup utilities
- **PR 7**: Configuration examples

## Testing

To test this PR locally:

```bash
# Checkout this branch
git checkout pr3-eens-environment-verification

# Prerequisites: Deploy and setup environment
.claude/deployer/deploy-ephemeral.sh
.claude/deployer/setup-for-dev.sh

# Run verification
.claude/scripts/verify-ephemeral-setup.sh

# Test with verbose output
.claude/scripts/verify-ephemeral-setup.sh --verbose

# Test failure detection (stop a port-forward first)
kill $(lsof -t -i:8000)
.claude/scripts/verify-ephemeral-setup.sh
```

Expected result:
- All checks pass when environment is healthy
- Failed checks clearly identified with ✗ red marks
- Helpful error messages for debugging

## Technical Details

### Pod Status Checks

Uses kubectl to verify pod state:
```bash
kubectl get pods -n $NAMESPACE -o json | \
  jq -r '.items[] | select(.status.phase != "Running") | .metadata.name'
```

### Port-Forward Validation

Two-stage validation:
1. Check process exists: `lsof -i :$PORT`
2. Test connectivity: `nc -z localhost $PORT`

### Database Connection Tests

Uses `psql` to test actual connectivity:
```bash
PGPASSWORD=$INVENTORY_DB_PASS psql \
  -h localhost -p 5432 \
  -U $INVENTORY_DB_USER \
  -d $INVENTORY_DB_NAME \
  -c "SELECT 1" >/dev/null 2>&1
```

### HTTP Endpoint Tests

Uses curl with timeout and proper headers:
```bash
curl -s -o /dev/null -w "%{http_code}" \
  --max-time 5 \
  -H "x-rh-identity: $IDENTITY_HEADER" \
  http://localhost:8000/health
```

### Kafka Broker Tests

Uses `kafka-broker-api-versions` from Kafka tools:
```bash
kafka-broker-api-versions --bootstrap-server localhost:9092
```

### Color-Coded Output

- ✓ Green for passing checks
- ✗ Red for failing checks
- 🔍 Yellow for warnings
- Clear summary at end

### Exit Codes

- `0` - All checks passed
- `1` - One or more checks failed
- `2` - Critical error (missing namespace, etc.)

## Rollback Plan

If issues are found after merge:
1. This PR only adds new files, doesn't modify existing code
2. Safe to revert without impacting other functionality
3. All changes are in `.claude/` directory (not production code)
4. Verification is read-only - never modifies environment

## Related Work

- Depends on PR 1 (needs deployed namespace)
- Depends on PR 2 (needs port-forwards and .env)
- Enables PR 5 (testing infrastructure uses verification)
- Complements existing Bonfire health checks

## Questions for Reviewers

1. Should we add timeout values for each check as configurable parameters?
2. Are the selected health endpoints sufficient or should we add more?
3. Should the script exit early on first failure or always run all checks?

---

**Merge Sequence**: Can merge **after PR 1 and PR 2** (requires deployed namespace with port-forwards)
**Size**: 2 files, 345 lines (213 lines script, 132 lines documentation)
**Risk**: Low - read-only verification, no state changes
