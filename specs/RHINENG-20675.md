# Spec: RHINENG-20675

## Summary
Create a one-time job to clean up redundant custom staleness records that are within one hour (3600 seconds) of system defaults

## Root Cause
The `staleness` table contains custom staleness records for various org_ids. Some of these records have values that are effectively the same as the system defaults (within ±3600 seconds / 1 hour). These near-default records are redundant since the system already falls back to defaults when no custom record exists. The task is to delete such records to clean up the table. The system default values (from `app/culling.py`) are: `CONVENTIONAL_TIME_TO_STALE_SECONDS = 104400`, `CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS = 604800`, and `CONVENTIONAL_TIME_TO_DELETE_SECONDS = 2592000`. A record qualifies for deletion if all three of its field values are within 3600 seconds of their respective defaults.

## Plan

- `jobs/clean_custom_staleness.py` (create): Create the new job script. It should define a `THRESHOLD = 3600` constant, import the three system-default constants from `app.culling`, query all rows from the `Staleness` table, identify rows where all three fields are within `THRESHOLD` seconds of their respective defaults (using `abs(field - default) <= THRESHOLD`), log what will be deleted, and — when `DRY_RUN` is false — delete those rows via `session_guard` and call `StalenessCache.delete(org_id)` for each, handling cache failures gracefully. Must support `SUSPEND_JOB` and `DRY_RUN` env vars defaulting to `true`, following the structure of `jobs/update_staleness.py`.

- `tests/test_job_clean_custom_staleness.py` (create): Create a test file modelled on `tests/test_job_update_staleness.py`. Use the real DB (via `flask_app` fixture) and `db.session`. Cover: (1) records with all three fields exactly at the threshold boundary are deleted; (2) records with at least one field beyond the threshold are preserved; (3) `DRY_RUN=true` leaves all rows untouched and does not call `StalenessCache.delete`; (4) a mix of deletable and non-deletable rows in the same run; (5) `StalenessCache.delete` is called once per deleted org_id; (6) cache invalidation failure is swallowed without aborting the job.

- `deploy/clowdapp.yml` (modify): Add a new job block named `clean-custom-staleness` immediately after the `delete-empty-org-groups` block, mirroring its structure (image, args pointing to `./jobs/clean_custom_staleness.py`, the full set of shared env vars, plus `DRY_RUN` and `SUSPEND_JOB` referencing new parameters `CLEAN_CUSTOM_STALENESS_DRY_RUN` and `CLEAN_CUSTOM_STALENESS_SUSPEND_JOB`). Add four resource parameters (`CPU_REQUEST_CLEAN_CUSTOM_STALENESS_JOB`, `CPU_LIMIT_CLEAN_CUSTOM_STALENESS_JOB`, `MEMORY_REQUEST_CLEAN_CUSTOM_STALENESS_JOB`, `MEMORY_LIMIT_CLEAN_CUSTOM_STALENESS_JOB`) with the same default values as the `delete-empty-org-groups` equivalents, and add a `# -- Clean custom staleness Job --` parameter section with `CLEAN_CUSTOM_STALENESS_DRY_RUN` (default `true`) and `CLEAN_CUSTOM_STALENESS_SUSPEND_JOB` (default `true`).

- `deploy/cji.yml` (modify): Add a new `ClowdJobInvocation` entry named `clean-custom-staleness-${CLEAN_CUSTOM_STALENESS_RUN_NUMBER}` referencing the `clean-custom-staleness` job, directly after the `delete-empty-org-groups` CJI block. Add `CLEAN_CUSTOM_STALENESS_RUN_NUMBER` to the parameters section with a default value of `'1'`.

## Notes
- The threshold check must be applied to ALL three fields simultaneously — a record is only deleted when all three pass; partial matches must be preserved.
- DRY_RUN and SUSPEND_JOB must default to true to prevent accidental data loss on first deploy.
- Cache invalidation failures must be caught per-org so a single Redis error does not roll back DB deletes that already committed.
- The job queries all Staleness rows at once; if the table is very large this may need batching in a future iteration, but for a one-time cleanup this is acceptable.
- The deletion threshold of 'within one hour' means abs(field_value - default_value) <= 3600 for ALL three staleness fields simultaneously — a record is only deleted if all three fields pass the check.
- The job must default SUSPEND_JOB=true and DRY_RUN=true as a safety gate, consistent with all other jobs in the codebase.
- After deleting a staleness row, the StalenessCache must be invalidated for the affected org_id (using `StalenessCache.delete(org_id)`) to avoid stale cache entries, as done in `jobs/update_staleness.py`.
- This is a one-time / CJI-triggered job, not a recurring scheduled job — it should be invocable via ClowdJobInvocation.
- The job should handle cache invalidation failures gracefully (log but do not abort, since the DB write already succeeded), as per the pattern in `update_staleness.py`.
- The `Staleness` model (in `app/models/staleness.py`) does not have an `immutable` flag or soft-delete — hard deletes are appropriate and consistent with existing patterns.
