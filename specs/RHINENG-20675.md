# Spec: RHINENG-20675

## Summary
Create a one-time job to clean up existing custom staleness data by deleting records in the staleness table whose settings are within one hour of the system defaults.

## Root Cause
Over time, some organisations may have accumulated rows in the `staleness` table whose custom values are essentially identical to the system defaults (within ±1 hour). These rows are redundant because the system already applies the same defaults when no custom row exists. The existing `staleness_equivalent_to_system_defaults` helper in `lib/staleness.py` already codifies the one-hour tolerance rule (< 3600 s difference on each conventional field), but no job currently scans and cleans up those near-default rows in bulk.

## Affected Files
- `jobs/cleanup_custom_staleness.py`: New file to be created. This is the main one-time job that queries every row in the `staleness` table, checks whether each row's conventional staleness fields are within one hour of system defaults (reusing `lib.staleness.DEFAULT_STALENESS_EQUIVALENCE_TOLERANCE_SECONDS` / `staleness_equivalent_to_system_defaults` logic), and deletes redundant rows. Must follow the same structural pattern as `jobs/update_staleness.py` and `jobs/delete_empty_org_groups.py`: SUSPEND_JOB safety gate, DRY_RUN mode, `job_setup` for DB/event infrastructure, and cache invalidation via `StalenessCache.delete`.
- `tests/test_job_cleanup_custom_staleness.py`: New test file to be created. Should cover: dry-run mode (no deletions), actual deletion of near-default rows, preservation of genuinely custom rows, SUSPEND_JOB gate, cache invalidation calls, and boundary cases (exactly ±1 hour must NOT be deleted; < 1 hour must be deleted). Should follow the test patterns established in `tests/test_job_update_staleness.py`.
- `deploy/clowdapp.yml`: Must register the new `cleanup-custom-staleness` job under the `jobs:` list of the ClowdApp, with its container image, args pointing to `./jobs/cleanup_custom_staleness.py`, standard env vars (PYTHONPATH, DB, Kafka, PROMETHEUS_PUSHGATEWAY, DRY_RUN, SUSPEND_JOB), and resource limits/requests — mirroring the existing `update-staleness` job block (lines 2113–2177).
- `deploy/cji.yml`: Must add a new `ClowdJobInvocation` object for `cleanup-custom-staleness` (with a `CLEANUP_CUSTOM_STALENESS_RUN_NUMBER` parameter) so SREs can trigger the one-time cleanup via CJI, consistent with all other jobs already listed in this file.

## Implementation Plan

### Step 1: Create a new one-time job that queries all rows in the `Staleness` table and deletes any whose three conventional fields each differ from the system defaults by strictly less than `DEFAULT_STALENESS_EQUIVALENCE_TOLERANCE_SECONDS` (3600 s). The job must respect a `SUSPEND_JOB` safety gate (default true) and a `DRY_RUN` flag (default true), log each deletion candidate, call `StalenessCache.delete(org_id)` for every deleted row, and use `session_guard(session, close=False)`. Use the system-default constants from `app.culling` and the tolerance constant from `lib.staleness` directly—no HTTP identity context is needed.
- File: `jobs/cleanup_custom_staleness.py`
- Change type: create
- Rationale: This is the core deliverable: a safe, idempotent, operator-triggered script that removes redundant near-default staleness rows without touching genuinely custom ones. Modelled after `jobs/update_staleness.py` (SUSPEND_JOB/DRY_RUN/job_setup/StalenessCache pattern) and `jobs/delete_empty_org_groups.py` (bulk-scan-and-delete structure).

### Step 2: Create a test file that covers: (a) dry-run mode leaves all rows intact and does not call cache invalidation; (b) rows whose values match `JUST_UNDER_ONE_HOUR` (from `tests/helpers/staleness_test_constants.py`) are deleted and cache is invalidated; (c) rows matching `AT_EXACTLY_ONE_HOUR` (exactly 3600 s offset) are preserved; (d) rows matching `CUSTOM_STALENESS` (>> 1 h offset) are preserved; (e) a table with a mix of near-default and genuinely-custom rows only deletes the near-default ones; (f) SUSPEND_JOB causes immediate exit with code 0 before any DB access. Test structure and fixtures should follow `tests/test_job_update_staleness.py`.
- File: `tests/test_job_cleanup_custom_staleness.py`
- Change type: create
- Rationale: Tests are needed to verify the boundary conditions (strictly-less-than vs. exactly-one-hour), dry-run safety, and cache invalidation behaviour without requiring a full integration environment.

