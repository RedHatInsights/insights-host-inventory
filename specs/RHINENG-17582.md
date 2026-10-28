# Spec: RHINENG-17582

## Summary
Handle database deadlocks gracefully when deleting hosts closely after changing staleness settings.

## Root Cause
When deleting custom staleness settings and then deleting a host immediately, concurrent database transactions (possibly from background workers, other requests, or event listeners) can cause a deadlock on the hosts table. This results in a 500 OperationalError.

## Plan

- `api/host.py` (modify): Import `OperationalError` from `sqlalchemy.exc` and `is_deadlock_error` from `lib.db`. In `_delete_host_list`, wrap the `delete_hosts` call and its result consumption in a try/except for `OperationalError`. When the caught error is a deadlock (checked via `is_deadlock_error`), log a warning and call `flask.abort(409)` with a message indicating a concurrent operation conflict. Re-raise non-deadlock `OperationalError` instances unchanged.

- `tests/test_api_hosts_delete_by_id.py` (modify): Add a test that creates a host, then mocks `lib.host_delete.delete_hosts` (or the underlying `_delete_host_db_records`) to raise an `OperationalError` wrapping a `psycopg2.errors.DeadlockDetected`. Verify the API returns a 409 status. Model the test after the existing `test_attempt_delete_host_read_only` test which patches a dependency and asserts a non-200 response code. Import `OperationalError` from `sqlalchemy.exc` and `DeadlockDetected` from `psycopg2.errors`.

## Constraints
- Non-deadlock OperationalError instances must still propagate as 500 errors — only DeadlockDetected should be converted to 409.
