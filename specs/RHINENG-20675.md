# Spec: RHINENG-20675

## Summary
Create a one-time job to clean up redundant custom staleness records that are within one hour of the system defaults

## Root Cause
The staleness table contains custom records for org_ids where the configured values are essentially identical to system defaults (within 1 hour / 3600 seconds). These records are redundant because the system already falls back to defaults when no custom row exists. The cleanup logic (checking if values are within one hour of defaults) is already encoded in `lib/staleness.py`'s `DEFAULT_STALENESS_EQUIVALENCE_TOLERANCE_SECONDS = 3600` constant and `staleness_equivalent_to_system_defaults()`. What is missing is a standalone job that iterates all rows in the `staleness` table, identifies those within tolerance of the defaults for all three conventional fields, deletes them, and invalidates their caches.

## Affected Files
- `jobs/cleanup_custom_staleness.py`: This new file needs to be created. It is the main cleanup job that: (1) reads all rows from the Staleness model, (2) for each row, guards against NULL conventional fields (skip and log a warning if any field is `None`), then checks `conventional_time_to_stale`, `conventional_time_to_stale_warning`, and `conventional_time_to_delete` against the system defaults from `app/culling.py` using the `DEFAULT_STALENESS_EQUIVALENCE_TOLERANCE_SECONDS` constant imported from `lib/staleness.py` (do not hardcode the tolerance value), (3) deletes matching rows via the session, (4) invalidates the Redis cache for each deleted org_id via `StalenessCache.delete()`, and (5) supports `DRY_RUN` and `SUSPEND_JOB` safety-gate env vars following the same pattern as `jobs/update_staleness.py` and `jobs/delete_empty_org_groups.py`.
- `deploy/clowdapp.yml`: A new job entry must be added under the `jobs` list (following the pattern of `delete-empty-org-groups` at line 2178) with its `args`, environment variables, and resource limits. Corresponding parameters (e.g. `CLEANUP_CUSTOM_STALENESS_DRY_RUN`, `CLEANUP_CUSTOM_STALENESS_SUSPEND_JOB`, CPU/memory limits) must be added to the `parameters` section at the bottom of the file.
- `deploy/cji.yml`: A new `ClowdJobInvocation` entry and a corresponding run-number parameter (e.g. `CLEANUP_CUSTOM_STALENESS_RUN_NUMBER`) must be added, following the same pattern as the `delete-empty-org-groups` CJI at lines 107-115.
- `tests/test_job_cleanup_custom_staleness.py`: A new unit-test file should be created (matching the pattern of `tests/test_job_update_staleness.py` and `tests/test_job_delete_empty_org_groups.py`) to cover: rows within tolerance being deleted, rows outside tolerance being retained, DRY_RUN mode preventing writes, cache invalidation being called per deleted org, and the SUSPEND_JOB early-exit path.

## Implementation Plan

### Step 1: Create the cleanup job following the structure of `jobs/update_staleness.py` and `jobs/delete_empty_org_groups.py`. The `run()` function queries all rows from `Staleness`, checks each row's three conventional fields (`conventional_time_to_stale`, `conventional_time_to_stale_warning`, `conventional_time_to_delete`) against the system defaults imported from `app/culling.py`, and flags rows where every field differs by strictly less than the tolerance. The tolerance value must be imported from `lib/staleness.py` as `DEFAULT_STALENESS_EQUIVALENCE_TOLERANCE_SECONDS` — do NOT hardcode `3600`; reusing the existing constant avoids divergence if the tolerance is ever updated. Before performing the `abs()` comparison on each field, the code must explicitly check for `None` (NULL) values: if any of the three conventional fields is `None`, the row must be skipped (retained) and a warning logged (e.g. `logger.warning("Skipping org_id %s: field %s is NULL", ...)`). This prevents `abs()` from raising a `TypeError` or silently coercing `None`. Flagged rows are logged, then — when not in `DRY_RUN` mode — deleted via `session.delete()` inside `session_guard(session, close=False)`, followed by `StalenessCache.delete(org_id)` for each deleted org. The `__main__` block honours the `SUSPEND_JOB` gate (default `true`) and uses `job_setup` + `excepthook` consistent with the existing jobs.
- File: `jobs/cleanup_custom_staleness.py`
- Change type: create
- Rationale: This is the core of the feature: a standalone, safe-by-default (DRY_RUN=true, SUSPEND_JOB=true) job that iterates the staleness table and removes rows whose values are within one hour of the system defaults, using the tolerance already defined in `lib/staleness.py`.

### Step 2: Add a new job entry named `cleanup-custom-staleness` in the `jobs:` list after the `delete-empty-org-groups` entry (around line 2237), with `args: ["./jobs/cleanup_custom_staleness.py"]`, the standard environment variables block (PYTHONPATH, logging, DB, Kafka, Clowder), plus `DRY_RUN: ${CLEANUP_CUSTOM_STALENESS_DRY_RUN}` and `SUSPEND_JOB: ${CLEANUP_CUSTOM_STALENESS_SUSPEND_JOB}`. Add corresponding parameters (`CLEANUP_CUSTOM_STALENESS_DRY_RUN`, `CLEANUP_CUSTOM_STALENESS_SUSPEND_JOB`, CPU/memory request/limit parameters) near the `DELETE_EMPTY_ORG_GROUPS` parameters block, using the same default values and structure.
- File: `deploy/clowdapp.yml`
- Change type: modify
- Rationale: The job must be declared in clowdapp.yml to be deployable as a Clowder job, following the existing convention used by all other CJI-triggered jobs.

