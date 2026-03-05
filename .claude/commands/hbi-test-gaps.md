# /hbi-test-gaps - Test Coverage Gap Analyzer

Detect test coverage gaps across the HBI codebase: unmapped source modules, untested API endpoints, missing error-path tests, uncovered public functions, and background jobs without test files. Produces an actionable report ordered by severity with effort estimates.

## Instructions

This command is **read-only** — it analyzes source and test files but never modifies anything or runs tests.

### Severity Rules

| Severity | Criteria |
|----------|----------|
| CRITICAL | Core business logic module (`host_repository`, `group_repository`, `middleware`, `kessel`) with NO test file |
| FAIL | API endpoint with no success-path test (2xx) |
| FAIL | Background job with no test file at all |
| WARN | Module tested only indirectly (via integration tests) — no direct unit tests |
| WARN | API endpoint missing error-path tests (4xx/5xx) |
| WARN | Missing auth test coverage (401/403) for a data endpoint |
| WARN | Public function in a key module with no test referencing it |
| INFO | Infrastructure module without tests (metrics, logging, cache) — lower risk |
| INFO | Utility or tooling module without tests |
| OK | Module has a direct test file covering both success and error paths |

### Phase 1: Load Sources

Inventory all source and test files to build the mapping foundation.

#### 1.1 Source File Inventory

Collect every Python file in the production source directories. For each file, record its path, approximate line count, and layer classification.

Scan these directories:
- `api/` — API endpoint handlers and query logic
- `lib/` — business logic, repositories, middleware
- `app/` — Flask app, models, auth, config, serialization, queue
- `jobs/` — background job scripts
- `utils/` — utility scripts (classify as tooling, lower priority)

Skip `__init__.py` files that contain only imports or are empty. Skip `__pycache__/` directories.

Classify each source file into one of these layers:

| Layer | Description | Priority |
|-------|-------------|----------|
| API Endpoint | Request handlers in `api/*.py` | High |
| API Query | Query builders in `api/host_query_db.py`, `api/group_query.py`, etc. | High |
| API Filtering | Filter logic in `api/filtering/*.py` | High |
| Business Logic | Repository, delete, synchronize in `lib/*.py` | High |
| Middleware/Auth | `lib/middleware.py`, `lib/kessel.py`, `app/auth/*.py` | High |
| Models | `app/models/*.py` | Medium |
| Serialization | `app/serialization.py`, `app/staleness_serialization.py` | Medium |
| Queue/Events | `app/queue/*.py` | Medium |
| Jobs | `jobs/*.py` | Medium |
| Config/Infra | `app/config.py`, `app/logging.py`, `api/metrics.py`, `lib/metrics.py` | Low |
| Utilities | `utils/*.py` | Low |

#### 1.2 Test File Inventory

Collect every test file:
- `tests/test_*.py` — top-level test files
- `tests/test_jobs/test_*.py` — job-specific tests
- `tests/fixtures/*.py` — fixture files (for reference, not coverage targets)
- `tests/helpers/*.py` — helper files (for reference, not coverage targets)

#### 1.3 Test Configuration

Read test configuration from:
- `setup.cfg` — check for `[pytest]` section, markers, exclusions
- `pyproject.toml` — check for `[tool.pytest.ini_options]` and `[tool.coverage]` sections
- Check if a `.coveragerc` file exists

Present a summary:

| Item | Value |
|------|-------|
| Source files (api/ + lib/ + app/ + jobs/) | N |
| Test files | M |
| Test fixture files | K |
| Test helper files | J |
| Coverage threshold configured | Yes/No |
| Pytest markers defined | list them |
| Coverage exclusion patterns | list or "none" |

### Phase 2: Module-to-Test File Mapping

For every source module identified in Phase 1, find its corresponding test file(s).

#### 2.1 Mapping Strategy

Apply these rules in order to find test coverage for each source file:

