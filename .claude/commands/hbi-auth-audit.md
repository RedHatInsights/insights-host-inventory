# /hbi-auth-audit - RBAC & Auth Path Auditor

Map every API endpoint to its required permissions, cross-reference with the OpenAPI spec security definitions, validate test coverage for auth scenarios, and audit the RBAC V1 / Kessel V2 dual-path consistency.

## Instructions

### Phase 1: Load Sources

Read all files that define or enforce authentication and authorization:

#### 1.1 Auth Module

1. **`app/auth/identity.py`** — extract:
   - All identity types: `User`, `System`, `ServiceAccount`, `X509`, `Associate`
   - All auth types: `basic-auth`, `cert-auth`, `jwt-auth`, `uhc-auth`, `saml-auth`, `x509`
   - System cert types: `hypervisor`, `rhui`, `sam`, `satellite`, `system`
   - `from_auth_header()` — how `x-rh-identity` is parsed and validated
   - `from_bearer_token()` — trusted identity via `INVENTORY_SHARED_SECRET`
   - RHSM Errata special handling — `x-inventory-org-id` fallback header

2. **`app/auth/rbac.py`** — extract:
   - `RbacResourceType` enum: `HOSTS`, `GROUPS`, `STALENESS`, `ALL`
   - `RbacPermission` enum: `READ`, `WRITE`, `ADMIN`
   - `KesselPermission` class — permission objects with `workspace_permission` and `resource_permission`
   - `KesselResourceTypes` — resource type definitions with their permission mappings (HOST.view, HOST.update, HOST.delete, WORKSPACE.move_host, STALENESS.view, STALENESS.update)

3. **`app/auth/__init__.py`** — extract:
   - `authentication_header_handler()` — Connexion security handler for `x-rh-identity`
   - `bearer_token_handler()` — Connexion security handler for Bearer tokens

#### 1.2 Middleware

4. **`lib/middleware.py`** — read in full. Extract:
   - `rbac()` decorator — V1 RBAC enforcement (HTTP calls to RBAC service)
   - `access()` decorator — V2 Kessel-aware enforcement (gRPC, with V1 fallback when flag off)
   - `get_rbac_filter()` — V1 permission parsing and group ID extraction
   - `get_kessel_filter()` — V2 Kessel permission check and workspace filtering
   - `rbac_group_id_check()` — validates group IDs against allowed set
   - `rbac_create_ungrouped_hosts_workspace()` — PSK-authenticated workspace creation
   - Read-only mode check: `FLAG_INVENTORY_API_READ_ONLY`
   - Kessel phase 1 flag: `FLAG_INVENTORY_KESSEL_PHASE_1`
   - System identity bypass logic (non-User, non-ServiceAccount on HOST resources)

5. **`lib/kessel.py`** — extract:
   - Kessel client initialization and gRPC configuration
   - `check()` / `check_for_update()` — single/bulk permission checks
   - `ListAllowedWorkspaces()` — workspace listing for filter construction
   - Error handling: how gRPC errors (UNAVAILABLE, DEADLINE_EXCEEDED, PERMISSION_DENIED) are handled
   - Fail-closed behavior (all errors → denied)

#### 1.3 API Endpoints

6. Read ALL endpoint files and extract the auth decorator on each function:
   - `api/host.py`
   - `api/group.py`
   - `api/staleness.py`
   - `api/system_profile.py`
   - `api/tag.py`
   - `api/host_views.py`
   - `api/host_group.py`
   - `api/resource_type.py`

   For each `def function_name(...)`:
   - Look for `@rbac(...)` or `@access(...)` decorators above the function
   - Extract parameters: resource type, permission, `id_param`, `permission_base`
   - Note if multiple decorators are stacked (e.g., staleness endpoints have two `@access()` decorators)
   - Note if NO auth decorator is present

#### 1.4 OpenAPI Spec

7. **`swagger/api.spec.yaml`** — extract:
   - `securitySchemes` definitions (`ApiKeyAuth`, `BearerAuth`)
   - For every path+method: the `security` declaration (if present)
   - The `operationId` for each path+method (maps to Python function)

#### 1.5 Configuration

8. **`app/config.py`** — extract:
   - `bypass_rbac` — env var `BYPASS_RBAC` (default: `false`)
   - `bypass_kessel` — env var `BYPASS_KESSEL` (default: `false`)
   - `rbac_psk` — loaded from `RBAC_PSKS` JSON env var
   - Test override: `RuntimeEnvironment.TEST` sets `bypass_rbac = bypass_kessel = bypass_unleash = True`

Present a summary of the auth architecture:

