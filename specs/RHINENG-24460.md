# Spec: RHINENG-24460

## Summary
Every GET /hosts request executes `SELECT COUNT(DISTINCT hosts.id)` with staleness OR conditions, causing a full sequential scan of all hosts in the org (416ms for a 466K-host org, 83ms for a 23K-host org). The staleness timestamp filter in `app/staleness_states.py` generates index-unfriendly OR conditions based on `last_check_in` arithmetic, preventing PostgreSQL from using btree indexes for the count query.

## Root Cause
In `api/host_query_db.py`, the `_get_host_list_using_filters` function (line 159) unconditionally calls `filtered_query.with_entities(func.count(Host.id.distinct())).scalar()` — issuing `SELECT COUNT(DISTINCT hosts.id)` — on every paginated host list request. The staleness filter (from `app/staleness_states.py` and `api/filtering/db_filters.py`) adds OR conditions like `now < last_check_in + stale_sec OR (now >= last_check_in + stale_sec AND now < last_check_in + warn_sec) OR ...` which are fundamentally incompatible with btree index lookups, forcing PostgreSQL to perform a full sequential scan of all rows in the org. Since the staleness filter is applied to every request (even when the user does not specify a staleness filter, it defaults to `ALL_STALENESS_STATES`), there is no escaping the expensive COUNT on the critical path.

## Affected Files
- `api/host_query_db.py`: This is where the expensive `COUNT(DISTINCT)` query is issued at line 159 inside `_get_host_list_using_filters`. The fix must go here: either make the count conditional (skip it by default or when a new `?count` parameter is absent), replace it with an estimated count (e.g., `pg_class.reltuples`), or delegate to a Redis-cached count. All public functions that call this (`get_host_list`, `get_host_list_by_id_list`, `get_host_list_for_views`) are also impacted.
- `api/host_query.py`: Contains `build_paginated_host_list_response`, which includes `'total': total` in the JSON response. If `total` is made optional/nullable (e.g., returns `null` when count is skipped), this function must be updated to handle a `None` total value. Currently the `total` field is always expected to be an integer.
- `api/host.py`: The GET /hosts handler function `get_host_list`. If a new `?count=true` query parameter is introduced to allow opt-in exact counting, the handler's parameter signature must be updated and the parameter passed down to the DB query layer.
- `api/host_views.py`: The GET /beta/hosts-view handler `get_host_views` also calls `get_host_list_for_views`, which in turn calls `_get_host_list_using_filters`. Any count-optimization changes need to be propagated to this endpoint as well.
- `swagger/api.spec.yaml`: The OpenAPI spec for GET /hosts and GET /beta/hosts-view. If a new `?count` query parameter is added, it must be declared here. If `total` becomes nullable, the schema reference `HostQueryOutput` (which references `PaginationOut`) must be updated.
- `swagger/pagination.yaml`: Defines `PaginationOut` schema with `total` as a required integer field. If the chosen approach makes `total` nullable (e.g., `null` when count is not requested), this schema definition must be updated to allow nullable and remove it from the `required` list.
- `api/cache.py`: Already contains the Redis client infrastructure used for staleness caching. If the chosen approach is to cache the count per org_id in Redis with a short TTL (option 3 or 4 from the ticket), new cache functions for host count storage/retrieval will need to be added here, similar to the existing `get_cached_staleness`/`set_cached_staleness` pattern.
- `app/staleness_states.py`: Defines `HostStalenessStatesDbFilters`, which generates the OR conditions (`fresh()`, `stale()`, `stale_warning()`) on `last_check_in` timestamp arithmetic that make the COUNT query index-unfriendly. Referenced by RHINENG-25499 as the underlying structural problem; changes here (e.g., switching to a pre-computed staleness column) would directly enable more efficient COUNT queries.
- `api/filtering/db_filters.py`: Contains `_staleness_filter` (line 296), which wraps the `HostStalenessStatesDbFilters` conditions in an `or_()` that is applied to every host query. The resulting filter is what forces the sequential scan during COUNT. Any change to how staleness filtering is structured (e.g., using an index-friendly pre-computed column) would need to be reflected here.
- `app/config.py`: Application configuration. If the chosen approach uses a threshold (e.g., estimated count only above 10K hosts) or a configurable TTL for cached counts, the threshold/TTL values should be declared as config properties here, consistent with existing patterns like `api_cache_timeout` and `api_staleness_cache_enabled`.