1. **Direct test file**: Look for `tests/test_<module_name>.py` (e.g., `lib/host_delete.py` → `tests/test_host_delete.py` if it exists)
2. **Name-variant test file**: Look for test files with related names (e.g., `api/host.py` → `tests/test_api_hosts_get.py`, `tests/test_api_hosts_update.py`, `tests/test_api_hosts_delete.py`)
3. **Job test file**: For `jobs/<name>.py`, look for `tests/test_jobs/test_<name>.py`
4. **Indirect coverage**: Use Grep to search for imports of the source module across all test files:
   ```
   Pattern: "from <module_path> import|import <module_name>"
   Path: tests/
   ```
   If the module or its functions are referenced in test files, classify as "Indirect".
5. **No coverage**: If none of the above find any reference, classify as "None".

#### 2.2 Present Module Coverage Map

Present results grouped by layer, sorted by severity within each layer.

**API Layer:**

| Source Module | Lines | Test File(s) | Coverage Type | Status |
|---------------|-------|--------------|---------------|--------|
| `api/host.py` | N | `test_api_hosts_get.py`, `test_api_hosts_update.py`, `test_api_hosts_delete.py` | Direct | OK |
| `api/group.py` | N | `test_api_groups_create.py`, `test_api_groups_get.py`, ... | Direct | OK |
| `api/cache.py` | N | — | None | INFO |
| ... | ... | ... | ... | ... |

**Business Logic Layer:**

| Source Module | Lines | Test File(s) | Coverage Type | Status |
|---------------|-------|--------------|---------------|--------|
| `lib/host_repository.py` | 418 | `test_api_hosts_*.py`, `test_host_mq_service.py` | Indirect only | WARN |
| `lib/middleware.py` | 701 | `test_rbac.py`, `test_api_*.py` | Indirect only | WARN |
| `lib/feature_flags.py` | N | — | None | WARN |
| ... | ... | ... | ... | ... |

**Queue/Events Layer:**

| Source Module | Lines | Test File(s) | Coverage Type | Status |
|---------------|-------|--------------|---------------|--------|
| ... | ... | ... | ... | ... |

**Models & Serialization Layer:**

| Source Module | Lines | Test File(s) | Coverage Type | Status |
|---------------|-------|--------------|---------------|--------|
| ... | ... | ... | ... | ... |

**Jobs Layer:**

| Source Module | Lines | Test File(s) | Coverage Type | Status |
|---------------|-------|--------------|---------------|--------|
| `jobs/host_reaper.py` | N | `test_jobs/test_host_reaper.py` | Direct | OK |
| `jobs/host_sync_group_data.py` | 37 | — | None | FAIL |
| ... | ... | ... | ... | ... |

**Infrastructure Layer:**

| Source Module | Lines | Test File(s) | Coverage Type | Status |
|---------------|-------|--------------|---------------|--------|
| `api/metrics.py` | N | — | None | INFO |
| `lib/metrics.py` | N | — | None | INFO |
| ... | ... | ... | ... | ... |

#### 2.3 Coverage Summary

| Coverage Type | Count | Percentage |
|---------------|-------|------------|
| Direct test file | N | X% |
| Indirect only | M | Y% |
| No coverage | K | Z% |

### Phase 3: API Endpoint Coverage

For every endpoint in the OpenAPI spec, check that tests exist for the required scenarios.

#### 3.1 Extract Endpoints

Read `swagger/api.spec.yaml` and extract every path+method combination with its `operationId`:
```
Grep pattern: "operationId:"
Path: swagger/api.spec.yaml
```

Build the complete endpoint list from the spec.

#### 3.2 Search for Endpoint Tests

For each endpoint, search test files for:

1. **Success path (2xx)**: Search for the URL pattern and a `200`, `201`, or `202` status assertion:
   ```
   Grep pattern: the endpoint's URL path segment
   Path: tests/test_api_*.py
   ```

2. **Client error path (4xx)**: Search for `400`, `404`, `409` assertions associated with the endpoint URL.

3. **Auth error path (401/403)**: Search for `401` or `403` assertions. Check `tests/test_api_auth.py` for shared auth tests that cover multiple endpoints.

4. **Pagination test** (for GET list endpoints only): Search for `per_page`, `page`, pagination-related assertions in tests that reference the endpoint.

5. **Empty result test** (for GET list endpoints only): Search for empty list assertions (`"total": 0`, `"count": 0`, `"results": []`).

