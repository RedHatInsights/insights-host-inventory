# Spec: RHINENG-31804

## Summary
Create metric for failed "Ungrouped Hosts" workspace/group creation

## Root Cause
When creation of the "Ungrouped Hosts" workspace/group fails in the kessel-enabled flow of `lib.group_repository.get_or_create_ungrouped_hosts_group_for_identity`, it raises an exception (e.g., TimeoutError, HTTPError, or ValueError if the group is not found in the DB) which is treated as a standard processing error. There is currently no specific Prometheus metric to track these failures, making it difficult to monitor and alert on them with high criticality.

## Plan

- `lib/metrics.py` (modify): Add a new Prometheus Counter named `ungrouped_hosts_group_creation_failure` with the metric name `inventory_ungrouped_hosts_group_creation_failure_count` and a description indicating it tracks failed 'Ungrouped Hosts' workspace/group creations. Place it in the Inventory Groups section alongside the existing group metrics.

- `lib/group_repository.py` (modify): Import `ungrouped_hosts_group_creation_failure` from `lib.metrics`. In `get_or_create_ungrouped_hosts_group_for_identity`, wrap the `else` block (the kessel-enabled flow: `rbac_create_ungrouped_hosts_workspace`, `wait_for_workspace_event`, and `get_group_by_id_from_db`) in a `try/except Exception` block. After the call to `get_group_by_id_from_db`, if the result is `None`, raise a `ValueError` indicating the group was not found in the DB. In the `except` block, increment the new metric and re-raise the exception.

- `tests/test_models.py` (modify): Add three new test functions after the existing `test_ungrouped_group_cache_deduplicates_group_creation_rbac_v2` test. Each test should mock `bypass_kessel` as False, `get_ungrouped_group` returning None, and use the `UngroupedGroupCache` context. (1) Test that when `rbac_create_ungrouped_hosts_workspace` raises an exception, the metric is incremented and the exception propagates. (2) Test that when `wait_for_workspace_event` raises a `TimeoutError`, the metric is incremented and the exception propagates. (3) Test that when `get_group_by_id_from_db` returns `None`, the metric is incremented and a `ValueError` is raised. Pattern after the existing kessel flow tests at lines ~2377-2436.

## Constraints
- The exception must always be re-raised after incrementing the metric to preserve existing error handling
- The metric should only cover the kessel-enabled (else) flow, not the bypass_kessel (if) flow
