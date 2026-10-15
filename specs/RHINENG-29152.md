# Spec: RHINENG-29152

## Summary
Tag filtering in Inventory incorrectly uses OR logic across all tags regardless of namespace and name. Per ADR-0007, tags with the same namespace+name (same identity) should be OR'd, but tags with different identities (different namespace or different name) should be AND'd.

## Root Cause
The `_tags_filter` function in `api/filtering/db_filters.py` (lines 156-162) creates a separate nested tag for each input string tag and then combines ALL of them with a single `or_()` expression. This means every tag filter is OR'd together regardless of whether tags share the same namespace and name or not. According to ADR-0007, tags should be grouped by their 'identity' (namespace + name pair): multiple values for the same identity should be OR'd (union), while different identities should be AND'd (conjunction). The current code: `return [or_(Host.tags.contains(tag) for tag in tags)]` unconditionally ORs everything.

## Plan

- `api/filtering/db_filters.py` (modify): Rewrite the `_tags_filter` function (lines 156-162) to group tags by identity (namespace, key) and apply correct boolean logic. Parse each string tag via `Tag.from_string()`, group the resulting Tag objects by `(tag.namespace, tag.key)` using a `defaultdict(list)`, then for each identity group create an `or_()` of `Host.tags.contains(Tag.create_nested_from_tags([tag]))` conditions for each tag in the group. Return the list of per-group conditions so they are AND'd together by the caller at line 575. Add `from collections import defaultdict` to imports.

- `tests/test_api_hosts_get.py` (modify): Update `test_get_host_by_multiple_tags` (line 608): change `expected_total` from 3 to 1 and update the assertion to check that only host_ids[1] (the host with both ns1/key1=val1 and ns1/key2=val2) is returned. Update its docstring to reflect AND semantics. Update `test_get_host_by_subset_of_tags` (line 630): change `expected_total` from 3 to 1 and update assertions to check that only host 1 (which has both NS1/key1=val1 and NS3/key3=val3) is returned. Add a new test `test_get_host_by_same_identity_tags_uses_or` that creates hosts with the same namespace+key but different values and queries with multiple values for that identity, verifying OR logic returns hosts matching any of the values. Add a new test `test_get_host_by_different_identity_tags_uses_and` that explicitly verifies AND across different identities, distinct from the updated existing tests.

## Constraints
- This is a breaking semantic change to the tag filtering API — downstream consumers relying on the old OR-across-all-tags behavior will be affected
- Empty/null namespace must be treated as distinct from named namespaces when grouping by identity
- The existing Host.tags JSONB @> (contains) query mechanism must be preserved
