# /hbi-spec-sync - API Spec ↔ Code Consistency Check

Validate that the OpenAPI spec (`swagger/api.spec.yaml`) and the Python endpoint implementations stay in sync. Catches drift before it reaches PR review.

## Instructions

### Phase 1: Load Sources

1. Read the OpenAPI spec:
   ```
   cat swagger/api.spec.yaml
   ```

2. Read the system profile spec:
   ```
   cat swagger/system_profile.spec.yaml
   ```

3. Read the Connexion initialization to understand the resolver pattern:
   ```
   Read app/__init__.py
   ```
   Identify how `RestyResolver("api")` maps `operationId` values to Python functions.

4. Read all API endpoint modules:
   - `api/host.py`
   - `api/host_views.py`
   - `api/group.py`
   - `api/staleness.py`
   - `api/system_profile.py`
   - `api/tag.py`
   - `api/resource_type.py`
   - `api/host_group.py`

5. Read query and filtering logic:
   - `api/host_query_db.py` — for `params_to_order_by()`, `ORDER_BY_STATIC_PROFILE_FIELDS`, sort/filter mappings
   - `api/filtering/db_filters.py`
   - `api/filtering/db_custom_filters.py`
   - `api/parsing.py` — for deep object parameter parsing

6. Read serialization and validation:
   - `app/serialization.py`
   - `app/custom_validator.py`

### Phase 2: Check operationId → Function Mapping

For every path+method in the spec that has an `operationId`:

1. Extract the `operationId` (e.g., `api.host.get_host_list`).
2. Parse it into module path + function name (e.g., `api/host.py` → `get_host_list()`).
3. Verify the function exists in the corresponding Python file.
4. Report any `operationId` that points to a missing function.

Present results:

| operationId | Expected File | Function | Status |
|-------------|---------------|----------|--------|
| api.host.get_host_list | api/host.py | get_host_list | OK/MISSING |
| ... | ... | ... | ... |

### Phase 3: Check Parameter Names

For each endpoint, compare spec parameter names against Python function arguments:

1. From the spec, collect all `parameters` (path, query, header) defined on the path or operation, including `$ref` resolved parameters from `components/parameters`.
2. From the Python function, collect argument names from the function signature.
3. Compare:
   - **Spec param not in function args** — the endpoint will fail at runtime if Connexion passes a parameter the function doesn't accept (unless `**kwargs` is used).
   - **Function arg not in spec** — the argument will always be `None`; could be intentional (internal args) or a missing spec param.

Ignore these known internal arguments that don't come from the spec:
- `body` (request body)
- `user` (injected by auth)
- `rbac_filter` (injected by RBAC middleware)
- `identity` (injected by auth)

Present mismatches only (skip OK results to reduce noise):

| Endpoint | Direction | Parameter | Details |
|----------|-----------|-----------|---------|
| GET /hosts | spec → code | new_param | Not in function signature |
| GET /hosts | code → spec | internal_arg | Not in spec (verify intentional) |

### Phase 4: Check Enum Consistency

#### 4.1 Order-By Enums

1. From the spec, extract the `enum` values from `hostOrderByParam` (and any other `*OrderByParam` components).
2. From `api/host_query_db.py`, read the `params_to_order_by()` function and extract all handled values from the `if/elif` chain.
3. Compare:
   - **Enum value in spec but not handled in code** — will raise `ValueError` at runtime.
   - **Value handled in code but not in spec** — dead code, or spec needs updating.

4. Also check `ORDER_BY_STATIC_PROFILE_FIELDS` — values listed here require a join to `HostStaticSystemProfile`. Verify the join logic exists for each.

#### 4.2 Order-How Enum

1. From the spec, extract the `OrderHow` schema pattern or enum (ASC/DESC).
2. From `params_to_order_by()`, check how `order_how` is compared.
3. Flag if spec allows case-insensitive (regex pattern) but code does case-sensitive comparison.

#### 4.3 Staleness Enums

