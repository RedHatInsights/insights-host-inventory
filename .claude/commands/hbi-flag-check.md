# /hbi-flag-check - Feature Flag Impact Analyzer

Audit all Unleash feature flags: inventory code references, cross-reference with Unleash configuration, check test coverage for both on/off paths, and detect stale flags that are candidates for removal.

## Instructions

### Phase 1: Load Sources

Read these files to establish the full feature flag context:

1. **`lib/feature_flags.py`** — extract:
   - All `FLAG_INVENTORY_*` constant definitions (name and string key, e.g., `FLAG_INVENTORY_API_READ_ONLY = "hbi.api.read-only"`)
   - The `FLAG_FALLBACK_VALUES` dict — maps flag keys to fallback values used when Unleash is unavailable
   - The `get_flag_value()` function signature — the primary API for checking flags
   - The `get_flag_value_and_fallback()` function — returns both value and whether fallback was used
   - The `custom_fallback()` function — behavior when Unleash client is unavailable
   - Any custom strategies (e.g., `SchemaStrategy`) — note their purpose and whether they're actively used

2. **`.unleash/flags.json`** — extract:
   - Every flag name in the `features` array
   - Each flag's `enabled` state (true/false)
   - Each flag's `strategies` — what rollout strategy is configured
   - Note: This file is auto-imported by the Unleash container on startup (`IMPORT_DROP_BEFORE_IMPORT=true` in `dev.yml`)

3. **`app/config.py`** — extract the Unleash-related configuration:
   - `bypass_unleash` — whether Unleash is bypassed entirely
   - `unleash_url`, `unleash_token` — connection settings
   - `unleash_refresh_interval` — how often flags are refreshed
   - `unleash_cache_directory` — local cache path
   - Note the test environment override: `RuntimeEnvironment.TEST` sets `bypass_unleash = True`

Present a configuration summary:

| Setting | Value | Source |
|---------|-------|--------|
| Unleash URL | `http://unleash:4242/api` (default) | app/config.py |
| Bypass Unleash | `false` (default) | app/config.py |
| Refresh Interval | `15` seconds | app/config.py |
| Cache Directory | `/tmp/.unleashcache` | app/config.py |
| Test Bypass | `True` (always) | app/config.py |

### Phase 2: Inventory All Flags

Build a master flag list from three independent sources:

#### 2.1 Code Constants

Search `lib/feature_flags.py` for all lines matching `FLAG_INVENTORY_* = "..."`. Extract:
- Constant name (e.g., `FLAG_INVENTORY_API_READ_ONLY`)
- Flag key string (e.g., `"hbi.api.read-only"`)
- Fallback value from `FLAG_FALLBACK_VALUES` dict

#### 2.2 Unleash Configuration

Parse `.unleash/flags.json` and extract every entry in the `features` array:
- Flag name (e.g., `"hbi.api.read-only"`)
- Enabled state (true/false)
- Strategy type (e.g., `"default"`, `"schema-strategy"`)

#### 2.3 Code References

Search the codebase for all uses of feature flags. Use Grep to find:

1. Direct `get_flag_value(` calls across `app/`, `api/`, `lib/`, `jobs/`:
   ```
   Pattern: get_flag_value\(
   Paths: app/, api/, lib/, jobs/
   ```

2. References to flag constants (`FLAG_INVENTORY_`) across the same paths:
   ```
   Pattern: FLAG_INVENTORY_
   Paths: app/, api/, lib/, jobs/
   Exclude: lib/feature_flags.py (the definition file itself), tests/
   ```

3. Direct string references to flag keys (for cases where the constant is not used):
   ```
   Pattern: "hbi\.(api\.|use_|workloads_)
   Paths: app/, api/, lib/, jobs/
   ```

For each reference found, record: flag name/constant, file path, line number.

#### 2.4 Cross-Reference Table

Present the master inventory:

| # | Flag Key | Code Constant | In flags.json | In Code | Fallback | Status |
|---|----------|--------------|---------------|---------|----------|--------|
| 1 | hbi.api.read-only | FLAG_INVENTORY_API_READ_ONLY | Yes (disabled) | Yes | False | OK |
| 2 | hbi.use_new_system_profile_tables | FLAG_INVENTORY_USE_NEW_SYSTEM_PROFILE_TABLES | Yes | **No references** | False | WARN |
| 3 | hbi.api.use-cached-insights-client-system | **Not defined** | Yes | **No references** | N/A | WARN |

**Status rules:**
- Flag in all three sources (constant + config + code): **OK**
- Flag constant defined but never used in code: **WARN** — dead code
- Flag in `.unleash/flags.json` but no constant in code: **WARN** — orphaned config
- Flag used in code via `get_flag_value()` but no constant: **FAIL** — unmanaged flag (using raw string instead of constant)
- Flag constant exists but missing from `FLAG_FALLBACK_VALUES`: **FAIL** — crash risk when Unleash is unavailable

### Phase 3: Impact Analysis

