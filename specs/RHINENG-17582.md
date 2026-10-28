# Spec: RHINENG-17582

## Summary
Handle database deadlocks gracefully when deleting hosts closely after changing staleness settings.

## Root Cause
When deleting custom staleness settings and then deleting a host immediately, concurrent database transactions (possibly from background workers, other requests, or event listeners) can cause a deadlock on the hosts table. This results in a 500 OperationalError.

## Plan

- `api/host.py` (modify): Import `OperationalError` from `sqlalchemy.exc`, `OutboxSaveException` from `app.exceptions`, and `is_deadlock_error` from `lib.db`. In `_delete_host_list`, wrap the `delete_hosts` call and its result consumption (the list comprehension iterating over `result_list` and the subsequent tracking loop) in a try/except that catches both `OperationalError` and `OutboxSaveException`. For `OperationalError`, check via `is_deadlock_error(e)`. For `OutboxSaveException`, check if the underlying cause is a deadlock via `is_deadlock_error(e.__cause__)` (since `write_events_to_outbox_batch` wraps `SQLAlchemyError` in `OutboxSaveException` using `raise ... from db_error`). When the caught error is a deadlock, log a warning and call `flask.abort(409)` with a message indicating a concurrent operation conflict. Re-raise non-deadlock errors unchanged. Because the handler is inside `_delete_host_list`, it covers all three calling paths: `delete_host_by_id`, `delete_hosts_by_filter`, and `delete_all_hosts`.

- `tests/test_api_hosts_delete_by_id.py` (modify): Add a test that creates a host, then mocks `lib.host_delete.delete_hosts` (or the underlying `_delete_host_db_records`) to raise an `OperationalError` wrapping a `psycopg2.errors.DeadlockDetected`. Verify the API returns a 409 status. Model the test after the existing `test_attempt_delete_host_read_only` test which patches a dependency and asserts a non-200 response code. Import `OperationalError` from `sqlalchemy.exc` and `DeadlockDetected` from `psycopg2.errors`. Add a second test where the mock raises `OutboxSaveException` with a `DeadlockDetected`-caused `OperationalError` as its `__cause__`, and verify the API also returns 409.

## Constraints
- Non-deadlock `OperationalError` instances must still propagate as 500 errors — only DeadlockDetected should be converted to 409.
- Non-deadlock `OutboxSaveException` instances must also propagate unchanged.

## Known Limitations (out of scope for this fix)
- **Message ordering with rollback**: If a deadlock occurs after deletion events have already been published to Kafka (e.g., during a later batch's flush/commit), consumers may receive deletion events for hosts that were not actually deleted because the transaction rolled back. A full fix would require a transactional outbox pattern or post-commit message publishing, which is a larger architectural change. This should be tracked as a follow-up item.
- **Partial batch deletion retries**: When `delete_hosts` processes hosts in batches and a later batch deadlocks after earlier batches have already committed, the 409 response does not report which hosts were successfully deleted. A subsequent retry of the same ID list may fail `check_all_ids_found` for already-deleted hosts. A full fix would require returning partial progress in the 409 response body. This should also be tracked as a follow-up item.
