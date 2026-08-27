# Spec: RHINENG-24460

## Summary
Every GET /hosts request executes SELECT count(DISTINCT hosts.id) with staleness OR filter conditions, forcing a sequential scan of all hosts in the org. This is causing significant performance degradation at scale (416ms for 466K-host orgs, 83ms for 23K-host orgs).

## Root Cause
In `api/host_query_db.py`, the `_get_host_list_using_filters` function (line 159) unconditionally runs `filtered_query.with_entities(func.count(Host.id.distinct())).scalar()` on every paginated host list request. The staleness filter (built in `api/filtering/db_filters.py` via `_staleness_filter()`) generates complex OR conditions combining multiple timestamp-based staleness states (e.g., `last_check_in <= X OR (last_check_in > X AND last_check_in < Y)`). PostgreSQL's B-tree indexes cannot efficiently serve these OR conditions across timestamp columns, forcing a full sequential scan of all hosts belonging to the org on every request. The fix approach chosen (per Jira discussion) involves making the count optional via a `?get_total=true` query parameter so consumers explicitly opt in, returning `total: null` by default to eliminate the expensive COUNT query from the hot path.

## Plan

- `swagger/pagination.yaml` (modify): Add `nullable: true` to the `Total` schema so that the `total` field in `PaginationOut` can legally be `null` in responses. The field stays in the `required` list (it must always be present), but its value may now be `null` when a count was not requested.

- `swagger/api.spec.yaml` (modify): Add a `get_total` boolean query parameter (default `false`, required `false`) to the GET `/hosts` operation's `parameters` list, following the same pattern as the other boolean params in that spec block. Connexion will automatically wire the value to the Python handler.

- `api/host_query_db.py` (modify): Add an `include_count: bool = True` keyword argument to `_get_host_list_using_filters`. When `False`, skip the `func.count(Host.id.distinct()).scalar()` call (and the `count_total == 0` early-exit that depends on it) and return `None` as the total element of the result tuple. Also add a `get_total: bool = False` parameter to `get_host_list` and pass it as `include_count` to `_get_host_list_using_filters`. All other callers (`get_host_list_by_id_list`, `get_host_list_for_views`) retain the default `include_count=True` so their behaviour is unchanged.

- `api/host.py` (modify): Add `get_total=False` to the `get_host_list()` API handler signature and forward it to `get_host_list_from_db`. No other handlers need changing because only GET `/hosts` exposes the new parameter.

- `tests/test_api_hosts_get.py` (modify): Add two focused test cases: (1) a test verifying that a plain GET `/hosts` request returns `total: null` in the response body (default opt-out behaviour); (2) a test verifying that GET `/hosts?get_total=true` returns an integer `total` matching the actual host count. Use existing fixtures such as `mq_create_three_specific_hosts` and `api_get` to keep the tests consistent with the existing suite style.
