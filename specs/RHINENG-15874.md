# Spec: RHINENG-15874

## Summary
Make SQLDump log the SQL query and parameters in a single message instead of calling the write method 5 times.

## Root Cause
The `SQLDump.dump_sql` method currently calls `self.write_method` five times to output different parts of the SQL dump (the query header, the formatted query, the parameters header, the JSON-serialized parameters, and the footer). When a logger method (like `logger.info`) is used as `write_method`, this results in five separate log entries, which clutters the logs and makes them hard to read.

## Plan

- `tests/helpers/sql_dump.py` (modify): In `dump_sql`, build the entire output (query header, formatted SQL, parameters header, JSON parameters, footer) into a single string and call `self.write_method` exactly once with that combined string.

- `tests/test_sql_dump.py` (modify): Add a test that creates a `SQLDump` with a `MagicMock` as `write_method`, invokes `dump_sql` with a mocked `clauseelement` (whose `compile()` returns an object with a string representation and a `.params` dict), and asserts that `write_method` is called exactly once. Also verify the single message contains the expected substrings: the query header, the formatted SQL text, the parameters header, the JSON-serialized parameters, and the footer.

## Constraints
- The combined message must preserve the same logical structure as the original five-call output (query header, formatted query, parameters header, JSON parameters, footer).
- sql_formatter and json.dumps must still be used to format the query and parameters respectively.