For each flag that IS used in application code, perform a detailed impact analysis.

Read the surrounding code at each reference location to understand what behavior the flag gates. Present findings per flag:

#### Flag Impact Template

For each flag, fill in:

**`FLAG_NAME`** (`"flag.key"`) — Fallback: `True`/`False`

| Location | File:Line | Behavior Gated |
|----------|-----------|---------------|
| API | api/host.py:NNN | Description of what happens when enabled vs disabled |
| Middleware | lib/middleware.py:NNN | Description |
| Consumer | app/queue/host_mq.py:NNN | Description |

**Blast Radius:**
- Endpoints affected: list specific REST endpoints or "all write endpoints"
- Consumers affected: list MQ consumers
- Background jobs affected: list jobs
- Downstream impact: describe effect on Kafka events, API responses, etc.

**Fallback Implications:**
- When Unleash is unavailable, this flag falls back to `True`/`False`
- This means: description of what happens with the fallback value

Present all flags in sequence, one section per flag.

### Phase 4: Test Coverage Audit

For each flag, search the `tests/` directory for test coverage. Look for:

1. **Flag constant references**:
   ```
   Pattern: FLAG_INVENTORY_<NAME>
   Path: tests/
   ```

2. **Mocking/patching of `get_flag_value`**:
   ```
   Pattern: get_flag_value
   Path: tests/
   ```

3. **Flag key string references**:
   ```
   Pattern: <flag.key.string>
   Path: tests/
   ```

For each match, determine:
- Does the test set the flag to **True** (enabled)?
- Does the test set the flag to **False** (disabled)?
- What mocking pattern is used? (`@patch`, `monkeypatch`, `patch.dict(FLAG_FALLBACK_VALUES, ...)`)

Present a coverage matrix:

| Flag | Enabled (True) Test | Disabled (False) Test | Mock Pattern | Status |
|------|--------------------|-----------------------|-------------|--------|
| FLAG_INVENTORY_API_READ_ONLY | test_attempt_delete_host_read_only | *(implicit — default disabled)* | @patch get_flag_value | WARN (no explicit False test) |
| FLAG_INVENTORY_REJECT_RHSM_PAYLOADS | test_add_host_with_rhsm_payloads_rejected | test_add_host_with_rhsm_payloads_allowed... | @patch get_flag_value | OK (both paths) |
| FLAG_INVENTORY_USE_NEW_SYSTEM_PROFILE_TABLES | None | None | N/A | WARN (no tests) |

**Status rules:**
- Tests exist for BOTH enabled and disabled paths: **OK**
- Test exists for only ONE path: **WARN** — missing coverage for the other branch
- No tests at all: **WARN** — flag behavior is untested
- Flag is dead code (Phase 2 found no references): **N/A** — no tests needed, flag should be removed

**Note:** Tests that run with `bypass_unleash=True` (the test default) implicitly test the "flag disabled" path for flags with `False` fallback. This counts as partial coverage, but an explicit test patching the flag to `False` is stronger.

### Phase 5: Stale Flag Detection

Identify flags that are candidates for cleanup. A flag is "stale" if it can be safely removed from the codebase.

#### 5.1 Dead Code Flags

Flags defined as constants in `lib/feature_flags.py` but NEVER referenced via `get_flag_value()` anywhere in `app/`, `api/`, `lib/`, or `jobs/`:

| Flag | Defined At | Last Modified | Recommendation |
|------|-----------|--------------|----------------|
| FLAG_INVENTORY_USE_NEW_SYSTEM_PROFILE_TABLES | lib/feature_flags.py:NN | date | Remove constant, remove from FLAG_FALLBACK_VALUES |

#### 5.2 Orphaned Configuration

Flags in `.unleash/flags.json` but not defined as constants in code:

| Flag Key | In flags.json | In Code | Recommendation |
|----------|--------------|---------|----------------|
| hbi.api.use-cached-insights-client-system | Yes (disabled) | No | Remove from flags.json |

#### 5.3 Always-On Cleanup Candidates

Flags where the fallback value suggests the feature is now permanent:
- If fallback is `True` AND the flag was originally introduced to gate a feature rollout → the feature may be fully rolled out
- If the flag has been enabled in production for a long time → consider removing the flag and keeping the "enabled" code path as the default

For each candidate:

| Flag | Fallback | Introduced For | Cleanup Steps |
|------|----------|---------------|--------------|
| FLAG_INVENTORY_WORKLOADS_FIELDS_BACKWARD_COMPATIBILITY | True | RHINENG-21211 backward compat | 1. Verify downstream consumers no longer need legacy fields<br>2. Remove flag checks from serialization.py, host_query_db.py<br>3. Remove constant + fallback from feature_flags.py<br>4. Remove from flags.json |

**Note:** Only flag candidates with `True` fallback. Flags with `False` fallback are protective (disabled by default) and should stay until explicitly activated and validated.

#### 5.4 Custom Strategy Audit