| Component | Mechanism | Transport | Status |
|-----------|-----------|-----------|--------|
| Identity Parsing | x-rh-identity header | Base64 JSON | Active |
| Bearer Token | INVENTORY_SHARED_SECRET | HTTP Header | Active |
| RBAC V1 | @rbac() decorator | HTTP to RBAC service | Active (groups, resource types) |
| Kessel V2 | @access() decorator | gRPC to Kessel | Phase 1 (flag-gated) |
| PSK Auth | X-RH-RBAC-PSK header | HTTP to RBAC service | Active (workspace creation) |

### Phase 2: Endpoint → Permission Map

Build the complete endpoint security matrix by combining OpenAPI spec paths with code decorators.

#### 2.1 Map operationId to Function

For every path+method in `swagger/api.spec.yaml` that has an `operationId`:
1. Parse the `operationId` into module + function (e.g., `api.host.get_host_list` → `api/host.py:get_host_list()`)
2. Find the function in the corresponding Python file
3. Extract the auth decorator(s) on that function

#### 2.2 Build Security Matrix

Present the complete matrix:

| # | Method | Path | operationId | Function | Decorator | Resource | Permission | ID Param | Auth Mechanism |
|---|--------|------|------------|----------|-----------|----------|------------|----------|---------------|
| 1 | GET | /hosts | api.host.get_host_list | get_host_list | @access | HOST | view | — | V2 (Kessel/V1) |
| 2 | DELETE | /hosts/{host_id_list} | api.host.delete_host_by_id | delete_host_by_id | @access | HOST | delete | host_id_list | V2 (Kessel/V1) |
| 3 | GET | /groups | api.group.get_group_list | get_group_list | @rbac | GROUPS | READ | — | V1 only |
| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |

Include every endpoint — do not omit any.

#### 2.3 Missing Decorator Check

Flag any endpoint function that does NOT have an `@rbac()` or `@access()` decorator:

| Function | File | Decorator | Status |
|----------|------|-----------|--------|
| get_host_list | api/host.py | @access(HOST.view) | OK |
| some_function | api/some.py | **NONE** | CRITICAL |

**Status rules:**
- Has `@rbac()` or `@access()`: **OK**
- No auth decorator: **CRITICAL** — endpoint is accessible without authorization
- Management endpoints (`api/mgmt.py`) may intentionally lack auth — note as **INFO** if they are health/status endpoints

### Phase 3: OpenAPI Spec Cross-Reference

Compare the spec's `security` declarations against the code-enforced auth.

#### 3.1 Spec Security Extraction

For every path+method in the spec, extract whether `security` is declared:
- `security: [{ApiKeyAuth: []}]` — requires x-rh-identity header
- `security: [{BearerAuth: []}]` — requires Bearer token
- `security: [{ApiKeyAuth: []}, {BearerAuth: []}]` — supports both
- No `security` key — unauthenticated (or inherits global security)

Check if a global `security` declaration exists at the spec root level.

#### 3.2 Cross-Reference

| # | Endpoint | Spec Security | Code Decorator | Status |
|---|----------|--------------|----------------|--------|
| 1 | GET /hosts | ApiKeyAuth | @access(HOST.view) | OK |
| 2 | GET /health | None | None | OK (management) |
| 3 | POST /hosts | ApiKeyAuth | **NONE** | FAIL |
| 4 | GET /custom | **None** | @access(HOST.view) | WARN |

**Status rules:**
- Both spec and code enforce auth: **OK**
- Spec declares security but code has no decorator: **FAIL** — spec promises auth that isn't enforced
- Code enforces auth but spec has no security declaration: **WARN** — spec should be updated
- Neither has auth (management/health endpoints): **OK** if intentional
- Neither has auth (data endpoints): **CRITICAL**

### Phase 4: Permission Level Validation

Verify that the permission level matches the HTTP method semantics.

#### 4.1 Method ↔ Permission Alignment

| HTTP Method | Expected Permission | Rationale |
|-------------|-------------------|-----------|
| GET | READ / view | Read-only operation |
| POST | WRITE / update / move_host | Creates or modifies resources |
| PUT | WRITE / update | Full resource replacement |
| PATCH | WRITE / update | Partial resource update |
| DELETE | WRITE / delete | Removes resources |

For each endpoint, check:

| # | Method | Path | Permission | Expected | Status |
|---|--------|------|------------|----------|--------|
| 1 | GET | /hosts | view (READ) | READ | OK |
| 2 | DELETE | /hosts/{id} | delete (WRITE) | WRITE | OK |
| 3 | GET | /groups | READ | READ | OK |

**Status rules:**
- Permission matches HTTP method semantics: **OK**
- GET with WRITE/update permission: **WARN** — over-permissioned
- POST/PATCH/DELETE with READ/view permission: **FAIL** — under-permissioned (write operation with read-only auth)

