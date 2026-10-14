# Spec: RHINENG-15780

## Summary
Optimize staleness query filters by combining consecutive staleness states into simpler, single-range SQL conditions.

## Root Cause
When filtering hosts by multiple staleness states (e.g., fresh, stale, stale_warning), the system builds an OR-conjunction of individual state filters. Each individual filter uses timestamp comparisons against boundaries (e.g., stale_boundary, stale_warning_boundary, deletion_boundary). When consecutive states are requested, these individual filters overlap at their boundaries, resulting in redundant and complex SQL conditions (e.g., `now < stale_boundary OR (now >= stale_boundary AND now < stale_warning_boundary) OR ...`). These can be simplified into a single range check (e.g., `now < deletion_boundary` if all three non-culled states are requested).

## Plan

- `app/staleness_states.py` (modify): Add a `combined_filter(states)` method to `HostStalenessStatesDbFilters` that accepts a list of state names and returns an optimized SQLAlchemy filter expression. The method should identify consecutive runs of states in the canonical order (fresh → stale → stale_warning → culled) and merge each run into a single range condition using only the outer boundaries. For example, a run of [fresh, stale] becomes a single `now < stale_warning_boundary`, a run of [stale, stale_warning] becomes `now >= stale_boundary AND now < deletion_boundary`, and [fresh, stale, stale_warning] becomes `now < deletion_boundary`. Non-consecutive states are kept as separate conditions and OR'd together.

- `api/filtering/db_filters.py` (modify): Update `_staleness_filter` to call the new `combined_filter` method on `HostStalenessStatesDbFilters` instead of iterating over individual states with `getattr` and OR'ing them. The `["unknown"]` special case should remain unchanged.

- `tests/test_custom_staleness.py` (modify): Add tests for the optimized combined staleness filter. Tests should cover: (1) consecutive pair [fresh, stale] matches a host in the fresh window and a host in the stale window but not stale_warning or culled; (2) consecutive pair [stale, stale_warning] matches hosts in those windows but not fresh or culled; (3) all three non-culled states [fresh, stale, stale_warning] matches any non-culled host; (4) non-consecutive states like [fresh, stale_warning] correctly match fresh and stale_warning hosts but not stale or culled hosts; (5) all four states [fresh, stale, stale_warning, culled] match any host. Use the existing `db_create_host` fixture and set `last_check_in` to place hosts into specific staleness windows, following the pattern of existing tests like `test_staleness_db_filter_fresh_uses_org_defaults_when_columns_null`.

## Constraints
- The optimization must preserve exact logical semantics — no host should be included or excluded differently than before
- The per_reporter_staleness_filter / staleness_to_conditions path is out of scope for this change
