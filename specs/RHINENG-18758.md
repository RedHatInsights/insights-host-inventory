# Spec: RHINENG-18758

## Summary
Cache doesn't get invalidated when we change staleness settings

## Root Cause
When custom staleness settings are created, updated, or deleted, the system-client cache for hosts in the organization is not invalidated. This causes subsequent 'GET /hosts?insights_id=...' requests to return stale cached values with old staleness timestamps.

## Plan

- `api/staleness.py` (modify): Import `delete_cached_system_keys` from `api.cache` and call `delete_cached_system_keys(org_id=org_id)` in four places: (1) inside `_response_if_staleness_equivalent_to_system_defaults` after the existing `StalenessCache.delete(org_id)` call, (2) in `create_staleness` after `StalenessCache.delete(org_id)`, (3) in `delete_staleness` after `StalenessCache.delete(org_id)`, and (4) in `update_staleness` after `StalenessCache.delete(org_id)`. This follows the same pattern used in `api/host.py` and `app/queue/host_mq.py`.

- `tests/api/staleness/test_staleness_create.py` (modify): Add a test that mocks `api.staleness.delete_cached_system_keys` and verifies it is called with the correct `org_id` when staleness is created. Follow the mocking pattern used in `tests/mq/test_misc.py` for the same function.

- `tests/api/staleness/test_staleness_delete.py` (modify): Add a test that mocks `api.staleness.delete_cached_system_keys` and verifies it is called with the correct `org_id` when staleness is deleted. Use `mocker` and the existing `db_create_staleness_culling` fixture to set up the custom staleness row first.

- `tests/api/staleness/test_staleness_update.py` (modify): Add a test that mocks `api.staleness.delete_cached_system_keys` and verifies it is called with the correct `org_id` when staleness is updated. Use `mocker`, `api_patch`, and the existing `db_create_staleness_culling` fixture.

## Constraints
- The call must use the org_id-only form: delete_cached_system_keys(org_id=org_id), which triggers a wildcard scan for all system cache keys belonging to that org.
- Cache invalidation must happen only on successful mutations, not on error paths (e.g., IntegrityError, NoResultFound).
