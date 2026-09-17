# Spec: RHINENG-17554

## Summary
Filtering hosts by tags fails with HTTP 400 when the tag value contains a '/' character

## Root Cause
In `app/utils.py` line 289, the `Tag.from_string` static method uses a regex pattern where the value capture group is `(?P<value>[^=/]+)`, which explicitly excludes the '/' character from tag values. When a tag like `namespace/key=my/value` is passed, the regex fails to match (returns `None`), and subsequently calling `.groupdict()` on `None` raises an `AttributeError` that gets translated into an HTTP 400 error. The '/' character should be allowed in tag values since the value is the last component of the tag string (after `=`, anchored by `$`), and there is no parsing ambiguity in allowing it.

## Plan

- `app/utils.py` (modify): In the `Tag.from_string` regex on line 289, change the value capture group from `[^=/]+` to `[^=]+` so that '/' characters are permitted in tag values.

- `tests/test_unit.py` (modify): Add a new test function (e.g. `test_slash_in_value_tag_from_string`) near the existing `test_all_parts_tag_from_string` test, asserting that `Tag.from_string('NS/key=my/value')` equals `Tag('NS', 'key', 'my/value')`.

## Constraints
- The '/' character must remain excluded from the namespace capture group (`[^=/]+`) since it delimits namespace from key
- Existing tag parsing behavior (encoded delimiters, special characters, length validation) must not be affected