1. From the spec, extract the `stalenessParam` enum values.
2. From the code, find where staleness values are validated or used.
3. Compare for mismatches.

#### 4.4 Group Order-By Enums

1. From the spec, extract any group-specific `orderByParam`.
2. From `api/group.py`, find the ordering logic.
3. Compare.

Present results:

| Enum | Spec Values | Code Values | Status |
|------|-------------|-------------|--------|
| hostOrderBy | display_name, group_name, updated, operating_system, last_check_in | (values from code) | MATCH/MISMATCH |
| orderHow | ASC, DESC | ASC, DESC | MATCH/WARN (case sensitivity) |
| staleness | fresh, stale, stale_warning, unknown | (values from code) | MATCH/MISMATCH |

### Phase 5: Check Default Values

For parameters that have `default` in the spec:

1. Extract the default value from the spec.
2. Find where the corresponding Python function applies a default when the parameter is `None` or missing.
3. Flag if the defaults differ.

Key defaults to check:
- `per_page` — spec default vs code default
- `page` — spec default vs code default
- `order_by` — spec default vs code default
- `order_how` — spec default vs code default
- `staleness` — spec default array vs code default

### Phase 6: Check Response Schema Consistency

For the main endpoints (`GET /hosts`, `GET /groups`, `GET /hosts/{host_id_list}`):

1. From the spec, extract the response schema field names (e.g., `HostQueryOutput` has `total`, `count`, `page`, `per_page`, `results`).
2. From `app/serialization.py` and the endpoint functions, extract the response dict keys.
3. Flag any field present in spec but missing from serialized output, or vice versa.

Focus on top-level pagination fields and the main `results` item structure. Do not deep-compare every nested field (the system profile spec handles that).

### Phase 7: Check System Profile Field Sync

1. From `swagger/system_profile.spec.yaml`, extract all top-level field names under `SystemProfile.properties`.
2. From `api/filtering/db_custom_filters.py`, extract which fields have filter handlers.
3. From `app/custom_validator.py`, check which fields are validated for sparse field selection.
4. Flag:
   - Fields in spec with no filter handler (may be intentional — not all fields are filterable)
   - Fields with filter handlers that don't exist in spec (dead code)

Present as a summary count, not a line-by-line list (the system profile has many fields):

| Check | Count | Details |
|-------|-------|---------|
| Spec fields | N | total in system_profile.spec.yaml |
| Fields with filter handlers | M | in db_custom_filters.py |
| Filter handlers for non-spec fields | X | list them if any |
| Spec fields without filters | Y | expected for non-filterable fields |

### Phase 8: Summary Report

Present the final results:

#### Overall Status

State one of:
- **IN SYNC** — no mismatches found
- **DRIFT DETECTED** — mismatches found that should be addressed

#### Findings Summary

| Check | Result | Issues |
|-------|--------|--------|
| operationId → function | PASS/FAIL | count and brief description |
| Parameter names | PASS/FAIL | count and brief description |
| Enum consistency | PASS/FAIL | count and brief description |
| Default values | PASS/WARN | count and brief description |
| Response schemas | PASS/FAIL | count and brief description |
| System profile fields | PASS/WARN | count and brief description |

#### Action Items

If any issues were found, list them as concrete actions ordered by severity:
1. **CRITICAL** — will cause runtime errors (missing functions, unhandled enums)
2. **WARNING** — may cause unexpected behavior (mismatched defaults, case sensitivity)
3. **INFO** — cosmetic or potential future issues (dead code, missing filters)

For each action item, provide the exact file:line references for both the spec and the code that need to be updated.

## Important Notes

- This command is read-only — it does not modify any files.
- When resolving `$ref` in the spec, follow the reference to get the actual parameter/schema definition.
- The `swagger/openapi.json` is the bundled version with all `$ref` resolved — prefer reading it if the YAML references are hard to follow.
- Some parameters are defined at the path level (shared across all methods on that path) and some at the operation level. Check both.
- Focus on substance: a parameter being optional in spec but having a default in code is normal — only flag when the default values actually differ.
