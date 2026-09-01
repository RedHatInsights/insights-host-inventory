# Spec: RHINENG-15874

## Summary
Make SQLDump log the SQL query and parameters in a single message instead of calling the write method 5 times.

## Root Cause
Currently, `SQLDump.dump_sql` calls `self.write_method` 5 separate times to output different parts of the query dump (the header, the formatted SQL query, the parameters header, the JSON-formatted parameters, and the footer). When `write_method` is a logger method (e.g., `logger.info`), this results in 5 separate log entries, which makes the output hard to read and pollutes the log stream.

## Plan

- `tests/helpers/sql_dump.py` (modify): In `dump_sql`, compile the clause element once, build the formatted SQL and JSON parameters into a single string (preserving the same header/footer formatting), and call `self.write_method` exactly once with that combined string.

- `tests/test_sql_dump.py` (modify): Add a test that creates a `SQLDump` with a mock `write_method`, invokes `dump_sql` with a mock `clauseelement` (whose `compile()` returns an object with a string representation and a `params` dict), and asserts that `write_method` is called exactly once and the single message contains all expected sections (QUERY header, formatted SQL, PARAMETERS header, JSON params, and footer).

## Constraints
- The compiled clause element should only be created once per dump_sql invocation (avoid the current double-compile).
- The textual content of the output must remain the same so existing users see no formatting difference.
