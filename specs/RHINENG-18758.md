# Spec: RHINENG-18758

## Summary
Cache doesn't get invalidated when we change staleness settings

## Root Cause
When custom staleness settings are created, updated, or deleted, the system-client cache for hosts in the organization is not invalidated. This causes subsequent 'GET /hosts?insights_id=...' requests to return stale cached values with old staleness timestamps.

## Design Decision
An org-level generation counter is used instead of a Redis SCAN-based key deletion. Calling `delete_cached_system_keys(org_id=org_id)` (without `insights_id` and `owner_id`) triggers `delete_keys` with a wildcard SCAN, which was previously removed in PR #4914 for performance reasons. Instead, incrementing a per-org generation counter is O(1) and makes all existing cache entries unreachable by changing the cache key they would be looked up under.

## Plan

- `api/cache.py` (modify): Add an org-level generation counter. Introduce `_org_generation_key(org_id)` that returns a Redis key such as `flask_cache_org={org_id}:org_gen`. Add `get_org_cache_generation(org_id)` that reads the org generation counter from Redis (lazily initialising to 0 with `SET NX` when absent, mirroring `get_system_cache_generation`). Add `get_system_cache_generations(insights_id, org_id, owner_id)` that fetches both the per-system generation and the per-org generation in a single `MGET` call, returning `(generation, org_generation)`. This avoids a second Redis round-trip on the MQ and API paths. Add `invalidate_org_system_cache(org_id)` that increments the org generation counter via `INCR`. The org generation counter must NOT have a TTL — it is permanent. An expired counter that resets to 0 could collide with a previously-cached key that used the same generation number, serving stale data. Since there is one key per org the memory cost is negligible. The counter is incremented in Redis at the call site, which is after the database commit performed inside the `lib/staleness.py` functions (`session_guard` commits before returning).

- `api/cache_key.py` (modify): Add an `org_generation` keyword argument (default 0) to `make_system_cache_key`. When `org_generation > 0`, change the key format from `…:g{generation}` to `…:g{generation}:o{org_generation}`. When `org_generation == 0` (the default, including all orgs that have never had a staleness change), the key format remains `…:g{generation}` — the `:o0` suffix is omitted. This preserves compatibility with existing cache entries at deploy time, preventing a cache-miss storm from every key changing format simultaneously. When the org generation counter is incremented, all previously-cached keys become unreachable because the new cache key no longer matches them.

- `api/host.py` (modify): Replace the `get_system_cache_generation` import with `get_system_cache_generations` from `api.cache`. At the point where `get_system_cache_generation` was called, call `get_system_cache_generations(insights_id, current_identity.org_id, owner_id)` instead, which returns `(generation, org_generation)` from a single `MGET`. Pass both values to `make_system_cache_key`.

- `app/queue/host_mq.py` (modify): Replace the `get_system_cache_generation` import with `get_system_cache_generations` from `api.cache`. At the point where `get_system_cache_generation` was called, call `get_system_cache_generations(insights_id, org_id, owner_id)` instead, which returns `(generation, org_generation)` from a single `MGET`. Pass both values to `make_system_cache_key`.

- `api/staleness.py` (modify): Import `invalidate_org_system_cache` from `api.cache` and call `invalidate_org_system_cache(org_id)` in four places, each after the database commit has completed: (1) inside `_response_if_staleness_equivalent_to_system_defaults`, after `StalenessCache.delete(org_id)` within the `if remove_staleness_if_exists()` block (the `session_guard` in `remove_staleness_if_exists` commits before returning True), (2) in `create_staleness`, after `StalenessCache.delete(org_id)` inside the try block (the `session_guard` in `add_staleness` commits before returning), (3) in `delete_staleness`, after `StalenessCache.delete(org_id)` inside the try block (the `session_guard` in `remove_staleness_if_exists` commits before the call returns), (4) in `update_staleness`, after confirming `updated_staleness is not None` — that is, after the `if updated_staleness is None: raise NoResultFound` check, not before it. The `db.session.commit()` in `patch_staleness` has already executed by this point. This avoids invalidating the cache when no staleness record exists (the 404 path).

- `tests/api/staleness/test_staleness_create.py` (modify): Add a test that mocks `api.staleness.invalidate_org_system_cache` and verifies it is called with the correct `org_id` after a successful staleness creation.

- `tests/api/staleness/test_staleness_delete.py` (modify): Add a test that mocks `api.staleness.invalidate_org_system_cache` and verifies it is called with the correct `org_id` after a successful staleness deletion. Use `mocker` and the existing `db_create_staleness_culling` fixture to set up the custom staleness row first.

- `tests/api/staleness/test_staleness_update.py` (modify): Add a test that mocks `api.staleness.invalidate_org_system_cache` and verifies it is called with the correct `org_id` after a successful staleness update. Use `mocker`, `api_patch`, and the existing `db_create_staleness_culling` fixture. Also verify the mock is NOT called when the staleness record does not exist (404 path).

- `tests/lib/test_utils.py` (modify): Add tests for `get_org_cache_generation` and `invalidate_org_system_cache` verifying correct Redis interactions (INCR, lazy init, no TTL on org counter).

## Constraints
- The org generation counter must use `INCR` (O(1)), NOT a SCAN-based approach.
- The org generation counter must NOT have a TTL. An expired counter that lazily resets to 0 can collide with a previously-cached key that used the same generation, returning stale data. One key per org makes the memory cost negligible.
- The `:o{org_generation}` suffix must be omitted from the cache key when `org_generation == 0`, so that existing cache entries remain reachable at deploy time and no cache-miss storm occurs.
- Cache invalidation in `update_staleness` must happen only after confirming `updated_staleness is not None`, not on the 404 error path.
- Cache invalidation must happen only on successful mutations, not on error paths (e.g., IntegrityError, NoResultFound).
- Both per-system and per-org generation counters must be fetched in a single `MGET` call (via `get_system_cache_generations`) to avoid doubling Redis round-trips.
- The org generation counter is recorded in Redis after the database commit that is performed inside the `lib/staleness.py` functions.