#### 4.2 Special Permission Patterns

Check these known special patterns:

**Dual decorators on staleness endpoints:**
Staleness endpoints (GET/POST/PATCH/DELETE /staleness) require BOTH staleness AND host permissions via stacked `@access()` decorators. Verify:
- Read endpoints: `@access(STALENESS.view)` + `@access(HOST.view)` — both present?
- Write endpoints: `@access(STALENESS.update)` + `@access(HOST.update)` — both present?
- Missing one decorator: **WARN**

**RBAC admin for resource types:**
Resource type endpoints use `@rbac(ALL, ADMIN, permission_base="rbac")`. Verify:
- `permission_base` is `"rbac"` (not default `"inventory"`)
- Permission is `ADMIN` (maps to `*`)

**Host-group operations use workspace permission:**
POST/DELETE on `/groups/{group_id}/hosts` use `@access(WORKSPACE.move_host, id_param="group_id")` — this is a workspace-level permission, not a host permission. Verify this pattern.

#### 4.3 System Identity Bypass

The `@rbac()` decorator allows system identities (cert-auth) to bypass RBAC checks for HOST resources only. Verify:
- System identity bypass is ONLY for `RbacResourceType.HOSTS`
- Non-HOST endpoints (groups, staleness) do NOT allow system identity bypass
- Search for test: `test_non_host_endpoints_cannot_bypass_RBAC`

### Phase 5: Auth Test Coverage

Search `tests/` for auth-related test coverage.

#### 5.1 Core Auth Tests

Search for test files and functions covering:

1. **Identity validation** (401 scenarios):
   ```
   Pattern: 401|missing.*identity|invalid.*identity|empty.*identity
   Path: tests/
   ```
   - Missing `x-rh-identity` header → 401
   - Invalid/malformed identity → 401
   - Empty identity → 401

2. **Permission denied** (403 scenarios):
   ```
   Pattern: 403|permission.*denied|forbidden|rbac.*denied
   Path: tests/
   ```
   - Valid identity but insufficient permissions → 403

3. **404 vs 403** (info leakage prevention):
   ```
   Pattern: 404.*403|nonexistent.*permission|not_found.*denied
   Path: tests/
   ```
   - Non-existent resource + denied → 404 (not 403)
   - Existing resource + denied → 403

4. **Read-only mode** (503 scenarios):
   ```
   Pattern: read.only|503|FLAG_INVENTORY_API_READ_ONLY
   Path: tests/
   ```

5. **System identity bypass**:
   ```
   Pattern: system.*identity|cert.*auth|bypass.*RBAC
   Path: tests/
   ```

6. **RBAC error handling**:
   ```
   Pattern: rbac.*retry|rbac.*error|rbac.*exception|rbac.*failure
   Path: tests/
   ```

#### 5.2 Per-Endpoint Auth Test Matrix

For each endpoint in the security matrix (Phase 2), search for a test that specifically verifies auth enforcement. Look for tests that:
- Call the endpoint with/without auth
- Mock RBAC/Kessel responses
- Verify 401/403 status codes

Present coverage:

| # | Endpoint | 401 Test | 403 Test | Bypass Test | Status |
|---|----------|----------|----------|-------------|--------|
| 1 | GET /hosts | Yes (shared) | Yes | N/A | OK |
| 2 | DELETE /hosts/{id} | Yes (shared) | Yes (read_only) | N/A | OK |
| 3 | POST /groups | Yes (shared) | Yes (read_only) | N/A | OK |
| 4 | GET /custom | No | No | No | WARN |

**Status rules:**
- Has both 401 and 403 tests (direct or shared): **OK**
- Missing 403 test: **WARN** — authorization enforcement not verified
- Missing 401 test: **WARN** — authentication enforcement not verified
- No auth tests at all: **WARN**

**Note:** Many auth tests are shared across endpoints (e.g., `test_api_auth.py` tests identity validation for all endpoint types). A shared test counts as coverage.

### Phase 6: RBAC V1 ↔ Kessel V2 Consistency

Audit the state of the RBAC V1 → Kessel V2 migration.

#### 6.1 Decorator Distribution

Count and categorize endpoints by auth mechanism:

| Auth Mechanism | Decorator | Endpoints | Examples |
|---------------|-----------|-----------|---------|
| V2 (Kessel/V1 fallback) | @access() | N | GET /hosts, DELETE /hosts/{id}, ... |
| V1 only | @rbac() | M | GET /groups, POST /groups, ... |
| None | — | K | /health, /metrics, ... |

#### 6.2 Migration Status

For each endpoint using `@rbac()` (V1 only), assess whether it should be migrated to `@access()`:

