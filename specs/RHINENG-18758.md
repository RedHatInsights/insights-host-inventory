# Spec: RHINENG-18758

## Summary
Cache doesn't get invalidated when we change staleness settings

## Root Cause
When custom staleness settings are created, updated, or deleted, the system-client cache for hosts in the organization is not invalidated. This causes subsequent 'GET /hosts?insights_id=...' requests to return stale cached values with old staleness timestamps.

## Plan

### Org-level generation counter

Instead of scanning Redis for all keys belonging to an org (which was removed in PR #4914 for performance), we introduce an org-level generation counter. This counter is included in every system cache key alongside the existing per-host generation counter. Incrementing it makes all existing cache entries for the org unreachable without a SCAN.

- `api/cache.py` (modify): Add two functions:
  - `get_org_cache_generation(org_id)`: reads the org generation counter from Redis key `flask_cache_org={org_id}:org_gen`. Returns 0 when Redis is unavailable or the key does not exist. When absent, lazily initialises to 0 with NX and the standard cache TTL, matching the pattern in `get_system_cache_generation`.
  - `increment_org_cache_generation(org_id)`: increments the org generation counter via `INCR` on key `flask_cache_org={org_id}:org_gen` and sets a TTL equal to the cache TTL. Uses a pipeline with `INCR` then `EXPIRE`, matching the pattern in `_invalidate_system_cache_redis`. Logs the new generation value. Silently catches exceptions.

- `api/cache_key.py` (modify): Add an `org_generation=0` parameter to `make_system_cache_key`. Append `:o{org_generation}` to the key after the existing `:g{generation}` segment (and before any subman delimiter). For example, the key becomes `insights_id={id}_org={org}_user=SYSTEM-{owner}:g{gen}:o{org_gen}`.

- `api/host.py` (modify): In the `get_hosts_by_id_list` function where the cached insights-client system query is built (around line 156), call `get_org_cache_generation(current_identity.org_id)` alongside the existing `get_system_cache_generation` call, and pass the result as `org_generation` to `make_system_cache_key`.

- `app/queue/host_mq.py` (modify): In `cache_ingested_system` (around line 1361), call `get_org_cache_generation(org_id)` and pass the result as `org_generation` to `make_system_cache_key`.

### Staleness mutation cache invalidation

- `api/staleness.py` (modify): Import `increment_org_cache_generation` from `api.cache`. Call `increment_org_cache_generation(org_id)` in the following places, only on successful mutation paths:
  1. In `_response_if_staleness_equivalent_to_system_defaults`, inside the `if remove_staleness_if_exists():` block, after `StalenessCache.delete(org_id)`.
  2. In `create_staleness`, after `StalenessCache.delete(org_id)` inside the `try` block (before `log_create_staleness_succeeded`). This runs only when `add_staleness` succeeds without raising `IntegrityError`.
  3. In `delete_staleness`, after `StalenessCache.delete(org_id)` inside the `try` block. This runs only when `remove_staleness` succeeds without raising `NoResultFound`.
  4. In `update_staleness`, after confirming the update succeeded — specifically after the `if updated_staleness is None: raise NoResultFound` check and before `log_patch_staleness_succeeded`. This ensures cache is not invalidated when `patch_staleness` returns `None` (no existing row).

### Tests

- `tests/api/staleness/test_staleness_create.py` (modify): Add a test that mocks `api.staleness.increment_org_cache_generation` and verifies it is called with the correct `org_id` when staleness is created.

- `tests/api/staleness/test_staleness_delete.py` (modify): Add a test that mocks `api.staleness.increment_org_cache_generation` and verifies it is called with the correct `org_id` when staleness is deleted. Use `mocker` and the existing `db_create_staleness_culling` fixture to set up the custom staleness row first.

- `tests/api/staleness/test_staleness_update.py` (modify): Add a test that mocks `api.staleness.increment_org_cache_generation` and verifies it is called with the correct `org_id` when staleness is updated. Use `mocker`, `api_patch`, and the existing `db_create_staleness_culling` fixture.

## Constraints
- Do not use `delete_cached_system_keys(org_id=org_id)` which triggers a wildcard Redis SCAN. Use org-level generation counter increment instead.
- Cache invalidation must happen only on successful mutations, not on error paths (e.g., IntegrityError, NoResultFound).
- In `update_staleness`, the `increment_org_cache_generation` call must be placed after the `if updated_staleness is None` check to avoid invalidating cache when the staleness row does not exist.
- The existing per-host `delete_cached_system_keys(insights_id=..., org_id=..., owner_id=...)` calls in `api/host.py` and `app/queue/host_mq.py` remain unchanged; those pass all three arguments and only increment one per-host counter.
