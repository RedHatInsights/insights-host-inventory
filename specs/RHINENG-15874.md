# Spec: RHINENG-15874

## Summary
Make SQLDump log the SQL query and parameters in a single message instead of calling the write method 5 times.

## Root Cause
The `SQLDump.dump_sql` method calls `self.write_method` 5 times to output the query header, query body, parameters header, parameters body, and footer. When `write_method` is a logger method (e.g., `logger.info`), this results in 5 separate log entries, making the output hard to read and cluttering the logs. Combining these into a single string and calling `self.write_method` once will produce a single, cohesive log entry.

## Plan

- `tests/helpers/sql_dump.py` (modify): In the `dump_sql` method, build a single formatted string containing the query header, formatted SQL, parameters header, JSON parameters, and footer — then call `self.write_method` exactly once with that combined string.

- `tests/test_sql_dump.py` (modify): Add a test that creates a `SQLDump` with a mock `write_method`, invokes `dump_sql` with a mock `clauseelement` (whose `.compile()` returns a mock with a `.params` dict and whose `str()` returns a SQL string), and asserts that `write_method` is called exactly once and the single argument contains the query, parameters, and delimiters.

## Constraints
- The combined string content must match the original multi-call output so existing consumers see the same formatting.
- write_method must remain compatible with both `print` and logger methods (single string argument).