| Endpoint | Current | Migrate? | Blocker | Status |
|----------|---------|----------|---------|--------|
| GET /groups | @rbac(GROUPS, READ) | Yes | Kessel groups support | INFO |
| POST /groups | @rbac(GROUPS, WRITE) | Yes | Kessel groups support | INFO |
| GET /resource-types | @rbac(ALL, ADMIN, "rbac") | No | Admin-only, special permission_base | OK |

**Status rules:**
- Already on `@access()` (V2): **OK**
- On `@rbac()` (V1) with known migration blocker: **INFO** — expected, waiting on Kessel support
- On `@rbac()` (V1) with no blocker: **WARN** — should be migrated

#### 6.3 Kessel Feature Flag Consistency

Verify the `@access()` decorator properly handles both flag states:
- `FLAG_INVENTORY_KESSEL_PHASE_1` **enabled**: Uses `get_kessel_filter()` (gRPC)
- `FLAG_INVENTORY_KESSEL_PHASE_1` **disabled**: Falls back to `get_rbac_filter()` (HTTP)

Check:
- Is the flag check inside `access()` or in each endpoint? (Should be in decorator)
- Does the fallback work correctly when Kessel is unavailable?
- Are there any endpoints that call Kessel directly outside the decorator? (e.g., `api/host.py:get_host_list_by_insights_id()` — note this as **INFO** if it duplicates decorator logic)

#### 6.4 Bypass Flag Audit

Verify bypass flags are correctly handled:

| Bypass Flag | Default | Where Checked | Effect |
|------------|---------|--------------|--------|
| BYPASS_RBAC | false | @rbac(), @access() | Skips all permission checks |
| BYPASS_KESSEL | false | Kessel client, PSK calls | Disables Kessel operations |

- Are bypass flags checked BEFORE making external calls (RBAC/Kessel)? **OK** if yes
- Could a misconfigured bypass flag expose data? Note implications

### Phase 7: Summary Report

#### Endpoint Security Matrix

Present the complete matrix from Phase 2 (abbreviated — show all endpoints).

#### Overall Auth Health

| Check | Result | Issues |
|-------|--------|--------|
| Endpoints with auth decorators | N/M (%) | count without |
| Spec ↔ code security alignment | PASS/FAIL | count mismatches |
| Permission ↔ method alignment | PASS/WARN | count mismatches |
| Auth test coverage | N/M endpoints | count gaps |
| V1 → V2 migration progress | N on V2, M on V1 | count pending |

#### Overall Status

- **SECURE** — all endpoints have proper auth, permissions match methods, spec aligns with code
- **NEEDS ATTENTION** — gaps found that should be addressed
- **CRITICAL** — endpoints without auth decorators or permission mismatches found

#### Findings

Present ALL findings with WARN, FAIL, or CRITICAL status:

| # | Phase | Check | Status | Details | Recommendation |
|---|-------|-------|--------|---------|----------------|
| 1 | Decorator | description | CRITICAL/FAIL/WARN | details | fix |

#### Action Items

Ordered by severity:
1. **CRITICAL** — unauthenticated endpoints, spec/code mismatches
2. **FAIL** — write endpoints with read-only permissions
3. **WARN** — missing auth tests, spec security gaps, over-permissioned endpoints
4. **INFO** — V1→V2 migration candidates, system identity bypass patterns

For each item, provide file:line references and the recommended fix.

## Important Notes

- This command is **read-only** — it analyzes auth configuration but never modifies files.
- The `@access()` decorator is the Kessel-aware decorator. When `FLAG_INVENTORY_KESSEL_PHASE_1` is disabled, it falls back to V1 RBAC. This means ALL `@access()` endpoints work with BOTH auth mechanisms — it is NOT an error for an `@access()` endpoint to make V1 RBAC calls.
- Management endpoints (`/health`, `/metrics`, `/version`) intentionally lack auth decorators. Do not flag these as CRITICAL.
- The `validate_schema` endpoint in `api/system_profile.py` has an additional username check (`SP_AUTHORIZED_USERS`) beyond the `@access()` decorator — note this as a secondary auth gate.
- System identity bypass (cert-auth systems skipping RBAC) is intentional for HOST resources only. It allows Satellite, RHSM, and other trusted systems to manage hosts without user-level RBAC checks.
- Tests run with `bypass_rbac=True` and `bypass_kessel=True`, so auth tests must explicitly mock RBAC/Kessel responses to test enforcement. The bypass does NOT mean auth is untested — it means tests that DON'T mock auth are testing business logic, not auth.
- The `404 vs 403` behavior (returning 404 for non-existent resources instead of 403) is a security best practice to prevent resource enumeration attacks.
- Group endpoints currently use `@rbac()` (V1) because Kessel group support is pending. This is tracked and expected — flag as INFO, not WARN.