#### 3.3 Present Endpoint Coverage Matrix

| # | Method | Path | operationId | 2xx Test | 4xx Test | Auth Test | Pagination | Empty | Status |
|---|--------|------|-------------|----------|----------|-----------|------------|-------|--------|
| 1 | GET | /hosts | api.host.get_host_list | Yes/No | Yes/No | Yes/No | Yes/No | Yes/No | OK/WARN/FAIL |
| 2 | DELETE | /hosts | api.host.delete_hosts_by_filter | Yes/No | Yes/No | Yes/No | N/A | N/A | OK/WARN/FAIL |
| 3 | POST | /hosts/checkin | api.host.host_checkin | Yes/No | Yes/No | Yes/No | N/A | N/A | OK/WARN/FAIL |
| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |

Include **every** endpoint — do not omit any.

**Status rules:**
- Has 2xx + 4xx + auth tests: **OK**
- Has 2xx but missing 4xx or auth: **WARN**
- No 2xx test at all: **FAIL**
- Management endpoints (`/health`, `/version`, `/metrics`) without auth tests: **OK** (intentional)

#### 3.4 Endpoint Coverage Summary

| Scenario | Covered | Total | Percentage |
|----------|---------|-------|------------|
| Success path (2xx) | N | M | X% |
| Client error (4xx) | N | M | X% |
| Auth (401/403) | N | M | X% |
| Pagination (list endpoints) | N | K | X% |
| Empty results (list endpoints) | N | K | X% |

### Phase 4: Public Function Coverage

For critical modules, enumerate every public function and check whether any test file references it.

#### 4.1 Key Modules to Audit

These modules contain critical business logic where untested functions represent the highest risk:

1. **`lib/host_repository.py`** — host CRUD, deduplication, canonical facts matching
2. **`lib/group_repository.py`** — group CRUD, host-group association, workspace events
3. **`lib/middleware.py`** — RBAC decorators, Kessel integration, permission filtering
4. **`lib/kessel.py`** — gRPC Kessel client, permission checks, workspace listing
5. **`lib/host_delete.py`** — host deletion logic
6. **`lib/host_synchronize.py`** — host synchronization logic
7. **`app/serialization.py`** — host/group serialization, canonical facts
8. **`lib/staleness.py`** — staleness calculation utilities

#### 4.2 Function Coverage Check

For each module, extract all public functions (functions not starting with `_`). Then search test files for references to each function name:

```
Grep pattern: "<function_name>"
Path: tests/
```

A function is considered "covered" if its name appears in any test file — either called directly, imported, or referenced in an assertion. A function referenced only via the module it belongs to (e.g., called through integration tests) counts as "Indirect".

Present results per module:

**`lib/host_repository.py`:**

| Function | Referenced in Tests | Coverage Type | Status |
|----------|--------------------| --------------|--------|
| `add_host` | `test_host_mq_service.py` | Indirect | WARN |
| `find_existing_host` | `test_host_mq_service.py` | Indirect | WARN |
| `create_new_host` | — | None | WARN |
| `host_query` | `test_api_hosts_get.py` | Indirect | WARN |
| ... | ... | ... | ... |

**`lib/middleware.py`:**

| Function | Referenced in Tests | Coverage Type | Status |
|----------|--------------------| --------------|--------|
| `access` | `test_rbac.py` | Indirect | WARN |
| `get_rbac_filter` | — | None | WARN |
| `get_kessel_filter` | — | None | WARN |
| ... | ... | ... | ... |

Repeat this table for each key module listed in 4.1.

#### 4.3 Function Coverage Summary

| Module | Total Public Funcs | Direct | Indirect | None | Status |
|--------|--------------------|--------|----------|------|--------|
| `lib/host_repository.py` | N | X | Y | Z | OK/WARN |
| `lib/group_repository.py` | N | X | Y | Z | OK/WARN |
| `lib/middleware.py` | N | X | Y | Z | OK/WARN |
| `lib/kessel.py` | N | X | Y | Z | OK/WARN |
| `lib/host_delete.py` | N | X | Y | Z | OK/WARN |
| `lib/host_synchronize.py` | N | X | Y | Z | OK/WARN |
| `app/serialization.py` | N | X | Y | Z | OK/WARN |
| `lib/staleness.py` | N | X | Y | Z | OK/WARN |

