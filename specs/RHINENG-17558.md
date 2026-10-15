# Spec: RHINENG-17558

## Summary
Filtering hosts by tags fails when namespace is empty and the key contains a '/' character. A request like GET /hosts?tags=/my/key=myvalue returns 0 results instead of the expected host.

## Root Cause
The regex in Tag.from_string() (app/utils.py line 289) does not handle the case where the tag string starts with '/' (indicating an empty/null namespace separator). The regex pattern is: ^((?P<namespace>[^=/]+)/)?(?P<key>(?!.*/=)[^=]+)(=(?P<value>[^=/]+))?$. When parsing '/my/key=myvalue', the namespace group fails at position 0 because '/' is excluded from [^=/]+, and since the group is optional, it's skipped. The key group [^=]+ then matches '/my/key' (including the leading '/'), resulting in key='/my/key' instead of key='my/key'. In the database, the tag is stored with key='my/key' (without leading slash), so the JSONB contains query in _tags_filter() fails to find a match, returning 0 results.

## Plan

- `app/utils.py` (modify): In Tag.from_string(), change the namespace capture group in the regex from [^=/]+ to [^=/]* so that an empty namespace is matched when the tag string starts with '/'. After the URL-decoding loop, normalize the decoded namespace by passing it through Tag.serialize_namespace() to convert empty string to None (consistent with NULL_NAMESPACES handling).

- `tests/test_unit.py` (modify): Add test cases for Tag.from_string() covering tags with empty namespace and '/' in the key. Add a test asserting Tag.from_string('/my/key=myvalue') equals Tag(None, 'my/key', 'myvalue'), a test for '/key=value' yielding Tag(None, 'key', 'value'), and a test for '/key' yielding Tag(None, 'key', None). Place these alongside the existing tag from_string tests near line 735.

## Constraints
- The regex change must not alter behavior for existing tag formats: 'NS/key=value', 'key=value', 'NS/key', 'key', and URL-encoded special characters
- Empty string namespace must be normalized to None via the existing NULL_NAMESPACES/serialize_namespace logic
