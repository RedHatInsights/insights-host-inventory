# Spec: RHINENG-20675

## Summary
Create a one-time job to clean up redundant custom staleness records — deleting any staleness table row whose three staleness values are all within one hour (3600 s) of the system defaults.

## Root Cause
Over time, organisations have had custom staleness records created in the `staleness` table whose values are essentially identical to the system defaults (within ±3600 seconds). These records are redundant because the code already falls back to system defaults when no custom row exists. The ticket asks for a one-time cleanup job (following the existing CJI/job pattern) to identify and remove such near-default records, reducing noise in the table.

The three default values (from `app/culling.py`) are:
- `CONVENTIONAL_TIME_TO_STALE_SECONDS = 104400`
- `CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS = 604800`
- `CONVENTIONAL_TIME_TO_DELETE_SECONDS = 2592000`

A record should be deleted when `abs(row.field - default) <= 3600` holds true for **all three fields**.

## Affected Files
- `jobs/cleanup_custom_staleness.py`: New file to be created. Implements the one-time cleanup job that queries all rows in the `staleness` table, evaluates whether each row's three fields are within 3600 s of their respective system defaults, and deletes matching rows. Must follow the same DRY_RUN / SUSPEND_JOB safety-gate pattern used by `jobs/update_staleness.py` and `jobs/delete_empty_org_groups.py`.
- `tests/test_job_cleanup_custom_staleness.py`: New test file to be created. Should cover: rows within threshold are deleted (dry-run does not delete), rows outside threshold are preserved, mixed batches, DRY_RUN default=true safety, SUSPEND_JOB behaviour. Mirrors the structure of `tests/test_job_update_staleness.py` and `tests/test_job_delete_empty_org_groups.py`.
- `deploy/clowdapp.yml`: Needs a new `jobs` entry (similar to the existing `update-staleness` and `delete-empty-org-groups` entries at lines 2113 and 2178) that declares the new job's podSpec, environment variables (DRY_RUN, SUSPEND_JOB, PYTHONPATH, DB settings, Kafka settings, etc.), resource limits/requests, and corresponding template parameters.
- `deploy/cji.yml`: Needs a new `ClowdJobInvocation` object and a corresponding template parameter (e.g. `CLEANUP_CUSTOM_STALENESS_RUN_NUMBER`) so SREs can invoke the one-time cleanup job via a CJI, consistent with every other one-time job in the file.

## Implementation Plan

### Step 1: Create the new cleanup job script. It should:

1. Add a module-level docstring explaining the job's purpose and env vars (`DRY_RUN`, `SUSPEND_JOB`).
2. Set constants `PROMETHEUS_JOB = 'cleanup-custom-staleness'`, `LOGGER_NAME = 'cleanup_custom_staleness'`, `COLLECTED_METRICS: tuple = ()`, `ONE_HOUR = 3600`.
3. Read `SUSPEND_JOB` at module level: `SUSPEND_JOB = os.environ.get('SUSPEND_JOB', 'true').lower() == 'true'`.
4. Import `CONVENTIONAL_TIME_TO_DELETE_SECONDS`, `CONVENTIONAL_TIME_TO_STALE_SECONDS`, `CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS` from `app.culling`.
5. Import `Staleness` from `app.models`, `session_guard` from `lib.db`, `threadctx` from `app.logging`, plus `excepthook`/`job_setup` from `jobs.common`.
6. Define a module-level `SYSTEM_DEFAULTS` dict mapping the three field names to their default values.
7. Define a helper `_is_near_default(row: Staleness) -> bool` that returns `True` only when `abs(getattr(row, field) - default) <= ONE_HOUR` for **all three** fields (using `all()`).
8. Define `run(logger, session, application)`:
   - Read `dry_run = os.environ.get('DRY_RUN', 'true').lower() == 'true'`.
   - Inside `with application.app.app_context():`, set `threadctx.request_id = None`.
   - Query `rows = session.query(Staleness).all()`.
   - Filter with `_is_near_default`: collect `candidates` (list of matching rows) and `skipped` count.
   - Log total found, how many match, how many skipped.
   - Log each candidate's `org_id` and field values.
   - If `dry_run`, log `'DRY_RUN is enabled; no changes written.'` and return.
   - Otherwise, collect `org_ids_to_delete = [r.org_id for r in candidates]`; if empty, log and return.
   - Use `with session_guard(session, close=False):` to execute a bulk `session.query(Staleness).filter(Staleness.org_id.in_(org_ids_to_delete)).delete(synchronize_session=False)`.
   - Log total deleted count.
9. Add the `if __name__ == '__main__':` block mirroring `delete_empty_org_groups.py`: check `SUSPEND_JOB`, set `sys.excepthook`, call `job_setup`, call `run()`, close session.
- File: `jobs/cleanup_custom_staleness.py`
- Change type: create
- Rationale: This is the core job implementation. It follows the established pattern of `jobs/delete_empty_org_groups.py` and `jobs/update_staleness.py` for safety gates (SUSPEND_JOB, DRY_RUN defaulting to true) and transactional writes via session_guard.