### Step 3: Add a new `ClowdJobInvocation` object named `cleanup-custom-staleness-${CLEANUP_CUSTOM_STALENESS_RUN_NUMBER}` referencing the `cleanup-custom-staleness` job, and add `CLEANUP_CUSTOM_STALENESS_RUN_NUMBER` with default `'1'` to the `parameters` list. Follow the identical structure used by the `delete-empty-org-groups` CJI at lines 107–115.
- File: `deploy/cji.yml`
- Change type: modify
- Rationale: All CJI-triggered one-time jobs in this repo require a corresponding entry in `cji.yml` so SREs can invoke them via the OpenShift template.

### Step 4: Create a test file modelled after `tests/test_job_update_staleness.py` and `tests/test_job_delete_empty_org_groups.py`. Tests should cover: (1) rows with all three conventional fields within tolerance (<3600s of defaults) are deleted; (2) rows with at least one field at exactly 3600s from the default are retained (boundary test); (3) rows with at least one field more than 3600s from the default are retained; (4) rows with any conventional field set to `None` (NULL) are retained and a warning is logged; (5) `DRY_RUN=true` logs intended deletes but makes no DB writes; (6) `DRY_RUN` env var absent defaults to `true` and makes no writes; (7) `StalenessCache.delete` is called exactly once per deleted org_id and not called for retained rows; (8) a no-op run when the staleness table is empty completes without error.
- File: `tests/test_job_cleanup_custom_staleness.py`
- Change type: create
- Rationale: Unit/integration tests ensure the tolerance logic, DRY_RUN guard, and cache invalidation all behave correctly, including the strict-less-than boundary case that the analysis specifically calls out.

## Test Strategy
- Approach: Integration tests using the existing `flask_app` and `db.session` fixtures (same pattern as `test_job_update_staleness.py`) to write real `Staleness` rows, invoke `run()`, and assert DB state afterward. Mock `StalenessCache.delete` with `unittest.mock.patch` to verify cache invalidation calls without needing Redis.
- Test files: tests/test_job_cleanup_custom_staleness.py
- Coverage targets: Rows where all conventional fields differ from defaults by <3600s are deleted, Rows where any conventional field differs from defaults by exactly 3600s are NOT deleted (boundary), Rows where any conventional field differs from defaults by >3600s are NOT deleted, Rows with any conventional field set to NULL are retained (not deleted) and a warning is logged, DRY_RUN=true prevents any DB deletion, DRY_RUN defaults to true when env var is absent, StalenessCache.delete is called once per deleted org_id, StalenessCache.delete is not called for retained rows, Empty staleness table results in a no-op run

## Risk Notes
- The tolerance is strictly less than 3600 seconds — a difference of exactly 3600s must NOT trigger deletion. Tests must explicitly assert this boundary.
- Both DRY_RUN and SUSPEND_JOB must default to 'true' to prevent accidental data loss if the job is deployed without explicit configuration.
- Cache invalidation via StalenessCache.delete() must happen after the DB delete is committed (within session_guard), not before, to avoid a window where cache is empty but DB row still exists.
- If a Staleness row has a NULL value for any conventional field (unlikely given the model defaults, but possible from legacy data), the `abs()` comparison would raise a `TypeError`. The job must explicitly branch on `None` before calling `abs()` — treat NULL as not-equivalent-to-defaults (i.e., skip/retain the row) and log a warning. Do not rely on exception handling or silent coercion.
- The job fetches all staleness rows at once; for very large tables this could be memory-intensive, but staleness table size is bounded by org count and should be manageable.

## Constraints
- The tolerance check must use `abs(value - default) < DEFAULT_STALENESS_EQUIVALENCE_TOLERANCE_SECONDS` where the constant is imported from `lib/staleness.py` (currently `60 * 60 = 3600`). The value must NOT be hardcoded — reuse the constant to stay consistent with `staleness_equivalent_to_system_defaults()`. A difference of exactly 3600 seconds must NOT be treated as equivalent (strictly less than).
- All three conventional fields (`conventional_time_to_stale`, `conventional_time_to_stale_warning`, `conventional_time_to_delete`) must be within tolerance for a row to be deleted.
- The job must default to `DRY_RUN=true` and `SUSPEND_JOB=true` to prevent accidental data loss when deployed.
- Cache invalidation (`StalenessCache.delete(org_id)`) must be called for each deleted row to avoid serving stale cached data from Redis.
- The system defaults to compare against are defined as constants in `app/culling.py`: `CONVENTIONAL_TIME_TO_STALE_SECONDS=104400`, `CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS=604800`, `CONVENTIONAL_TIME_TO_DELETE_SECONDS=2592000`. These should be used directly rather than going through the config/API path to avoid needing an Identity object.
- This is described as a one-time (CJI-triggered) job, so it belongs in the `jobs/` directory and must be registered in the `deploy/clowdapp.yml` jobs list and `deploy/cji.yml`.
- The session should use `session_guard(session, close=False)` from `lib/db.py` consistent with other jobs that commit but don't close the session mid-run.
