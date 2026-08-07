# Spec: RHINENG-24460

## Summary
The GET /hosts endpoint runs a slow SELECT COUNT(DISTINCT hosts.id) query on every request, causing sequential scans of all org hosts due to index-unfriendly staleness OR filter conditions. This results in 416ms latency for a 466K-host org and 83ms for a 23K-host org.

## Root Cause
In `api/host_query_db.py`, the `_get_host_list_using_filters` function unconditionally executes `filtered_query.with_entities(func.count(Host.id.distinct())).scalar()` on every paginated request. The staleness filter applied via `_staleness_filter` in `api/filtering/db_filters.py` generates OR conditions on timestamp fields (e.g., `stale_timestamp < X OR (stale_timestamp >= X AND stale_warning_timestamp < Y)`) that no btree index can serve efficiently, forcing a sequential scan of all hosts belonging to the org. Since this COUNT query runs before pagination (and before the early-exit check for zero results), it is always executed regardless of whether the caller needs a total count.

## Affected Files
- `api/host_query_db.py`: Contains `_get_host_list_using_filters` which runs `func.count(Host.id.distinct())` unconditionally. This is the primary place the slow COUNT query is issued. Also contains `get_host_list`, `get_host_list_by_id_list`, and `get_host_list_for_views` which all call `_get_host_list_using_filters` and would need to propagate a new `count` flag or implement an alternative counting strategy (e.g., pg_class.reltuples estimate).
- `api/host.py`: Contains the `get_host_list` API handler that calls `get_host_list_from_db` (imported from `api/host_query_db.py`). If a `?count=true` optional parameter is added, this handler needs to accept and forward that parameter. It also builds the final JSON response using `build_paginated_host_list_response`.
- `api/host_query.py`: Contains `build_paginated_host_list_response` which currently always places the `total` count into the response dict. If the optional-count approach is chosen, this function must handle `total=None` and emit it as null in the response JSON.
- `api/host_views.py`: Calls `get_host_list_for_views` from `api/host_query_db.py` and places `total` in the response. The same count-skipping logic would need to be threaded through this view endpoint as well.
- `swagger/api.spec.yaml`: The OpenAPI spec defines the GET /hosts endpoint parameters. Adding a `?count=true` query parameter requires updating the spec here. The HostQueryOutput schema references PaginationOut which currently requires `total` to be a non-null integer.
- `swagger/pagination.yaml`: Defines the `PaginationOut` schema with `total` as a required non-null integer. If total is to be optional/nullable when count is not requested, this schema must be updated to mark `total` as nullable or remove it from `required`.

## Implementation Plan

### Step 1: Make `total` nullable in the `Total` schema (add `nullable: true`) so the OpenAPI spec accepts `null` as a valid value. Keep `total` in the `required` list of `PaginationOut` so it is always present in the response body (just null when not computed).
- File: `swagger/pagination.yaml`
- Change type: modify
- Rationale: The default behaviour will now return `total: null` when the `?count=true` query parameter is not supplied. The schema must allow null to avoid spec validation errors.

### Step 2: 1) Add a `countParam` boolean query parameter definition under `components/parameters`:
```yaml
countParam:
  in: query
  name: count
  schema:
    type: boolean
    default: false
  description: >-
    When true, execute a COUNT query and return the exact total number of
    matching hosts. When false (default), skip the COUNT query and return
    total: null. Omitting this parameter is equivalent to count=false.
  required: false
```
2) Add `- $ref: '#/components/parameters/countParam'` to the parameters list of GET /hosts (line ~54).
3) Add `- $ref: '#/components/parameters/countParam'` to the parameters list of GET /beta/hosts-view (line ~140).
- File: `swagger/api.spec.yaml`
- Change type: modify
- Rationale: The parameter must be declared in the OpenAPI spec so connexion parses it from the request and injects it as a keyword argument into the handler functions.

### Step 3: Three sub-changes:

(A) Add `skip_count: bool = True` parameter to `_get_host_list_using_filters`. When `skip_count=True`, skip the `filtered_query.with_entities(func.count(Host.id.distinct())).scalar()` call entirely and set `count_total = None`. Also skip the early-exit `if count_total == 0` block (it relies on the count). The paginated query still runs; SQLAlchemy returns an empty list naturally when there are no results. Change return type hint from `int` to `int | None`.

(B) Add `count: bool = False` keyword parameter (at the end, before `rbac_filter`) to `get_host_list`. Pass `skip_count=not count` in the call to `_get_host_list_using_filters`.

(C) Add `count: bool = False` keyword parameter (at the end) to `get_host_list_for_views`. Pass `skip_count=not count` in the call to `_get_host_list_using_filters`.

Leave `get_host_list_by_id_list` unchanged — it feeds `check_all_ids_found` which requires a real integer total.
- File: `api/host_query_db.py`
- Change type: modify
- Rationale: This is the core change that eliminates the slow `SELECT COUNT(DISTINCT hosts.id)` query on the common (no-`?count=true`) path. The flag propagates from the API layer to the DB layer.

