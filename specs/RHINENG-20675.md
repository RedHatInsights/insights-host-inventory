# Spec: RHINENG-20675

## Summary
Create a one-time job to clean up redundant custom staleness records — deleting any row in the `staleness` table whose values are all within one hour (3600 seconds) of the system defaults.

## Root Cause
Over time, some orgs have had custom staleness rows created that are effectively equivalent to the system defaults (within ±3600 s on every field). These redundant rows add noise to the staleness table and make the fallback-to-default path less meaningful. There is no bug per se; this is a data hygiene task requiring a new one-time cleanup job following the same pattern already used by `jobs/update_staleness.py` and `jobs/delete_empty_org_groups.py`.

## Plan

- `jobs/clean_custom_staleness.py` (create): Create the new one-time job script. Model the overall structure (module docstring, `SUSPEND_JOB`/`DRY_RUN` env-flag helpers, `PROMETHEUS_JOB`, `COLLECTED_METRICS`, `job_setup`, `session_guard`, `__main__` guard) after `jobs/delete_empty_org_groups.py`. In the `run()` function, import the three system-default constants from `app.culling`, query all rows from the `Staleness` table, and collect those where every field's absolute deviation from its system default is at most 3600 seconds. Log which org_ids would be deleted. If `DRY_RUN` is true, return early. Otherwise, delete each qualifying row inside a `session_guard` block and call `StalenessCache.delete(org_id)` for each (log and continue on cache-invalidation failure). The function should be idempotent — an empty qualifying set is a valid no-op.

- `deploy/clowdapp.yml` (modify): Add a `clean-custom-staleness` job entry to the `jobs:` list, modelled after the `delete-empty-org-groups` block (same common env vars: `PYTHONPATH`, `INVENTORY_LOG_LEVEL`, `INVENTORY_DB_*`, Kafka vars, `CLOWDER_ENABLED`, `NAMESPACE`, `REPLICA_NAMESPACE`) but with only `DRY_RUN` set to `${CLEAN_CUSTOM_STALENESS_DRY_RUN}` and `SUSPEND_JOB` set to `${CLEAN_CUSTOM_STALENESS_SUSPEND_JOB}` as job-specific env vars and `args: ["./jobs/clean_custom_staleness.py"]`. Add four resource parameters (`CPU_REQUEST_CLEAN_CUSTOM_STALENESS_JOB`, `CPU_LIMIT_CLEAN_CUSTOM_STALENESS_JOB`, `MEMORY_REQUEST_CLEAN_CUSTOM_STALENESS_JOB`, `MEMORY_LIMIT_CLEAN_CUSTOM_STALENESS_JOB`) near the other job resource parameters, and add `CLEAN_CUSTOM_STALENESS_DRY_RUN` (default `'true'`) and `CLEAN_CUSTOM_STALENESS_SUSPEND_JOB` (default `'true'`) in the parameters section alongside the `DELETE_EMPTY_ORG_GROUPS_*` parameters.

- `deploy/cji.yml` (modify): Append a new `ClowdJobInvocation` object for `clean-custom-staleness` (following the same label/name/spec pattern as the `delete-empty-org-groups` CJI entry), and add `CLEAN_CUSTOM_STALENESS_RUN_NUMBER` with a default value of `'1'` to the parameters list.

- `tests/test_job_clean_custom_staleness.py` (create): Create a test file following the structure of `tests/test_job_update_staleness.py`. Include unit tests for the boundary filter: a row with all three fields exactly 3600 s from defaults is deleted; a row with any single field 3601 s from its default is retained. Add integration tests using `flask_app` and `db.session` for: happy-path deletion (qualifying rows removed, non-qualifying rows kept), dry-run mode (no rows deleted, `StalenessCache.delete` not called), cache invalidation called per deleted org_id, and idempotency (second run on an already-clean table is a no-op). Mock `StalenessCache` where needed.

## Notes
- SUSPEND_JOB and DRY_RUN must both default to 'true' in clowdapp.yml to prevent accidental mass deletion on first deploy.
- The ±3600 s tolerance applies to all three fields simultaneously; a partial match must not trigger deletion.
- StalenessCache.delete failures should be caught and logged without rolling back the DB delete, consistent with update_staleness.py.
- The job is idempotent but irreversible — deleted rows cannot be recovered without re-creating them via update_staleness.py, so the DRY_RUN default is critical.
- The SUSPEND_JOB flag must default to `true` (safety gate) so the job does not run accidentally on first deploy.
- DRY_RUN must default to `true` for the same reason, matching the pattern of `update_staleness.py` and `delete_empty_org_groups.py`.
- The within-one-hour check applies to ALL three fields simultaneously — a record is only deleted if every field is within 3600 s of its default; a single out-of-range field means the row is left untouched.
- System defaults are `CONVENTIONAL_TIME_TO_STALE_SECONDS = 104400`, `CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS = 604800`, `CONVENTIONAL_TIME_TO_DELETE_SECONDS = 2592000` (from `app/culling.py`).
- Cache invalidation via `StalenessCache.delete(org_id)` should be called for each deleted org_id (or failures should be logged without failing the job), consistent with the pattern in `update_staleness.py`.
- The job should commit deletes in batches or within a `session_guard` context to avoid long-lived transactions on a large table.
- This is a one-time (botfix) job, so it should be safe to run multiple times (idempotent — re-running when no qualifying rows remain is a no-op).
