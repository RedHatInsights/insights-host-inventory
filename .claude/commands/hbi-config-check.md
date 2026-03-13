# /hbi-config-check - Configuration Drift Detection

Detect drift between HBI's three configuration sources: `.env`, `dev.yml` container environments, and Python code (`app/config.py` + other files). Identifies orphaned vars, missing definitions, type mismatches, inconsistent defaults, and security concerns.

## Instructions

This command is **read-only** — it never modifies any files.

### Phase 1: Inventory All Env Var References

Scan the entire Python codebase for environment variable references. Use `Grep` to find all occurrences of these patterns:

1. `os.environ.get(` — optional access with default
2. `os.getenv(` — optional access with default
3. `os.environ[` — required access (KeyError if missing)

Search these directories/files:
- `app/`, `api/`, `jobs/`, `migrations/`, `utils/`, `lib/`
- `run.py`, `wait_for_migrations.py`, `dev_server.py`, `inv_mq_service.py`, `inv_export_service.py`
- `run_pendo_syncher.py`, `rebuild_events.py`, `sp_data_validator.py`

**Exclude** from the scan:
- `tests/`, `.local/`, `librdkafka/`, `.claude/`, `iqe-host-inventory-plugin/`, `__pycache__/`, `.cache/`

For each variable found, record:

| Variable | File:Line | Access Pattern | Default Value | Context | Type Conversion |
|----------|-----------|----------------|---------------|---------|-----------------|
| `INVENTORY_DB_HOST` | `app/config.py:171` | `os.getenv()` | `"localhost"` | non-clowder | `str` (none) |
| `INVENTORY_DB_PORT` | `app/config.py:172` | `os.getenv()` | `5432` | non-clowder | `str` (none) |
| ... | ... | ... | ... | ... | ... |

**Context classification rules:**
- If inside `clowder_config()` method or guarded by `CLOWDER_ENABLED == "true"` → `clowder-only`
- If inside `non_clowder_config()` method or guarded by `CLOWDER_ENABLED != "true"` → `non-clowder-only`
- If in `__init__()` (after the clowder/non-clowder branch) or in other files → `shared`

**Type conversion classification:**
- Wrapped in `int()` → `int`
- `.lower() == "true"` or similar boolean check → `bool`
- `json.loads()` → `json`
- `float()` → `float`
- `.split()` → `list`
- No conversion → `str`

Present the master inventory table sorted by file, then line number.

Count: report the total number of unique environment variables found.

### Phase 2: Cross-Reference with `.env`

1. Read the `.env` file in the project root.
2. Extract all `KEY=VALUE` pairs, ignoring:
   - Lines starting with `#` (comments)
   - Blank lines
   - Lines that only set a key with no value but are commented out

3. Compare `.env` keys against the master inventory from Phase 1. Classify each finding:

| Finding | Severity | Description |
|---------|----------|-------------|
| `.env` key not referenced in code | WARN | Orphaned variable — defined but never used |
| Code var with no default, missing from `.env` | WARN | Risk of `None` value at runtime |
| Code var with default, missing from `.env` | INFO | Will use code default — usually intentional |

**Known benign variables** (note but do not flag):
- `PDB_DEBUG_MODE` — consumed by debugger tooling (`pdb`/`ipdb`), not HBI Python code
- `FLASK_ENV` — consumed by Flask framework, not accessed via `os.environ` in HBI code
- `PROMETHEUS_MULTIPROC_DIR` — consumed by the Prometheus client library

**Variables to ignore entirely** (Claude-internal, not HBI):
- `CLAUDE_PROJECT_DIR`, `CLAUDE_ENV_FILE`

Present results as a table:

| Variable | In `.env` | In Code | Default | Severity | Notes |
|----------|-----------|---------|---------|----------|-------|
| `PDB_DEBUG_MODE` | Yes | No | — | INFO | Framework/tool var (benign) |
| ... | ... | ... | ... | ... | ... |

### Phase 3: Cross-Reference with `dev.yml`

1. Read `dev.yml` and extract environment variables from:
   - `hbi-web` service `environment:` section
   - `hbi-mq` service `environment:` section
   - `hbi-mq-apps` service `environment:` section

2. For each container, parse the env vars. Note the `${VAR:-default}` pattern used for shell variable substitution — the value comes from the host `.env` file at compose time, with the fallback after `:-`.

3. Compare container env vars against the code inventory:

| Finding | Severity | Description |
|---------|----------|-------------|
| Container var not referenced in code | WARN | Orphaned container env var |
| Code var (non-clowder) missing from containers | INFO | Will use code default when running in containers |
| Value/default mismatch between container and code | WARN | Inconsistent configuration |

**Known intentional differences** (note as INFO, not WARN):
- `INVENTORY_DB_HOST`: `.env` has `localhost`, `dev.yml` has `db` — container hostname vs local hostname
- `KAFKA_BOOTSTRAP_SERVERS`: `.env` omits it (code defaults to `localhost:29092`), `dev.yml` has `kafka:29092` — container hostname
- `KAFKA_CONSUMER_TOPIC`: `hbi-mq-apps` sets this to `platform.inventory.host-apps` (overrides the default `platform.inventory.host-ingress`)

Present results per container:

**hbi-web:**

| Variable | In Container | In Code | Container Value | Code Default | Severity | Notes |
|----------|-------------|---------|-----------------|--------------|----------|-------|
| ... | ... | ... | ... | ... | ... | ... |

**hbi-mq:**

| Variable | In Container | In Code | Container Value | Code Default | Severity | Notes |
|----------|-------------|---------|-----------------|--------------|----------|-------|
| ... | ... | ... | ... | ... | ... | ... |

**hbi-mq-apps:**

| Variable | In Container | In Code | Container Value | Code Default | Severity | Notes |
|----------|-------------|---------|-----------------|--------------|----------|-------|
| ... | ... | ... | ... | ... | ... | ... |

### Phase 4: Default Value Consistency

For variables that appear in **multiple locations** (`.env`, `dev.yml`, and/or code), compare the effective default values:

1. `.env` value — the literal value in the file
2. `dev.yml` fallback — the value after `:-` in `${VAR:-default}`, or the hardcoded value if no substitution
3. Code default — the second argument to `os.getenv()` / `os.environ.get()`

Flag mismatches:

| Variable | `.env` Value | `dev.yml` Fallback | Code Default | Match | Severity |
|----------|--------------|--------------------|--------------|-------|----------|
| `INVENTORY_DB_POOL_TIMEOUT` | `5` | `5` | `"5"` | Yes (same after type) | — |
| `INVENTORY_DB_HOST` | `localhost` | `db` | `"localhost"` | Expected diff | INFO |
| ... | ... | ... | ... | ... | ... |

**Important:** When comparing values, account for type differences — `.env` and `dev.yml` always provide strings, while code defaults may be `int`, `bool`, etc. Only flag a mismatch when the **semantic value** differs (e.g., `"5"` vs `5` is fine, but `"5"` vs `"10"` is a mismatch).

### Phase 5: Type Safety

Identify environment variables where the type handling is inconsistent or risky:

1. **Missing type conversion**: Variable has an `int`, `float`, `bool`, or other non-string default but `os.environ.get()` / `os.getenv()` returns a string — and no `int()`, `float()`, `.lower() == "true"`, etc. wraps the call.

2. **Inconsistent conversion**: Variable is cast to `int()` in one location but used as a string in another.

3. **Invalid default for conversion**: Variable is wrapped in `int()` but has a default value that would fail `int()` conversion.

**Known real issues to verify:**
- `RBAC_RETRIES` (`app/config.py:239`): `os.environ.get("RBAC_RETRIES", 2)` — default is `int(2)`, but when the env var IS set, the value is a `str` with no `int()` cast. The variable is used in retry logic that likely expects an `int`.
- `RBAC_TIMEOUT` (`app/config.py:240`): `os.environ.get("RBAC_TIMEOUT", 10)` — same pattern. Default is `int(10)`, but env var value would be `str`.
- `INVENTORY_DB_PORT` (`app/config.py:172`): `os.getenv("INVENTORY_DB_PORT", 5432)` — default is `int(5432)`, but env var value would be `str`. Used in URI construction via f-string, so may work by coincidence, but the type is inconsistent.

Present findings:

| Variable | File:Line | Access | Default | Default Type | Env Type | Cast | Severity | Issue |
|----------|-----------|--------|---------|-------------|----------|------|----------|-------|
| `RBAC_RETRIES` | `config.py:239` | `os.environ.get()` | `2` | `int` | `str` | None | WARN | Type mismatch: int default, str from env |
| ... | ... | ... | ... | ... | ... | ... | ... | ... |

### Phase 6: Security Review

Scan for sensitive variable patterns by matching names against these keywords (case-insensitive):
`PASSWORD`, `PASS`, `SECRET`, `TOKEN`, `KEY`, `CREDENTIAL`, `PSK`, `AUTH`