### Step 2: Create a comprehensive test file covering:

1. **Imports**: `logging`, `pytest`, `Staleness`, `db` from `app.models`, `run` and `_is_near_default` from `jobs.cleanup_custom_staleness`, plus the three `CONVENTIONAL_TIME_TO_*_SECONDS` constants from `app.culling`.
2. **Test constants**: `ORG_DEFAULT = 'cleanup-staleness-org-default'`, `ORG_NEAR = 'cleanup-staleness-org-near'`, `ORG_FAR = 'cleanup-staleness-org-far'`, `ORG_OTHER = 'cleanup-staleness-org-other'`.
3. **Helper** `_get_staleness_row(org_id)` and `_stale_count()` querying Staleness table.
4. **Fixture** `_job_env(monkeypatch)` setting `DRY_RUN=false`.
5. **Unit tests for `_is_near_default`** (no DB needed):
   - Row with exact system defaults → `True`.
   - Row with all fields exactly at `default + 3600` → `True` (inclusive boundary).
   - Row with all fields exactly at `default - 3600` → `True` (inclusive boundary).
   - Row with one field at `default + 3601` → `False` (just outside threshold).
   - Row with stale far above default, others within threshold → `False`.
6. **Integration tests for `run()`**:
   - `test_run_deletes_near_default_rows`: create rows at/within threshold for two orgs; after run, those rows are gone.
   - `test_run_preserves_far_rows`: create a row with one field far outside threshold; after run, row still exists.
   - `test_run_mixed_batch`: create two rows — one near-default, one far; only the near-default row is deleted.
   - `test_run_dry_run_does_not_delete`: DRY_RUN=true; near-default row survives.
   - `test_run_dry_run_defaults_to_true`: delete DRY_RUN env var; near-default row survives (confirms safe default).
   - `test_run_empty_table`: run on empty staleness table; no errors, no deletions.
   - `test_run_boundary_inclusive_deletes`: create row at exactly ±3600 on each field; confirm deletion.
- File: `tests/test_job_cleanup_custom_staleness.py`
- Change type: create
- Rationale: Comprehensive tests ensure correctness of the threshold logic, dry-run safety, and DB interaction, mirroring the test style of `tests/test_job_delete_empty_org_groups.py` and `tests/test_job_update_staleness.py`.

### Step 3: Make two additions:

**A) New job block** — insert after the `delete-empty-org-groups` job block (after line ~2236) and before `run-db-migrations`:

```yaml
    - name: cleanup-custom-staleness
      restartPolicy: Never
      podSpec:
        image: ${IMAGE}:${IMAGE_TAG}
        args: [ "./jobs/cleanup_custom_staleness.py" ]
        env:
          - name: PYTHONPATH
            value: '/opt/app-root/src'
          - name: INVENTORY_LOG_LEVEL
            value: ${LOG_LEVEL}
          - name: INVENTORY_DB_SSL_MODE
            value: ${INVENTORY_DB_SSL_MODE}
          - name: INVENTORY_DB_SSL_CERT
            value: ${INVENTORY_DB_SSL_CERT}
          - name: INVENTORY_DB_SCHEMA
            value: "${INVENTORY_DB_SCHEMA}"
          - name: KAFKA_BOOTSTRAP_SERVERS
            value: ${KAFKA_BOOTSTRAP_HOST}:${KAFKA_BOOTSTRAP_PORT}
          - name: KAFKA_EVENT_TOPIC
            value: ${KAFKA_EVENT_TOPIC}
          - name: KAFKA_NOTIFICATION_TOPIC
            value: ${KAFKA_NOTIFICATION_TOPIC}
          - name: PAYLOAD_TRACKER_KAFKA_TOPIC
            value: ${PAYLOAD_TRACKER_KAFKA_TOPIC}
          - name: PAYLOAD_TRACKER_SERVICE_NAME
            value: inventory-mq-service
          - name: PAYLOAD_TRACKER_ENABLED
            value: 'true'
          - name: PROMETHEUS_PUSHGATEWAY
            value: ${PROMETHEUS_PUSHGATEWAY}
          - name: KAFKA_PRODUCER_ACKS
            value: ${KAFKA_PRODUCER_ACKS}
          - name: KAFKA_PRODUCER_RETRIES
            value: ${KAFKA_PRODUCER_RETRIES}
          - name: KAFKA_PRODUCER_RETRY_BACKOFF_MS
            value: ${KAFKA_PRODUCER_RETRY_BACKOFF_MS}
          - name: KAFKA_SECURITY_PROTOCOL
            value: ${KAFKA_SECURITY_PROTOCOL}
          - name: KAFKA_SASL_MECHANISM
            value: ${KAFKA_SASL_MECHANISM}
          - <<: *namespaceFieldRef
            name: NAMESPACE
          - name: CLOWDER_ENABLED
            value: "true"
          - name: DRY_RUN
            value: ${CLEANUP_CUSTOM_STALENESS_DRY_RUN}
          - name: SUSPEND_JOB
            value: ${CLEANUP_CUSTOM_STALENESS_SUSPEND_JOB}
          - name: REPLICA_NAMESPACE
            value: ${REPLICA_NAMESPACE}
        resources:
          limits:
            cpu: ${CPU_LIMIT_CLEANUP_CUSTOM_STALENESS_JOB}
            memory: ${MEMORY_LIMIT_CLEANUP_CUSTOM_STALENESS_JOB}
          requests:
            cpu: ${CPU_REQUEST_CLEANUP_CUSTOM_STALENESS_JOB}
            memory: ${MEMORY_REQUEST_CLEANUP_CUSTOM_STALENESS_JOB}
```

