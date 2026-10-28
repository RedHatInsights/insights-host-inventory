# Spec: RHINENG-17582

## Summary
When the `hbi.create_last_check_in_update_per_reporter_staleness` feature flag is enabled, deleting custom staleness settings triggers asynchronous `per_reporter_staleness` updates on all hosts in the org. If a user then immediately deletes a host (or performs another staleness operation), a PostgreSQL deadlock can occur between the background staleness update and the new request, resulting in an unhandled `OperationalError` that surfaces as an HTTP 500.

## Root Cause
Deleting a custom staleness record causes a cascade of host updates (`per_reporter_staleness` column). These updates acquire `ShareLock`s on host rows. If a concurrent request (e.g., `DELETE /hosts/<id>`) tries to delete one of those same host rows, PostgreSQL detects a deadlock between the two transactions and raises `psycopg2.errors.DeadlockDetected`. The staleness API endpoints (`delete_staleness`, `create_staleness`, `update_staleness`) do not catch `OperationalError`, so the exception propagates as an unhandled 500 error.

## Plan

- `api/staleness.py` (modify): Import `OperationalError` from `sqlalchemy.exc` and `is_deadlock_error` from `lib.db`. In the `delete_staleness`, `create_staleness`, and `update_staleness` functions, add an except clause for `OperationalError` that checks `is_deadlock_error`; when true, log the error and return a 503 Service Unavailable response via `json_error_response`. For non-deadlock `OperationalError`, re-raise to preserve existing behavior.

- `tests/test_api_staleness_delete.py` (modify): Add a test that uses `mocker.patch` on `api.staleness.remove_staleness` to raise an `OperationalError` wrapping a `psycopg2.errors.DeadlockDetected`, then calls `api_delete_staleness` and asserts the response status is 503. Also create a staleness record first via `db_create_staleness_culling` so the endpoint reaches the code path that calls `remove_staleness`.

## Constraints
- Non-deadlock OperationalError exceptions must still propagate normally (re-raise) to avoid masking genuine database failures.
