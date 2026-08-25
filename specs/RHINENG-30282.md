# Spec: RHINENG-30282

## Summary
Deprecate and remove the `immutable_time_to_*` staleness fields from the HBI (Host Based Inventory) API — including the OpenAPI spec, request handling, serialization, and tests.

## Root Cause
The `immutable_time_to_stale`, `immutable_time_to_stale_warning`, and `immutable_time_to_delete` staleness fields are legacy fields that are no longer stored in the database (they were already dropped from the `Staleness` model and `StalenessSchema`). However, they still exist in: (1) the OpenAPI spec (`StalenessIn` and `StalenessOutput` schemas), (2) API response serializers (`serialize_staleness_response` and `build_staleness_sys_default`/`build_serialized_acc_staleness_obj`), and (3) the `_validate_input_data` function in `api/staleness.py`, which silently filters them out with a TODO comment noting they should be removed once 'fully deprecated and removed from the API spec'. This partial state means the API still accepts and returns these fields despite having no backend storage or meaning.

## Plan

- `swagger/openapi.json` (modify): Remove the three `immutable_time_to_stale`, `immutable_time_to_stale_warning`, and `immutable_time_to_delete` entries from the `StalenessIn` properties block, and remove the same three field names from the `required` array inside the `StalenessOutput` allOf block.

- `api/staleness.py` (modify): Delete the `immutable_fields` set, the `filtered_body` comprehension, and the associated TODO comment from `_validate_input_data`, replacing `filtered_body` with the original `body` in the `StalenessSchema().load()` call. After this change, marshmallow's default `RAISE` behavior for unknown fields will naturally reject any request that still sends the removed fields.

- `app/serialization.py` (modify): Remove the three `immutable_time_to_*` key-value pairs from the dict returned by `serialize_staleness_response`.

- `app/staleness_serialization.py` (modify): Remove the three `immutable_time_to_*` entries from the `AttrDict` returned by both `build_staleness_sys_default` and `build_serialized_acc_staleness_obj`.

- `tests/test_api_staleness_create.py` (modify): Delete the `test_create_staleness_ignores_immutable_fields` parametrized test entirely. This test asserted that sending immutable fields with invalid values still returned 201; after removing the silent filter, marshmallow will return 400 for unknown fields, making the old assertion wrong and the old test purpose obsolete.

- `tests/test_staleness_cache.py` (modify): Remove the three `immutable_time_to_*` keys from the `SAMPLE_STALENESS` AttrDict fixture at the top of the file.

- `iqe-host-inventory-plugin/iqe_host_inventory/modeling/staleness_api.py` (modify): Remove the three `immutable_time_to_*` parameters from `_build_staleness_body`, `create_staleness`, and `update_staleness`. Update each call-site that passes the removed parameters positionally or by keyword to drop them.

## Constraints
- The four auto-generated IQE API model files (`iqe-host-inventory-plugin/iqe_host_inventory_api/models/staleness_in.py`, `staleness_output.py`, `iqe_host_inventory_api_v7/models/staleness_in.py`, `staleness_output.py`) also reference `immutable_time_to_*` fields and should be regenerated from the updated OpenAPI spec; they are out of scope for this PR if managed via a separate submodule commit.
- After step 2, any API client that sends `immutable_time_to_*` fields in a POST/PATCH body will receive a 400. This is a breaking change for callers that have not already stopped sending these fields.