### Phase 5: Error Path and Edge Case Audit

Identify error handling patterns in source code and check whether tests exercise them.

#### 5.1 Exception Handler Coverage

Search for exception handling and raising patterns in source files:

```
Grep pattern: "except \w|raise \w"
Path: api/, lib/, app/queue/
```

For each unique exception type found, search test files for references to that exception:

```
Grep pattern: "<ExceptionType>"
Path: tests/
```

Also check `app/exceptions.py` for HBI-specific exception classes and verify each is tested.

Present results:

| Exception Type | Raised In | Tested In | Status |
|----------------|-----------|-----------|--------|
| `InventoryException` | `lib/host_repository.py:N` | `test_host_mq_service.py` | OK |
| `ValidationException` | `api/validation.py:N` | test file or — | OK/WARN |
| `ValueError` | various | various | OK/WARN |
| `IntegrityError` | `lib/group_repository.py:N` | test file or — | OK/WARN |
| ... | ... | ... | ... |

#### 5.2 HTTP Error Response Coverage

Search for `abort()` calls and direct error status returns in API handlers:

```
Grep pattern: "abort\("
Path: api/
```

For each `abort(status_code)` found, check if a test asserts that status code for the corresponding endpoint:

| File:Line | Error Code | Condition | Test Exists | Status |
|-----------|------------|-----------|-------------|--------|
| `api/host.py:NNN` | 400 | Invalid input | Yes/No | OK/WARN |
| `api/group.py:NNN` | 404 | Group not found | Yes/No | OK/WARN |
| `api/host.py:NNN` | 503 | Read-only mode | Yes/No | OK/WARN |
| ... | ... | ... | ... | ... |

#### 5.3 Edge Case Patterns

Search for common edge case tests that should exist for a CRUD API:

| Edge Case | Search Pattern | Found In | Status |
|-----------|----------------|----------|--------|
| Empty list response | `"total": 0` or `"count": 0` | test file(s) | OK/WARN |
| Max pagination | `per_page` with boundary values | test file(s) | OK/WARN |
| Invalid UUID format | `invalid` near UUID patterns | test file(s) | OK/WARN |
| Duplicate creation | `409` or `duplicate` | test file(s) | OK/WARN |
| Null/None input fields | `None` in request body tests | test file(s) | OK/WARN |
| Oversized input | `too long` or `max length` | test file(s) | OK/WARN |
| Special characters | SQL injection or XSS patterns | test file(s) | OK/WARN |

#### 5.4 Kafka Error Path Coverage

Search for Kafka-related error handling and verify tests exist:

```
Grep pattern: "KafkaError|KafkaException|ProduceError|producer.*error|delivery.*fail"
Path: app/queue/, lib/
```

For each error handling path found, check if tests exercise it:

| Error Scenario | Source File:Line | Test File | Status |
|----------------|-----------------|-----------|--------|
| Producer delivery failure | `app/queue/event_producer.py:NNN` | test file or — | OK/WARN |
| Message deserialization error | `app/queue/host_mq.py:NNN` | test file or — | OK/WARN |
| Consumer poll timeout | `app/queue/host_mq.py:NNN` | test file or — | OK/WARN |
| Null message handling | `app/queue/host_mq.py:NNN` | `test_kafka_null_implementations.py` | OK |
| ... | ... | ... | ... |

### Phase 6: Background Job Coverage

Audit every file in `jobs/` for test coverage depth.

#### 6.1 Job File Inventory

For each file in `jobs/` (excluding `__init__.py` and `common.py`):

1. Check if a corresponding test file exists in `tests/test_jobs/`
2. If a test file exists, read it to assess coverage depth:
   - **Normal operation**: Does the test run the job successfully?
   - **Error handling**: Does the test simulate failures (DB errors, missing data)?
   - **Batch processing**: Does the test check chunked/batched operation?
   - **Metrics**: Does the test verify metrics are emitted?

Present results:

