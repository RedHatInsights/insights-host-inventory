# Spec: RHINENG-20675

## Summary
Create a one-time job to clean up redundant custom staleness records where values are within one hour (3600 seconds) of the system defaults.

## Root Cause
Over time, some orgs have had custom staleness records written to the `staleness` table with values that are effectively the same as the system defaults (within ±3600 seconds / 1 hour). These redundant rows cause unnecessary overhead in queries (e.g., in host_reaper.py which iterates all staleness rows to apply custom filtering). The fix is a one-time cleanup job that deletes any staleness record whose three fields (`conventional_time_to_stale`, `conventional_time_to_stale_warning`, `conventional_time_to_delete`) are all within one hour of their respective system defaults (`CONVENTIONAL_TIME_TO_STALE_SECONDS=104400`, `CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS=604800`, `CONVENTIONAL_TIME_TO_DELETE_SECONDS=2592000`).

## Plan

- `jobs/clean_custom_staleness.py` (create): Create a new job script that queries all rows in the `Staleness` table and deletes any row where all three fields (`conventional_time_to_stale`, `conventional_time_to_stale_warning`, `conventional_time_to_delete`) are within ±3600 seconds of their respective system defaults imported from `app/culling.py`. For each deleted row, invalidate the `StalenessCache` for that `org_id`. Log a final summary of deleted vs. skipped counts. Model the overall structure (module-level `SUSPEND_JOB` guard, `run()` signature, `session_guard` usage, `DRY_RUN` default of true, `job_setup` bootstrapping, `excepthook`) directly on `jobs/update_staleness.py`.

- `deploy/clowdapp.yml` (modify): Add a new Job entry named `clean-custom-staleness` (after the existing `update-staleness` job block around line 2177 and before `delete-empty-org-groups`) pointing to `./jobs/clean_custom_staleness.py`, with `DRY_RUN` mapped to a new `CLEAN_STALENESS_DRY_RUN` parameter and `SUSPEND_JOB` mapped to `CLEAN_STALENESS_SUSPEND_JOB`. Also add the corresponding parameter definitions (with defaults `true`) in the parameters section alongside the existing `UPDATE_STALENESS_*` block (~line 3250), and add CPU/memory resource parameter definitions alongside the `CPU_REQUEST_UPDATE_STALENESS_JOB` block (~line 2888). Use the `update-staleness` job entry as the exact template.

- `tests/test_job_clean_custom_staleness.py` (create): Create a test file that covers: (1) rows with all three fields within ±3600s of defaults are deleted and cache is invalidated; (2) rows with any field outside the ±3600s threshold are preserved; (3) rows where only a subset of fields are within range are preserved (partial match does not trigger deletion); (4) dry-run mode logs but performs no deletion and no cache call; (5) `StalenessCache.delete` is called exactly once per deleted org. Model fixture usage and assertion patterns on `tests/test_job_update_staleness.py`.

## Notes
- The threshold check must be strictly `abs(value - default) <= 3600` for ALL THREE fields — a logical AND, not OR. Any weakening of this condition would delete non-redundant rows.
- Cache invalidation must happen after each successful DB delete, not batched at the end, to avoid a window where the DB row is gone but stale cache data is still served.
- DRY_RUN must default to `true` at the module level (read at import time) as well as inside `run()` to ensure safety even if env var is unset.
- This is a one-time CJI job; ensure SUSPEND_JOB defaults to `true` so it cannot accidentally run on every deploy.
- One hour is defined as 3600 seconds — the check must be `abs(record_value - default_value) <= 3600` for ALL THREE fields simultaneously.
- The job must default `DRY_RUN=true` and `SUSPEND_JOB=true` as a safety gate (consistent with `update_staleness.py`).
- Cache invalidation via `StalenessCache.delete(org_id)` must be performed for every deleted record to avoid serving stale (no-longer-existing) custom staleness data from Redis.
- This is a one-time / CJI-triggered job; it should not be scheduled to run continuously.
- The system default constants live in `app/culling.py` (`CONVENTIONAL_TIME_TO_STALE_SECONDS`, `CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS`, `CONVENTIONAL_TIME_TO_DELETE_SECONDS`) and must be imported rather than hard-coded.
- Use `session_guard` from `lib/db.py` for all writes to ensure rollback on failure.
- Follow the same `job_setup` bootstrapping pattern from `jobs/common.py` to correctly initialise the Flask app, DB session, and Prometheus metrics.