**B) New template parameters** — append after the `DELETE_EMPTY_ORG_GROUPS_ORG_IDS` parameter block (around line ~3265):

```yaml
# -- Cleanup custom staleness Job --
- name: CLEANUP_CUSTOM_STALENESS_DRY_RUN
  description: Whether the cleanup-custom-staleness job should run in dry-run mode
  value: 'true'
- name: CLEANUP_CUSTOM_STALENESS_SUSPEND_JOB
  description: Whether the cleanup-custom-staleness job should be suspended
  value: 'true'
- name: CPU_REQUEST_CLEANUP_CUSTOM_STALENESS_JOB
  value: 250m
- name: CPU_LIMIT_CLEANUP_CUSTOM_STALENESS_JOB
  value: 500m
- name: MEMORY_REQUEST_CLEANUP_CUSTOM_STALENESS_JOB
  value: 256Mi
- name: MEMORY_LIMIT_CLEANUP_CUSTOM_STALENESS_JOB
  value: 512Mi
```
- File: `deploy/clowdapp.yml`
- Change type: modify
- Rationale: Registers the new job in Clowder so it can be managed and invoked in all environments, following the identical structure of existing jobs (`update-staleness`, `delete-empty-org-groups`).

### Step 4: Make two additions:

**A) New CJI object** — append before the `parameters:` section:

```yaml
- apiVersion: cloud.redhat.com/v1alpha1
  kind: ClowdJobInvocation
  metadata:
    labels:
      app: host-inventory
    name: cleanup-custom-staleness-${CLEANUP_CUSTOM_STALENESS_RUN_NUMBER}
  spec:
    appName: host-inventory
    jobs:
      - cleanup-custom-staleness
```

**B) New parameter** — append to the parameters list:

```yaml
- name: CLEANUP_CUSTOM_STALENESS_RUN_NUMBER
  value: '1'
```
- File: `deploy/cji.yml`
- Change type: modify
- Rationale: Adds the CJI entry so SREs can trigger the one-time cleanup job via `oc process` / AppSRE tooling, consistent with every other one-time job in the file (e.g., `update-staleness`, `delete-empty-org-groups`).

## Test Strategy
- Approach: Integration tests use the existing Flask/SQLAlchemy test fixtures (`flask_app`, `db.session`) to insert Staleness rows directly, invoke `run()`, then assert DB state. Unit tests for `_is_near_default` use in-memory Staleness objects (no DB required) to verify boundary logic exhaustively.
- Test files: tests/test_job_cleanup_custom_staleness.py
- Coverage targets: _is_near_default returns True for exact default values, _is_near_default returns True at inclusive ±3600s boundary on all three fields, _is_near_default returns False when any single field exceeds 3600s from default, run() deletes rows within threshold when DRY_RUN=false, run() preserves rows outside threshold, run() handles mixed batch correctly (delete near-default, keep far-from-default), run() does not delete anything when DRY_RUN=true, run() defaults DRY_RUN to true when env var is unset (safety gate), run() is a no-op on an empty staleness table

## Risk Notes
- SUSPEND_JOB and DRY_RUN both default to 'true', preventing accidental deletions on first deployment — verify these defaults are preserved in both the Python module and the clowdapp.yml parameters.
- The bulk delete uses `synchronize_session=False` for efficiency; this is safe here because the session is not reused after the delete within the same request context.
- The `session_guard` wraps the delete, so any DB error will trigger a rollback; confirm `lib/db.py::session_guard` behaves as expected (commit on success, rollback on exception).
- All three fields must be within threshold simultaneously — the `all()` predicate in `_is_near_default` enforces this; a bug that uses `any()` instead would cause catastrophic data loss.
- No cache invalidation is needed here (unlike `update_staleness.py`) because we are only deleting rows; the code already falls back to system defaults when no row exists, so stale cache entries will simply be evicted naturally.

## Constraints
- The job must default SUSPEND_JOB=true and DRY_RUN=true to prevent accidental mass deletions on first deployment.
- Deletion logic must check ALL three fields simultaneously; a record should only be deleted if every field is within 3600 s of its default — not just one or two.
- The one-hour threshold (3600 s) should be treated as an inclusive range: abs(value - default) <= 3600.
- No DB schema migrations are required; the job only reads from and deletes rows in the existing `staleness` table.
- The job is one-time / CJI-triggered, not a scheduled recurring cron job.
- Care must be taken with the SQLAlchemy session: use `session_guard` from `lib/db.py` for the delete operation so rollback happens on error.
