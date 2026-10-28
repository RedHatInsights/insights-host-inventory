# Spec: RHINENG-17582

## Summary
Let's investigate further.

## Root Cause
Let's investigate further.

## Plan

- `api/staleness.py` (modify): Import `OperationalError` from `sqlalchemy.exc` and `is_deadlock_error` from `lib.db`. In the `delete_staleness`, `create_staleness`, and `update_staleness` functions, wrap the **entire** function body (after input validation) in a `try/except OperationalError` block. This must include the call to `_response_if_staleness_equivalent_to_system_defaults` in `create_staleness` and `update_staleness`, since that helper calls `remove_staleness_if_exists()` which performs a DB delete that can also deadlock. When `is_deadlock_error` returns true, log the error and return a 503 Service Unavailable response via `json_error_response`. For non-deadlock `OperationalError`, re-raise to preserve existing behavior.

- `tests/test_api_staleness_delete.py` (modify): Add a test that uses `mocker.patch` on `api.staleness.remove_staleness` to raise an `OperationalError` wrapping a `psycopg2.errors.DeadlockDetected`, then calls `api_delete_staleness` and asserts the response status is 503. Also create a staleness record first via `db_create_staleness_culling` so the endpoint reaches the code path that calls `remove_staleness`.

- `tests/test_api_staleness_create.py` (modify): Add a test that uses `mocker.patch` on `api.staleness.add_staleness` to raise an `OperationalError` wrapping a `psycopg2.errors.DeadlockDetected`, then calls the create staleness endpoint and asserts the response status is 503. Add a second test that patches `api.staleness.remove_staleness_if_exists` to deadlock during the default-equivalence check, verifying 503 is returned.

- `tests/test_api_staleness_update.py` (modify): Add a test that uses `mocker.patch` on `api.staleness.patch_staleness` to raise an `OperationalError` wrapping a `psycopg2.errors.DeadlockDetected`, then calls the update staleness endpoint and asserts the response status is 503. Add a second test that patches `api.staleness.remove_staleness_if_exists` to deadlock during the default-equivalence check, verifying 503 is returned.

## Constraints
- Non-deadlock OperationalError exceptions must still propagate normally (re-raise) to avoid masking genuine database failures.
- The deadlock handler in `create_staleness` and `update_staleness` must cover the call to `_response_if_staleness_equivalent_to_system_defaults`, since that helper invokes `remove_staleness_if_exists()` which can deadlock when deleting a custom staleness row that matches system defaults.