Check if any flags use the `SchemaStrategy` custom strategy:
- Is `SchemaStrategy` registered in the Unleash client?
- Is any flag in `.unleash/flags.json` configured with `"strategy": "schema-strategy"`?
- If the strategy is registered but no flags use it: **INFO** — dead strategy code

### Phase 6: Unleash Service Health (Optional)

Check if the local Unleash service is running and queryable.

1. Test connectivity:
   ```
   curl -s -o /dev/null -w "%{http_code}" http://localhost:4242/health
   ```

2. If Unleash is running (HTTP 200), query the API for current flag states:
   ```
   curl -s -H "Authorization: ${UNLEASH_TOKEN}" http://localhost:4242/api/admin/features | python3 -m json.tool
   ```
   If the token is not available in the environment, try reading it from `.env`:
   ```
   grep UNLEASH_TOKEN .env
   ```

3. If Unleash is available, compare live states against `.unleash/flags.json`:

   | Flag | flags.json State | Live State | Match? |
   |------|-----------------|------------|--------|
   | hbi.api.read-only | disabled | disabled | OK |
   | hbi.api.kessel-phase-1 | disabled | enabled | DRIFT |

   Flags toggled differently from their config defaults: **INFO** — may indicate manual testing or a config that needs updating.

4. If Unleash is NOT running, report:
   *"Unleash service is not running locally (port 4242 not responding). Skipping live flag state comparison. Run `make hbi-up` to start services."*

### Phase 7: Summary Report

#### Flag Inventory Summary

| # | Flag Key | Defined | Configured | Used | Tested | Status |
|---|----------|---------|-----------|------|--------|--------|
| 1 | hbi.api.read-only | Yes | Yes | Yes | Partial | OK |
| 2 | hbi.use_new_system_profile_tables | Yes | Yes | No | No | WARN (dead) |
| 3 | hbi.api.use-cached-insights-client-system | No | Yes | No | No | WARN (orphan) |

Where:
- **Defined** = constant exists in `lib/feature_flags.py`
- **Configured** = entry exists in `.unleash/flags.json`
- **Used** = `get_flag_value()` called with this flag in application code
- **Tested** = test coverage exists (Full / Partial / None)

#### Test Coverage Matrix

| Flag | Enabled Path | Disabled Path | Coverage |
|------|-------------|--------------|----------|
| FLAG_INVENTORY_API_READ_ONLY | Yes (3 tests) | Implicit | Partial |
| FLAG_INVENTORY_KESSEL_PHASE_1 | Yes (1 test) | Implicit | Partial |
| FLAG_INVENTORY_USE_NEW_SYSTEM_PROFILE_TABLES | None | None | None |
| FLAG_INVENTORY_REJECT_RHSM_PAYLOADS | Yes (1 test) | Yes (2 tests) | Full |
| FLAG_INVENTORY_WORKLOADS_FIELDS_BACKWARD_COMPATIBILITY | Yes (2 tests) | Yes (1 test) | Full |
| FLAG_INVENTORY_KESSEL_GROUPS | Yes (parametrized) | Yes (parametrized) | Full |

#### Stale Flag Candidates

List all flags identified in Phase 5 as cleanup candidates, with their recommended action.

#### Overall Status

- **CLEAN** — all flags are defined, configured, used, and tested
- **NEEDS ATTENTION** — stale flags, coverage gaps, or orphaned configuration found

#### Action Items

Ordered by severity:

1. **FAIL** — flags without fallback values (crash risk), unmanaged flags (raw strings)
2. **WARN** — dead code flags, orphaned config, missing test coverage
3. **INFO** — cleanup candidates, custom strategy audit, Unleash drift

For each item, provide:
- The specific flag name
- The file:line reference(s)
- The recommended action (remove constant, add test, update flags.json, etc.)

## Important Notes

- This command is **read-only** — it analyzes code and configuration but never modifies them.
- The test environment always sets `bypass_unleash = True`, so all flags effectively fall back to their `FLAG_FALLBACK_VALUES` during tests. This means tests that DON'T explicitly mock `get_flag_value` are implicitly testing the fallback path.
- The `.unleash/flags.json` file is auto-imported into the Unleash container on every restart (`IMPORT_DROP_BEFORE_IMPORT=true`). Changes to this file take effect after `make hbi-down && make hbi-up`.
- Phase 6 (Unleash Service Health) is optional and depends on the local Unleash container running. If not running, the phase is skipped with a note.
- Flags with `False` fallback are "protective" — they default to the safe/existing behavior when Unleash is unavailable. Flags with `True` fallback are "permissive" — they default to the new behavior, making them higher-risk candidates for cleanup.
- The `SchemaStrategy` custom strategy allows flag rollout by schema/account, but no flags currently use it. It is registered for future use.
- When checking test coverage, `@patch("module.path.get_flag_value", return_value=True)` counts as an "enabled" test, and `return_value=False` counts as a "disabled" test. `@patch.dict(FLAG_FALLBACK_VALUES, ...)` is an alternative pattern.
