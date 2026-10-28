# Spec: RHINENG-17582

## Summary
Let's investigate further.

## Root Cause
Let's investigate further.

## Plan

- `api/staleness.py` (modify): Import `OperationalError` from `sqlalchemy.exc` and `is_deadlock_error` from `lib.db`. In the `delete_staleness`, `create_staleness`, and `update_staleness` functions, add an except clause for `OperationalError` that checks `is_deadlock_error`; when true, log the error and return a 503 Service Unavailable response via `json_error_response`. For non-deadlock `OperationalError`, re-raise to preserve existing behavior.

- `tests/test_api_staleness_delete.py` (modify): Add a test that uses `mocker.patch` on `api.staleness.remove_staleness` to raise an `OperationalError` wrapping a `psycopg2.errors.DeadlockDetected`, then calls `api_delete_staleness` and asserts the response status is 503. Also create a staleness record first via `db_create_staleness_culling` so the endpoint reaches the code path that calls `remove_staleness`.

## Constraints
- Non-deadlock OperationalError exceptions must still propagate normally (re-raise) to avoid masking genuine database failures.