For each match, classify:

| Finding | Severity | Criteria |
|---------|----------|----------|
| Hardcoded dev-safe default | INFO | Default like `"testing-a-psk"`, `"insights"`, `""` — clearly not production secrets |
| Real-looking token in `.env` | WARN | Value that looks like a real token/key (long alphanumeric/hex string) |
| Sensitive var with no default, missing from `.env` | INFO | Will be `None` — safe, but may cause runtime failures |
| Sensitive var with `os.environ["VAR"]` (required) | WARN | Will KeyError if not set — intentional but risky |

Present findings:

| Variable | File:Line | In `.env` | Value Pattern | Default | Severity | Notes |
|----------|-----------|-----------|---------------|---------|----------|-------|
| `UNLEASH_TOKEN` | `config.py:198` | Yes | `*:*.dbffff...` | `""` | WARN | Real-looking token in `.env` |
| `EXPORT_SERVICE_TOKEN` | `config.py:201` | No | — | `"testing-a-psk"` | INFO | Dev-safe hardcoded default |
| ... | ... | ... | ... | ... | ... | ... |

**Do NOT display actual secret values.** Truncate or mask them (e.g., `*:*.dbff...cfc`).

### Phase 7: Summary Report

#### Overall Status

Determine one of:
- **NO DRIFT** — all phases passed with no WARN or CRITICAL findings
- **DRIFT DETECTED** — WARN or CRITICAL findings exist across sources
- **ISSUES FOUND** — type safety or security issues found but no cross-source drift

#### Findings Summary

| Phase | Check | Result | CRITICAL | WARN | INFO |
|-------|-------|--------|----------|------|------|
| 1 | Env var inventory | PASS | 0 | 0 | N total vars |
| 2 | `.env` cross-reference | PASS/WARN | count | count | count |
| 3 | `dev.yml` cross-reference | PASS/WARN | count | count | count |
| 4 | Default value consistency | PASS/WARN | count | count | count |
| 5 | Type safety | PASS/WARN | count | count | count |
| 6 | Security review | PASS/WARN | count | count | count |

#### Severity Rules

| Severity | Criteria |
|----------|----------|
| CRITICAL | `os.environ["VAR"]` with no default anywhere (KeyError risk in production) |
| CRITICAL | `int()` / `json.loads()` cast on a variable with an invalid or missing default |
| WARN | Type mismatch: int/bool default but env returns str, no cast applied |
| WARN | Sensitive variable with real-looking value in `.env` |
| WARN | Orphaned variable in `.env` (defined but never referenced in code) |
| INFO | Container hostname differences (`localhost` vs `db`/`kafka`) — expected |
| INFO | Clowder-only variables missing from `.env` — intentional |
| INFO | Hardcoded dev-safe defaults (`"testing-a-psk"`, `"insights"`) |

#### Action Items

List all findings ordered by severity: **CRITICAL** → **WARN** → **INFO**

For each action item:
1. State the issue clearly
2. Reference the exact `file:line` location(s)
3. Suggest the fix (e.g., "Wrap in `int()`: `self.rbac_retries = int(os.environ.get('RBAC_RETRIES', 2))`")

## Important Notes

- **Clowder-only variables**: Many env vars are only read when `CLOWDER_ENABLED=true` (production/staging). These are intentionally absent from `.env` and `dev.yml`. Tag them as `clowder-only` and classify their absence as INFO, not WARN.
- **Container hostname differences**: `INVENTORY_DB_HOST=db` and `KAFKA_BOOTSTRAP_SERVERS=kafka:29092` in `dev.yml` vs `localhost` defaults in code are expected — containers use Docker DNS names, local dev uses `localhost`.
- **`${VAR:-default}` inheritance**: `dev.yml` uses shell variable substitution. The value before `:-` is the host env var name (usually from `.env`), the value after `:-` is the fallback. Both should be checked.
- **Runtime environment scoping**: Some vars only apply to specific runtime environments (`SERVER`, `SERVICE`, `PENDO_JOB`). Note the scope but do not flag vars as missing if they are scoped to a different runtime.
- **Exclusion of `tests/`**: Test files often set env vars for test purposes. These are intentional overrides and should not be included in the inventory.
- **Framework variables**: `FLASK_ENV`, `FLASK_DEBUG`, `PDB_DEBUG_MODE`, `PROMETHEUS_MULTIPROC_DIR` are consumed by frameworks/tools, not by HBI Python code directly. Note them but do not flag as orphaned.
