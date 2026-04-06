# PR 4: Unleash Feature Flag Management

**Part 4 of 7** in the HBI Deployment Infrastructure Series

This PR adds automated Unleash feature flag management for enabling Kessel integration in ephemeral environments.

## What This PR Does

Provides automated feature flag management that:
- Configures Unleash API client
- Enables `hbi.api.kessel-groups` feature flag
- Supports org-specific flag targeting
- Validates flag state after updates
- Handles Unleash API authentication
- Enables the `/hbi-enable-flags` slash command

## Why This Matters

Before this PR, developers had to:
- Manually access Unleash UI in browser
- Navigate through Unleash admin interface
- Manually toggle feature flags
- Remember flag names and settings
- Verify changes took effect

After this PR, developers can:
- Run `/hbi-enable-flags` to enable Kessel integration
- Automatically configure all required flags
- Target specific org IDs for testing
- Verify flag state programmatically
- Consistent flag configuration across team

## Files Added (2 files, 550 lines)

### Feature Flag Script
- **`.claude/scripts/enable-feature-flags.sh`** (415 lines)
  - Unleash API client implementation
  - Feature flag toggle automation
  - Org-specific targeting configuration
  - Strategy creation and updates
  - Flag state validation
  - Error handling and retry logic
  - Support for multiple flag types

### Documentation
- **`.claude/commands/hbi-enable-flags.md`** (135 lines)
  - `/hbi-enable-flags` command documentation
  - Usage examples for different scenarios
  - Flag targeting configuration
  - Troubleshooting guide
  - Unleash API reference

## Commands Enabled

### `/hbi-enable-flags`

Enables Kessel feature flags in ephemeral Unleash instance.

**Usage:**
```bash
# Enable flags globally (all org IDs)
/hbi-enable-flags

# Enable flags for specific namespace
/hbi-enable-flags --namespace ephemeral-abc123

# Enable flags for specific org ID only
/hbi-enable-flags --org-id 3340851

# Enable multiple flags
/hbi-enable-flags --flags "hbi.api.kessel-groups,hbi.api.kessel-rbac"
```

**What it does:**
1. Detects active namespace and Unleash URL
2. Extracts Unleash admin API token
3. Enables `hbi.api.kessel-groups` feature flag
4. Configures gradual rollout strategy (default: 100%)
5. Optionally adds org-specific targeting
6. Validates flag state
7. Reports flag configuration

**Feature Flags Configured:**

**hbi.api.kessel-groups**
- **Purpose**: Enable RBAC v2 workspace integration for Groups API
- **Endpoints affected**:
  - GET /groups/{group_id_list}
  - POST /groups/{group_id}/hosts
  - DELETE /groups/{group_id}/hosts/{host_id_list}
  - GET /groups/{group_id}/hosts
- **Default**: Disabled (uses database validation)
- **When enabled**: Uses Kessel workspace API validation

## Dependencies

**Requires:**
- **PR 1** - Ephemeral namespace with Unleash deployed
- **PR 2** - Port-forward to Unleash (localhost:4242)

This PR manages feature flags in the Unleash instance deployed by PR 1.

## What's Next

After this PR is merged, subsequent PRs will add:
- **PR 5**: Testing infrastructure
- **PR 6**: Cleanup utilities
- **PR 7**: Configuration examples

## Testing

To test this PR locally:

```bash
# Checkout this branch
git checkout pr4-eens-feature-flags

# Prerequisites: Deploy and setup environment
.claude/deployer/deploy-ephemeral.sh
.claude/deployer/setup-for-dev.sh

# Enable feature flags globally
.claude/scripts/enable-feature-flags.sh

# Enable for specific org ID
.claude/scripts/enable-feature-flags.sh --org-id 3340851

# Verify flag state via API
curl -s http://localhost:4242/api/client/features/hbi.api.kessel-groups | jq

# Verify flag state in Unleash UI
# Access via: oc get route unleash -n <namespace>
```

Expected result: Feature flag enabled with correct targeting configuration.

## Technical Details

### Unleash API Integration

The script uses Unleash Admin API for programmatic control:

**Authentication:**
```bash
# Extract admin token from K8s secret
ADMIN_TOKEN=$(kubectl get secret unleash-admin -n $NAMESPACE \
  -o jsonpath='{.data.adminToken}' | base64 -d)

# Use in API requests
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:4242/api/admin/features
```

**Feature Flag Toggle:**
```bash
# Enable flag
curl -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  http://localhost:4242/api/admin/features/hbi.api.kessel-groups/toggle

# Verify state
curl -s http://localhost:4242/api/admin/features/hbi.api.kessel-groups | \
  jq '.enabled'
```

### Targeting Strategies

**Gradual Rollout (Default):**
```json
{
  "name": "flexibleRollout",
  "parameters": {
    "rollout": "100",
    "stickiness": "default"
  }
}
```

**Org-Specific Targeting:**
```json
{
  "name": "userWithId",
  "parameters": {
    "userIds": "3340851"
  },
  "constraints": [
    {
      "contextName": "orgId",
      "operator": "IN",
      "values": ["3340851"]
    }
  ]
}
```

### Strategy Configuration

The script intelligently manages strategies:
1. Check if strategy already exists
2. Update existing strategy if found
3. Create new strategy if not found
4. Validate strategy is active

### Error Handling

- Validates Unleash service is accessible
- Retries API calls on transient failures
- Provides clear error messages
- Validates token extraction
- Checks flag state after updates

### Flag State Validation

After enabling flags, verifies:
```bash
# Check flag is enabled
enabled=$(curl -s http://localhost:4242/api/admin/features/$FLAG_NAME | jq '.enabled')

# Check strategy is active
strategy_count=$(curl -s http://localhost:4242/api/admin/features/$FLAG_NAME | \
  jq '.strategies | length')

# Report status
echo "✓ Flag $FLAG_NAME: enabled=$enabled, strategies=$strategy_count"
```

### Multiple Flag Support

Can enable multiple flags in single run:
```bash
FLAGS="hbi.api.kessel-groups,hbi.api.kessel-rbac,hbi.api.kessel-staleness"
for flag in ${FLAGS//,/ }; do
  enable_feature_flag "$flag"
done
```

## Rollback Plan

If issues are found after merge:
1. This PR only adds new files, doesn't modify existing code
2. Safe to revert without impacting other functionality
3. All changes are in `.claude/` directory (not production code)
4. Feature flags can be disabled manually via Unleash UI
5. Script only enables flags, never disables them

## Related Work

- Depends on PR 1 (Unleash must be deployed)
- Depends on PR 2 (port-forward to Unleash needed)
- Enables Kessel integration testing in ephemeral
- Related to RBAC v2 migration work

## Questions for Reviewers

1. Should we add support for disabling flags (currently only enables)?
2. Are the default rollout percentages (100%) appropriate for ephemeral?
3. Should we validate flag changes via HBI API endpoints after enabling?

---

**Merge Sequence**: Can merge **after PR 1 and PR 2** (requires Unleash deployed with port-forward)
**Size**: 2 files, 550 lines (415 lines script with extensive error handling, 135 lines documentation)
**Risk**: Low - only enables feature flags, doesn't modify HBI code