| Job File | Lines | Test File | Normal | Errors | Batch | Metrics | Status |
|----------|-------|-----------|--------|--------|-------|---------|--------|
| `jobs/host_reaper.py` | N | `test_host_reaper.py` | Yes | Yes/No | Yes/No | Yes/No | OK/WARN |
| `jobs/host_delete_duplicates.py` | N | `test_duplicate_hosts.py` | Yes | Yes/No | Yes/No | Yes/No | OK/WARN |
| `jobs/inv_publish_hosts.py` | N | `test_inv_publish_hosts.py` | Yes | Yes/No | Yes/No | Yes/No | OK/WARN |
| `jobs/host_sync_group_data.py` | N | — | — | — | — | — | FAIL |
| `jobs/generate_stale_host_notifications.py` | N | — | — | — | — | — | FAIL |
| `jobs/populate_host_type.py` | N | — | — | — | — | — | FAIL |
| `jobs/assign_ungrouped_hosts_to_groups.py` | N | — | — | — | — | — | FAIL |
| `jobs/create_ungrouped_host_groups.py` | N | — | — | — | — | — | FAIL |
| `jobs/add_inventory_view.py` | N | — | — | — | — | — | FAIL |
| `jobs/system_profile_validator.py` | N | — | — | — | — | — | FAIL |
| ... | ... | ... | ... | ... | ... | ... | ... |

Include **every** job file — do not omit any.

#### 6.2 Job Coverage Summary

| Status | Count | Jobs |
|--------|-------|------|
| Tested (Direct) | N | list |
| Not Tested | M | list |
| Coverage Rate | | N / (N+M) = X% |

### Phase 7: Summary Report

#### 7.1 Module Coverage Matrix

| Layer | Total Modules | Direct Tests | Indirect Only | No Tests | Health |
|-------|---------------|------------- |---------------|----------|--------|
| API Endpoints | N | X | Y | Z | X% direct |
| API Query/Filter | N | X | Y | Z | X% direct |
| Business Logic (lib/) | N | X | Y | Z | X% direct |
| Middleware/Auth | N | X | Y | Z | X% direct |
| Models & Serialization | N | X | Y | Z | X% direct |
| Queue/Events | N | X | Y | Z | X% direct |
| Background Jobs | N | X | Y | Z | X% direct |
| Infrastructure | N | X | Y | Z | X% direct |
| **Total** | **N** | **X** | **Y** | **Z** | **X%** |

#### 7.2 API Endpoint Coverage Matrix

| Scenario | Covered | Total | Health |
|----------|---------|-------|--------|
| Success path (2xx) | N | M | X% |
| Error path (4xx) | N | M | X% |
| Auth (401/403) | N | M | X% |

#### 7.3 Overall Test Health Rating

Based on the findings, determine the overall rating:

- **STRONG** — >80% direct module coverage, >90% endpoint 2xx coverage, no CRITICAL findings
- **MODERATE** — 60-80% direct module coverage, >70% endpoint 2xx coverage, ≤2 CRITICAL findings
- **NEEDS IMPROVEMENT** — <60% direct module coverage or <70% endpoint 2xx coverage or >2 CRITICAL findings

#### 7.4 Consolidated Findings

Present ALL findings with WARN, FAIL, or CRITICAL status in a single table, ordered by severity:

| # | Severity | Phase | Module/Endpoint | Finding | Suggested Action | Effort |
|---|----------|-------|-----------------|---------|------------------|--------|
| 1 | CRITICAL | 2 | `lib/middleware.py` | No direct test file for 701-line module with RBAC/Kessel logic | Create `tests/test_middleware.py` with unit tests for `get_rbac_filter()`, `get_kessel_filter()` | High |
| 2 | FAIL | 6 | `jobs/system_profile_validator.py` | 279-line job with no test file | Create `tests/test_jobs/test_system_profile_validator.py` | Medium |
| 3 | WARN | 4 | `lib/host_repository.py:create_new_host` | Function not directly tested | Add unit test for `create_new_host()` | Low |
| ... | ... | ... | ... | ... | ... | ... |