## Implementation Plan

### Step 1: Add two new config properties to the `Config.__init__` block (alongside the existing `staleness_cache_timeout` line at ~line 238): `self.host_count_cache_timeout = int(os.getenv('HOST_COUNT_CACHE_TIMEOUT_SECONDS', '120'))` and `self.host_count_cache_enabled = os.environ.get('INVENTORY_HOST_COUNT_CACHE_ENABLED', 'true').lower() == 'true'`. These mirror the existing `staleness_cache_timeout` / `api_staleness_cache_enabled` pattern.
- File: `app/config.py`
- Change type: modify
- Rationale: Provides a configurable TTL for the new per-org host-count Redis cache and an on/off flag. Defaulting to 120 seconds gives a reasonable balance between freshness and performance. The flag allows operators to disable it without a code change.

### Step 2: 1) Add a module-level flag `HOST_COUNT_L2_CACHE_ENABLED = False` alongside the existing `STALENESS_L2_CACHE_ENABLED` flag. 2) In `init_cache`, set `HOST_COUNT_L2_CACHE_ENABLED` to `True` when Redis is configured AND `app_config.host_count_cache_enabled` is `True` (follow the exact same pattern used for `STALENESS_L2_CACHE_ENABLED`). 3) Add a cache key prefix constant `HOST_COUNT_CACHE_KEY_PREFIX = 'hbi:hostcount:'`. 4) Add three functions following the staleness cache pattern:

```python
def get_cached_host_count(cache_key: str):
    if not HOST_COUNT_L2_CACHE_ENABLED:
        return None
    try:
        client = _get_redis_client()
        key = f"{HOST_COUNT_CACHE_KEY_PREFIX}{cache_key}"
        raw = client.get(key)
        if raw is None:
            return None
        return int(raw)
    except Exception as exc:
        logger.warning('Failed to get cached host count', exc_info=exc)
        return None

def set_cached_host_count(cache_key: str, count: int, timeout: int):
    if not HOST_COUNT_L2_CACHE_ENABLED:
        return
    try:
        client = _get_redis_client()
        key = f"{HOST_COUNT_CACHE_KEY_PREFIX}{cache_key}"
        client.set(key, str(count), ex=timeout)
    except Exception as exc:
        logger.exception('Failed to set cached host count', exc_info=exc)

def delete_cached_host_count(cache_key: str):
    if not HOST_COUNT_L2_CACHE_ENABLED:
        return
    try:
        client = _get_redis_client()
        key = f"{HOST_COUNT_CACHE_KEY_PREFIX}{cache_key}"
        client.delete(key)
    except Exception as exc:
        logger.exception('Failed to delete cached host count', exc_info=exc)
```
- File: `api/cache.py`
- Change type: modify
- Rationale: Reuses the existing Redis infrastructure and follows the same cache-aside pattern already used for staleness caching. Storing count as a plain integer string in Redis is lightweight and avoids serialization overhead.

### Step 3: 1) Add `import hashlib` to the imports at the top of the file. 2) Add imports `from api.cache import get_cached_host_count, set_cached_host_count` alongside existing cache imports. 3) Also import `from app.common import inventory_config` if not already present (needed to read `host_count_cache_timeout`). 4) In `_get_host_list_using_filters`, replace the single `count_total = filtered_query.with_entities(func.count(Host.id.distinct())).scalar()` line (currently at ~line 159) with:

```python
# Build a stable, deterministic cache key from org + filter hash to avoid per-request COUNT scan.
#
# NOTE on `all_filters` determinism: The `all_filters` list is constructed by `query_filters()`
# in `api/filtering/db_filters.py`, which appends filter clauses in a fixed, code-defined order
# (fqdn → display_name → hostname_or_id → insights_id → system_type → provider → timestamps →
# groups → tags → staleness → registered_with → rbac). For the same set of request parameters,
# the list order is always identical, so `str(all_filters)` is deterministic for equivalent requests.
#
# CAVEAT: The `md5(str(all_filters))` approach relies on SQLAlchemy's `__str__` representation
# of filter/clause objects remaining stable across versions. If SQLAlchemy changes its string
# output, cache keys will change — causing extra cache misses (not incorrect data). A more robust
# alternative is to construct the key from explicit, normalized filter inputs (e.g.,
# `org_id + sorted(filter_param_name=value)` pairs) passed down from `query_filters()`. This
# would require threading an additional `cache_key_components` dict through the call chain.
# The current approach is chosen for minimal code change; if cache fragmentation is observed
# after a SQLAlchemy upgrade, switch to the explicit key approach.
identity = get_current_identity()
filter_hash = hashlib.md5(str(all_filters).encode(), usedforsecurity=False).hexdigest()[:12]
count_cache_key = f"{identity.org_id}:{filter_hash}"

count_total = get_cached_host_count(count_cache_key)
if count_total is None:
    count_total = filtered_query.with_entities(func.count(Host.id.distinct())).scalar()
    cfg = inventory_config()
    set_cached_host_count(count_cache_key, count_total, timeout=cfg.host_count_cache_timeout)
```

No other changes to function signatures or callers are needed.
- File: `api/host_query_db.py`
- Change type: modify
- Rationale: This is the minimal surgical fix: the expensive COUNT query still runs on a cache miss, but subsequent requests within the TTL window (default 120s) are served from Redis in O(1) time. Using org_id + filter-hash as the key means different filter combinations (by display_name, tags, etc.) each get their own cache slot, preventing false hits. `hashlib.md5` with `usedforsecurity=False` is appropriate here since this is used as a hash key, not a cryptographic purpose. The existing `get_current_identity()` is already imported and called in this file. The `all_filters` list produced by `query_filters()` is constructed in a deterministic, fixed append order (see `api/filtering/db_filters.py` lines 489–585), so equivalent requests always produce the same `str()` output and the same cache key.

### Step 4: Create a new unit test file modelled on `tests/test_staleness_cache.py`. Tests should cover:

1. `test_get_cached_host_count_returns_none_when_cache_disabled` — patches `HOST_COUNT_L2_CACHE_ENABLED=False`, asserts `get_cached_host_count('key')` returns `None` without touching Redis.
2. `test_get_cached_host_count_cache_miss` — Redis returns `None`, asserts function returns `None`.
3. `test_get_cached_host_count_cache_hit` — Redis returns `b'12345'`, asserts function returns integer `12345`.
4. `test_set_cached_host_count_skips_when_disabled` — patches `HOST_COUNT_L2_CACHE_ENABLED=False`, asserts `mock_client.set` is never called.
5. `test_set_cached_host_count_stores_value` — asserts Redis `set` called with correct key prefix, string value, and `ex=timeout`.
6. `test_get_cached_host_count_degrades_on_redis_error` — `mock_client.get.side_effect = ConnectionError(...)`, asserts function returns `None` without raising.
7. `test_delete_cached_host_count` — asserts Redis `delete` called with the correct prefixed key.

Use helper functions `_mock_redis()` and `_host_count_cache_patches()` following the same pattern as `tests/test_staleness_cache.py`.
- File: `tests/test_host_count_cache.py`
- Change type: create
- Rationale: Validates the new caching functions in isolation (no DB needed), following established test patterns in the repository. Covers the happy path, cache miss/hit, disabled cache, and Redis failure (graceful degradation).

## Test Strategy
- Approach: Unit tests for the new cache functions in isolation using mock Redis (following `tests/test_staleness_cache.py` patterns), plus existing integration tests in `tests/test_api_hosts_get.py` should continue to pass unchanged since the `total` field is still returned as a non-null integer — the cache is transparent to the API contract.
- Test files: tests/test_host_count_cache.py, tests/test_api_hosts_get.py
- Coverage targets: get_cached_host_count returns None when HOST_COUNT_L2_CACHE_ENABLED is False, get_cached_host_count returns integer on cache hit, get_cached_host_count returns None on Redis error (graceful degradation), set_cached_host_count skips Redis when cache disabled, set_cached_host_count stores count as string with correct key prefix and TTL, delete_cached_host_count removes the correct Redis key, Existing GET /hosts tests remain green (total is still a non-null integer)