### Step 4: Add `count=False` as a keyword argument to the `get_host_list` view function (connexion injects it from the `?count` query param). Forward it to `get_host_list_from_db` (i.e., `get_host_list` imported from `api/host_query_db.py`) by passing `count=count` at the call site.
- File: `api/host.py`
- Change type: modify
- Rationale: The handler must accept the new query parameter from the HTTP layer and pass it down to the DB layer. Without this change the parameter is silently ignored.

### Step 5: Add `count=False` as a keyword argument to the `get_host_views` view function. Forward it to `get_host_list_for_views` by passing `count=count` at the call site. No changes are needed to `_build_host_view_response` — it already builds `"total": total` directly, which serialises to JSON `null` when `total is None`.
- File: `api/host_views.py`
- Change type: modify
- Rationale: The /beta/hosts-view endpoint has the same performance problem. Threading the `count` flag here ensures consistent behaviour across both host-listing endpoints.

### Step 6: Add two focused test functions (or a parametrised test) near the top of the file:

1. `test_get_host_list_total_is_null_without_count_param` — creates N hosts, calls GET /hosts without `?count=true`, asserts `response_data["total"] is None`.

2. `test_get_host_list_total_is_integer_with_count_param` — creates N hosts, calls GET /hosts with `?count=true`, asserts `response_data["total"] == N` (an integer).

Also update any existing tests that assert on the exact value of `response_data["total"]` from a plain GET /hosts call — those tests should either append `?count=true` to the URL or change the assertion to `response_data["total"] is None` to match the new default behaviour.
- File: `tests/test_api_hosts_get.py`
- Change type: modify
- Rationale: Tests must verify both the new null-by-default path and the opt-in count path. Existing tests that rely on total being an integer from a plain GET /hosts call will fail without updating them.

## Test Strategy
- Approach: Unit-style integration tests using the existing pytest + Flask test client setup (api_get fixture, db_create_host / mq_create_three_specific_hosts fixtures). Test the new `?count=true` boolean parameter on both GET /hosts and GET /beta/hosts-view. Verify the slow COUNT query is skipped (null total) and that opting in returns the correct integer total.
- Test files: tests/test_api_hosts_get.py, tests/test_api_host_views.py
- Coverage targets: GET /hosts without ?count returns total=null, GET /hosts with ?count=true returns total as a non-negative integer equal to the number of matching hosts, GET /beta/hosts-view without ?count returns total=null, GET /beta/hosts-view with ?count=true returns total as a non-negative integer, _get_host_list_using_filters with skip_count=True never calls func.count(...).scalar(), Existing tests that assert total is an integer are updated to pass ?count=true or assert total is None

## Risk Notes
- Breaking change for existing API consumers: the `total` field defaults to `null` instead of an integer. Consumers that assume `total` is always an integer (e.g., for pagination UI) will need to handle null or pass `?count=true`.
- Existing unit/integration tests that assert a numeric `total` from a plain GET /hosts call will fail — they must all be updated to pass `?count=true` or change the assertion to `total is None`.
- The early-exit optimisation (`if count_total == 0: return early`) is removed for the skip-count path. With 0 results the paginated query still executes, but its cost is negligible and this preserves correctness.
- `get_host_list_by_id_list` (used by GET /hosts/{host_id_list} → check_all_ids_found) intentionally keeps the count query so 404 detection for missing IDs continues to work.
- The cached system-identity path in api/host.py builds the response with `total=1` hardcoded; this code path is unaffected by the change.
- If connexion strict mode is enabled, the `count` param must match the spec exactly (boolean type). Verify the connexion version in use handles boolean query params correctly (it typically coerces 'true'/'false' strings).

## Constraints
- The `total` field in the PaginationOut schema is currently marked as required and non-nullable — making it nullable is a breaking API change for existing consumers (UI, integrations) that depend on `total` always being an integer.
- The staleness OR filter is the root cause of the seq-scan, and a parallel ticket (RHINENG-25499) aims to remove staleness timestamps. The count optimization here is partially blocked until that work lands.
- If using pg_class.reltuples for estimated counts, the estimate is per-table and not per-org, so it can't distinguish between orgs — it would only be suitable as a fallback when the org filter alone can be applied and not in combination with staleness/tag filters.
- A Redis-cached count approach requires infrastructure changes (Redis availability, cache invalidation) and adds eventual-consistency complexity.
- All three public functions using `_get_host_list_using_filters` (`get_host_list`, `get_host_list_by_id_list`, `get_host_list_for_views`) must be updated consistently to avoid inconsistent behaviour across endpoints.
- Pagination correctness (page boundaries) is not affected by skipping the count query — paginate() with `count=False` is already used for the results fetch. Only the `total` in the response would be null/estimated.
