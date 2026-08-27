# Spec: RHINENG-20675

## Summary
Create a one-time cleanup job that scans every row in the `staleness` table and deletes any record whose custom staleness values are all within one hour (3600 seconds) of the system defaults, since such records are effectively redundant.

## Root Cause
Over time, custom staleness records have been written into the `staleness` table for org IDs whose values are functionally equivalent to the system defaults (within ±3600 s). These near-default records are redundant: they bloat the table and cause unnecessary cache lookups / joins in the host-reaper path (`filter_hosts_in_state_using_custom_staleness` in `jobs/host_reaper.py` queries every `Staleness` row). The existing API and the recently-added `update_staleness.py` job create/update rows but provide no way to bulk-delete near-default rows. A dedicated one-off cleanup job is therefore needed.

## Plan

- `jobs/cleanup_custom_staleness.py` (create): Create a new job that queries all rows in the `Staleness` table, identifies those where every field (`conventional_time_to_stale`, `conventional_time_to_stale_warning`, `conventional_time_to_delete`) is within ±`TOLERANCE` of its respective system default (imported from `app.culling`), logs the candidates, and — unless `DRY_RUN=true` — collects the qualifying row IDs/org_ids, issues a single bulk `DELETE` (or batched deletes if the candidate set is very large) inside one `session_guard` block, and then calls `StalenessCache.delete(org_id)` for each deleted org_id. This mirrors the bulk-delete pattern used in `jobs/delete_empty_org_groups.py` and avoids per-row transaction overhead. Read `TOLERANCE` from the `CLEANUP_STALENESS_TOLERANCE` environment variable (default `3600` seconds). Follow the SUSPEND_JOB / DRY_RUN guard pattern and `__main__` block from `jobs/update_staleness.py` and `jobs/delete_empty_org_groups.py`.

- `tests/test_job_cleanup_custom_staleness.py` (create): Create a test file covering: rows with all three fields within tolerance are deleted and their cache entries invalidated; rows with any field outside tolerance are kept; a mix of qualifying and non-qualifying rows in the same run is handled correctly; `DRY_RUN=true` leaves the DB unchanged and skips cache invalidation; `SUSPEND_JOB=true` exits early; custom `CLEANUP_STALENESS_TOLERANCE` env var is respected (e.g., a tighter tolerance keeps rows that would be deleted under the default). Model fixtures and patching approach after `tests/test_job_update_staleness.py`, patching `StalenessCache` to verify `delete` call counts.

- `deploy/clowdapp.yml` (modify): Add a new `cleanup-custom-staleness` job spec block immediately after the `delete-empty-org-groups` job block (around line 2236), mirroring the same env-var set (PYTHONPATH, LOG_LEVEL, DB SSL, KAFKA, PROMETHEUS, CLOWDER_ENABLED, DRY_RUN, SUSPEND_JOB, REPLICA_NAMESPACE) with `DRY_RUN` bound to `${CLEANUP_CUSTOM_STALENESS_DRY_RUN}`, `SUSPEND_JOB` bound to `${CLEANUP_CUSTOM_STALENESS_SUSPEND_JOB}`, and `CLEANUP_STALENESS_TOLERANCE` bound to `${CLEANUP_STALENESS_TOLERANCE}`. Add resource-limit parameters (`CPU_REQUEST/LIMIT_CLEANUP_CUSTOM_STALENESS_JOB`, `MEMORY_REQUEST/LIMIT_CLEANUP_CUSTOM_STALENESS_JOB`) alongside the existing job resource params (after line 2902), and add the job-control parameters (`CLEANUP_CUSTOM_STALENESS_DRY_RUN` defaulting to `'true'`, `CLEANUP_CUSTOM_STALENESS_SUSPEND_JOB` defaulting to `'true'`, `CLEANUP_STALENESS_TOLERANCE` defaulting to `'3600'`) alongside the existing staleness job params (after the `DELETE_EMPTY_ORG_GROUPS_*` block near line 3265).

- `deploy/cji.yml` (modify): Add a new `ClowdJobInvocation` object for `cleanup-custom-staleness` (referencing the job by name, following the `delete-empty-org-groups` entry at the end of the objects list), and add a corresponding `CLEANUP_CUSTOM_STALENESS_RUN_NUMBER` parameter with default value `'1'` alongside the existing run-number parameters.

## Constraints
- All three staleness fields must simultaneously be within ±TOLERANCE of their defaults for a row to be deleted — any single field outside tolerance keeps the whole row.
- SUSPEND_JOB and DRY_RUN must both default to 'true' so accidental production runs are safe.
- Qualifying rows should be deleted using a bulk `DELETE` statement (or batched deletes for very large candidate sets) inside a single `session_guard` block, rather than per-row transactions, to minimise transaction overhead. Cache invalidation (`StalenessCache.delete`) is still called per org_id after the delete.
- No database schema migrations may be introduced.
- The job must be idempotent: a second run when no near-default rows remain must be a clean no-op.