### Step 3: Insert a new `cleanup-custom-staleness` job entry in the `jobs:` list (after the `delete-empty-org-groups` entry), pointing args at `./jobs/cleanup_custom_staleness.py` and carrying the same standard env vars (PYTHONPATH, DB, Kafka, PROMETHEUS_PUSHGATEWAY, CLOWDER_ENABLED, NAMESPACE, REPLICA_NAMESPACE) plus `DRY_RUN` and `SUSPEND_JOB` mapped to new template parameters `CLEANUP_CUSTOM_STALENESS_DRY_RUN` and `CLEANUP_CUSTOM_STALENESS_SUSPEND_JOB`. Add the four resource limit/request parameters (`CPU_REQUEST_CLEANUP_CUSTOM_STALENESS_JOB`, etc.) in the parameters section with the same defaults as the `delete-empty-org-groups` job. Add the two new DRY_RUN/SUSPEND_JOB parameters in the parameters section (both defaulting to `'true'`), with descriptions analogous to the `DELETE_EMPTY_ORG_GROUPS_*` parameters.
- File: `deploy/clowdapp.yml`
- Change type: modify
- Rationale: Every job that can be invoked via CJI must be registered in the ClowdApp manifest. The SUSPEND_JOB and DRY_RUN defaults must be `true` so the job cannot accidentally run in production without explicit SRE override.

### Step 4: Add a new `ClowdJobInvocation` object for `cleanup-custom-staleness` (named `cleanup-custom-staleness-${CLEANUP_CUSTOM_STALENESS_RUN_NUMBER}`) before the `parameters:` block, and add `CLEANUP_CUSTOM_STALENESS_RUN_NUMBER` with a default value of `'1'` to the parameters list. Pattern is identical to the existing `delete-empty-org-groups` CJI block.
- File: `deploy/cji.yml`
- Change type: modify
- Rationale: SREs trigger one-time jobs via CJI; without this entry the job cannot be invoked through the standard operational workflow used for every other job in this file.

## Test Strategy
- Approach: Unit and integration tests in the new test file using the `flask_app` fixture (from `tests/fixtures/app_fixtures.py`) and the shared staleness constants from `tests/helpers/staleness_test_constants.py`. Tests insert rows directly via `db.session`, call `run()` with the appropriate monkeypatched env, and then assert DB state and `StalenessCache.delete` call counts. SUSPEND_JOB behaviour is tested by patching the module-level flag and checking `SystemExit(0)`.
- Test files: tests/test_job_cleanup_custom_staleness.py
- Coverage targets: Near-default rows (JUST_UNDER_ONE_HOUR) are deleted in live mode, Exactly-one-hour-offset rows (AT_EXACTLY_ONE_HOUR) are preserved, Genuinely custom rows (CUSTOM_STALENESS) are preserved, Mixed table: only near-default rows are removed, DRY_RUN=true leaves all rows intact and suppresses cache invalidation, SUSPEND_JOB=true exits immediately with code 0, StalenessCache.delete is called exactly once per deleted row, DRY_RUN defaults to true when env var is absent

## Risk Notes
- The strict-less-than boundary (< 3600, not <=) must be preserved exactly; an off-by-one would incorrectly delete rows at exactly one hour of deviation.
- All three conventional fields must be within tolerance simultaneously; a partial match must not trigger deletion.
- The job iterates and deletes one row at a time (ORM delete), which is safe for correctness but may be slow for very large staleness tables—acceptable for a one-time cleanup.
- Cache invalidation failure is non-fatal (DB write already committed); the job should log and continue rather than abort, consistent with the pattern in `jobs/update_staleness.py`.
- SUSPEND_JOB defaults to true in both code and ClowdApp parameters, so no accidental production execution is possible without an explicit parameter override in the CJI.

## Constraints
- The job is described as one-time but must ship with a SUSPEND_JOB=true default so it cannot accidentally run in production without an explicit SRE action (consistent with existing job conventions).
- DRY_RUN must default to true to prevent accidental data loss; callers must explicitly set DRY_RUN=false.
- The equivalence tolerance (3600 s = one hour) is defined in `lib/staleness.py` as `DEFAULT_STALENESS_EQUIVALENCE_TOLERANCE_SECONDS`. The job must use `< 3600` (strictly less than), not `<=`, matching the existing API logic.
- System defaults come from `app.culling` constants (CONVENTIONAL_TIME_TO_STALE_SECONDS=104400, CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS=604800, CONVENTIONAL_TIME_TO_DELETE_SECONDS=2592000). Since there is no HTTP request identity in a job context, pass `sys_defaults` explicitly to `staleness_equivalent_to_system_defaults` (the function accepts a keyword `sys_defaults` argument to bypass the identity-based lookup), or perform the comparison directly against the constants.
- After deleting a staleness row, `StalenessCache.delete(org_id)` should be called to invalidate any in-process cache for that org, matching the pattern in `jobs/update_staleness.py`.
- The session must be managed with `lib.db.session_guard` (with `close=False`) for consistency with other jobs.
- All three conventional fields must be within tolerance for a row to be deleted; if any one field is >= 1 hour from its default, the row is kept.