## Risk Notes
- The cache key uses `md5(str(all_filters))` — SQLAlchemy filter object `str()` output is generally stable for the same query parameters, but if the output format changes across SQLAlchemy versions, cache keys may change (causing extra cache misses, not incorrect data). A more robust long-term alternative is to build the cache key from explicit, normalized filter inputs (e.g., `org_id` + sorted `param_name=value` pairs) threaded through from `query_filters()`. The current approach is chosen for minimal diff size; see the implementation note in Step 3 for migration guidance.
- With a 120-second TTL, the displayed `total` may be stale by up to 2 minutes. Paginated UIs that compute 'page N of M' from `total` may briefly show an incorrect page count after bulk host additions/deletions. This is an acceptable tradeoff for the performance gain on large orgs.
- The first GET /hosts request after a cache miss (or on cold start) still runs the full `COUNT(DISTINCT)` query. For 466K-host orgs, this means the first request per 120s window still takes ~416ms.
- Cache invalidation on host insert/delete is NOT implemented in this minimal plan — the TTL provides eventual consistency. If stricter consistency is needed, `delete_cached_host_count` should be called from the following specific code paths:
  - **Host creation**: `lib/host_repository.py:add_host()` (line ~58) — after a new host is successfully committed, invalidate the cache for that org_id. Since `add_host` already has access to the identity/org_id, a call to `delete_cached_host_count(f"{org_id}:*")` (or a wildcard-based invalidation) could be added at the end of the function.
  - **Host deletion**: `lib/host_delete.py:delete_hosts()` (line ~68) and `lib/host_delete.py:_delete_host()` (line ~95) — after host records are removed. The `_delete_host` function receives the `Host` object (which contains `org_id`) and the `identity`, so it can call invalidation directly.
  - **Bulk deletion**: `api/host.py:delete_hosts_by_filter()` (line ~195) and `api/host.py:delete_all_hosts()` (line ~323) — these bulk operations could invalidate the cache for the requesting org after completion.
  - Note: Wildcard key deletion (e.g., invalidating all filter-variant cache keys for an org) requires `SCAN`-based iteration in Redis, which adds complexity. An alternative is to use a per-org generation counter as part of the cache key; incrementing the counter on any host mutation effectively invalidates all prior cache entries for that org without needing key enumeration.
  Implementing this increases scope significantly and is deferred to a follow-up ticket.
- inventory_config() must be callable from within _get_host_list_using_filters. Verify it is available in the Flask app context at request time (it should be, based on existing usage in the codebase).
- HOST_COUNT_L2_CACHE_ENABLED is only True when Redis is configured AND the new flag is enabled. In environments without Redis (e.g., NullCache), the code falls back to the original COUNT query — no regression.

## Constraints
- The `total` field is currently declared as a required integer in `swagger/pagination.yaml` (PaginationOut schema). Making it nullable would be a breaking API change for existing consumers (UI, API clients).
- The approach must be evaluated with the team and API consumers (per acceptance criteria) before implementation, as different options have different consumer-facing impacts.
- RHINENG-25499 (removing staleness timestamps in favour of a pre-computed staleness column) is a prerequisite that directly addresses the index-unfriendliness; the current ticket may be partially blocked until that work is done.
- Redis is already deployed and used for staleness caching (`api/cache.py`), so adding count caching there is feasible without new infrastructure — but introduces eventual consistency.
- If using `pg_class.reltuples` for estimated counts, the estimate is only updated after VACUUM/ANALYZE, so it can lag significantly in fast-changing orgs.
- Pagination correctness must be verified: if `total` is null or estimated, UIs that compute page ranges or show 'page N of M' may break or show incorrect values.
- Any new `?count` query parameter must be added to both `swagger/api.spec.yaml` and propagated through the connexion parameter binding in the handler functions.
- The `get_host_list_by_id_list` function also calls `_get_host_list_using_filters`, so it will be affected by any changes to the count mechanism.
