# Spec: RHINENG-31261

## Summary
Disallow forward-slash (/) character in the tag filter's namespace and value regex patterns, reversing the previous change that allowed '/' in tag values.

## Root Cause
The tag parsing regex in `Tag.from_string()` (app/utils.py line 288) currently uses `[^=]+` for the value capture group, which allows the '/' character in tag values. This was intentionally changed from `[^=/]+` to `[^=]+` by RHINENG-17554. The same permissive pattern exists in the OpenAPI YAML source (swagger/api.spec.yaml line 1477) and in the generated JSON specs that the application actually serves: `swagger/openapi.json` (line 2391) and `swagger/openapi_v2.json` (line 169). The namespace group already disallows '/' via `[^=/]*`, so no change is needed there. The requirement now is to re-restrict '/' in the value group across all spec files, effectively reverting the RHINENG-17554 change for the value portion.

## Plan

- `app/utils.py` (modify): In the `Tag.from_string` regex on line 288, change the value capture group from `[^=]+` to `[^=/]+` to disallow the forward-slash character in tag values.

- `swagger/api.spec.yaml` (modify): In the `tagsParam` pattern on line 1478, change the value portion from `[^=]+` to `[^=/]+` to match the updated Python regex.

- `swagger/openapi.json` (modify): Regenerate from `swagger/api.spec.yaml`, or manually update the `tagsParam` pattern (line 2391) to change the value portion from `[^=]+` to `[^=/]+`. This file is the specification actually loaded and served by the application (`app/__init__.py` line 58), so it must stay in sync with the YAML source.

- `swagger/openapi_v2.json` (modify): Update the `tagsParam` pattern (line 169) to change the value portion from `[^=]+` to `[^=/]+`, keeping it consistent with the v1 spec and YAML source.

- `tests/test_unit.py` (modify): Replace the `test_slash_in_value_tag_from_string` parametrized test (lines 725–737) so that each of its current inputs (which contain '/' in the value) is instead asserted to raise an error (AttributeError from the None match). Keep the test parametrized for clarity. Existing tests for empty/null namespace, URL-encoded slashes, and key-containing slashes must remain unchanged.

## Constraints
- The '/' character must remain allowed in the key capture group — only the value group is restricted
- URL-encoded '/' (%2F) in values is decoded after regex matching and must continue to work (see test_delimiters_tag_from_string)
- The namespace capture group already excludes '/' — no change needed there

## Related Specs

- `specs/RHINENG-17554.md` (**contradicts**): RHINENG-17554 explicitly changed the value regex from `[^=/]+` to `[^=]+` to ALLOW '/' in tag values. RHINENG-31261 now requires the opposite — disallowing '/' in tag values. The RHINENG-17554 spec and its associated test (`test_slash_in_value_tag_from_string`) are invalidated by this new requirement.

- `specs/RHINENG-17558.md` (**related**): RHINENG-17558 modified the namespace regex to allow empty namespace (changing `[^=/]+` to `[^=/]*`). While that change is unaffected by this ticket (namespace already disallows '/'), some of its test cases (e.g., `/key=my/value`) combine empty namespace with '/' in values and may need updating if they exist in the test suite.