**Effort guidelines:**
- **Low** — single test function or a few assertions, <30 minutes
- **Medium** — new test file with multiple scenarios, 1-3 hours
- **High** — complex test setup (mocking gRPC, Kafka, RBAC, multiple fixtures), 3-8 hours

#### 7.5 Top 5 Action Items

List the 5 highest-impact improvements, considering both severity and effort:

1. **[Action]** — [Why it matters] — Effort: [Low/Medium/High]
2. **[Action]** — [Why it matters] — Effort: [Low/Medium/High]
3. **[Action]** — [Why it matters] — Effort: [Low/Medium/High]
4. **[Action]** — [Why it matters] — Effort: [Low/Medium/High]
5. **[Action]** — [Why it matters] — Effort: [Low/Medium/High]

Prioritize: CRITICAL+Low effort first, then CRITICAL+High, then FAIL+Low, etc.

#### 7.6 Test Infrastructure Recommendations

Based on the analysis, note improvements to the test infrastructure itself:

| Recommendation | Impact | Effort |
|----------------|--------|--------|
| Add `.coveragerc` with minimum threshold (e.g., 75%) | Prevents regression | Low |
| Add coverage reporting to CI pipeline | Visibility | Low |
| Create shared fixtures for job testing | Enables job test creation | Medium |
| ... | ... | ... |

## Important Notes

- This command is **read-only** — it analyzes code but never modifies files, runs tests, or executes coverage tools.
- **Indirect coverage is not zero coverage.** A module tested via integration tests (e.g., `lib/host_repository.py` exercised through API tests) has real coverage. The WARN severity reflects that direct unit tests would improve isolation and debugging speed, not that the module is untested. Do not flag indirect-only modules as FAIL or CRITICAL.
- **Test file naming is not always 1:1.** Some modules are covered by multiple test files (e.g., `api/host.py` → `test_api_hosts_get.py`, `test_api_hosts_update.py`, `test_api_hosts_delete.py`). Some test files cover multiple modules. The mapping logic should check multiple name patterns and imports.
- **Auth tests are often shared.** `tests/test_api_auth.py` tests identity validation across multiple endpoint types (hosts, groups, system profiles, staleness). A shared auth test counts as coverage for all endpoints it exercises. Search `test_api_auth.py` to see which endpoints it covers before flagging auth gaps.
- **Tests run with `bypass_rbac=True` and `bypass_kessel=True`** (set in `app/config.py` for `RuntimeEnvironment.TEST`). Auth-specific tests must explicitly mock RBAC/Kessel responses via the `enable_rbac` or `enable_kessel` fixtures. When searching for auth test coverage, look for tests that configure these mocks, not just tests that happen to call the endpoint.
- **Infrastructure modules** (`api/metrics.py`, `lib/metrics.py`, `api/cache.py`, `api/cache_key.py`, `app/logging.py`) are classified as INFO rather than WARN/FAIL because they are low-risk — they primarily wrap external libraries (Prometheus, Redis, Python logging) with thin configuration layers. Testing the wrapper adds limited value.
- **The `utils/` directory** contains developer tooling scripts (Kafka consumer/producer, REST producer, dashboard validator, simple API client), not production code. These are classified as INFO priority and do not need the same test rigor as `api/` or `lib/` modules.
- **`jobs/common.py`** is a shared utility module for jobs (contains `job_setup()`, `excepthook()`), not a standalone job. Skip it in the job coverage audit (Phase 6) but include it in the module mapping (Phase 2) as a support module.
- **Function name grep is a heuristic.** Searching for `create_new_host` in test files will find both direct calls and indirect references (e.g., mocks, comments, imports). False positives are preferable to false negatives — err on the side of marking functions as covered when their name appears in test files.
- **Management endpoints** (`/health`, `/version`, `/metrics` in `api/mgmt.py`) are intentionally lightweight and do not require auth or error-path tests. Do not flag their absence as WARN or FAIL.
- **Effort estimates** in the action items are approximate: Low (<30 min), Medium (1-3 hours), High (3-8 hours). They reflect the complexity of test setup, not the size of the test. A small job with simple inputs is "Low" even if it has 200 lines; a middleware test requiring gRPC mocking is "High" even if the test itself is short.
