# Spec: RHINENG-29152

## Summary
Tag filtering in Inventory incorrectly uses OR logic across all tags. Per ADR-0007, tags with the same namespace+name (same identity) should be OR'd, but tags with different identities (different namespace or different name) should be AND'd.

## Root Cause
The `_tags_filter` function in `api/filtering/db_filters.py` (line 156-162) creates individual nested tag representations for each tag string and then combines ALL of them with a single `or_()` clause. This means all tag filters are OR'd together regardless of their namespace/name identity. The function should instead group tags by their identity (namespace, key), OR values within the same identity group using `Host.tags.contains()`, and then AND the resulting groups together.

## Plan

- `api/filtering/db_filters.py` (modify): Rewrite the `_tags_filter` function (lines 156-162) to group parsed tags by their identity tuple (namespace, key). For each identity group, OR together the `Host.tags.contains()` checks for each tag value. Then AND all identity-group filters together. Use `collections.defaultdict` to collect tags by identity, `Tag.from_string` to parse, and `Tag.create_nested_from_tags` to build the nested representation for each individual tag.

- `tests/test_api_hosts_get.py` (modify): Update `test_get_host_by_multiple_tags` (line 608): change expected_total from 3 to 1 and assert only `host_ids[1]` matches (the only host with both ns1/key1=val1 AND ns1/key2=val2). Update `test_get_host_by_subset_of_tags` (line 630): change expected_total from 3 to 1 and assert only `created_hosts[1]` matches (the only host with both NS1/key1=val1 AND NS3/key3=val3). Add a new test `test_get_host_by_tags_same_identity_uses_or` that creates hosts with different values for the same namespace+key, queries with both values, and asserts both hosts are returned (verifying OR-within-same-identity logic).

- `tests/test_api_hosts_delete_bulk.py` (modify): Update `test_delete_bulk_by_tags_multiple` (line 413): change expected matches from 4 to 2, update match_ids to contain only the two hosts that have both tags (both_tags and both_tags+extra), and move the tag1-only and tag2-only hosts into nomatch_ids. Update the comment from 'OR logic' to 'AND logic across different identities'. Adjust assertions accordingly.

## Constraints
- Single-tag queries must remain unaffected by this change
- Tags with the same namespace and key (same identity) must still use OR logic for different values
- None/null namespace must be treated as a distinct identity from named namespaces
- Performance must not degrade — continue using JSONB containment checks (Host.tags.contains)
