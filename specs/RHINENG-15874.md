# Spec: RHINENG-15874

## Summary
Make SQLDump log the SQL query and parameters in a single message instead of calling the write method 5 times.

## Root Cause
The `SQLDump.dump_sql` method currently makes 5 separate calls to `self.write_method` to output different parts of the SQL dump (the query header, the formatted query, the parameters header, the JSON-serialized parameters, and the footer). When a logger method (like `logger.info`) is passed as the `write_method`, this results in 5 separate log entries, making the output fragmented and hard to read.

## Plan

- `tests/helpers/sql_dump.py` (modify): In `dump_sql`, call `clauseelement.compile()` once and store the result. Build a single formatted string from all five parts (query header, formatted SQL, parameters header, JSON parameters, footer) and call `self.write_method` exactly once with that combined string.

- `tests/test_sql_dump.py` (modify): Add a test that creates a `SQLDump` with a mock `write_method`, calls `dump_sql` with a mock `clauseelement` (whose `compile()` returns an object with a string representation and a `.params` dict), and asserts that `write_method` is called exactly once. Also assert the single string argument contains the query header, the formatted SQL, the parameters header, the JSON parameters, and the footer. Verify `compile()` is called only once on the clause element.

## Constraints
- The default write_method (print) must continue to work without changes to the public API.
- The output content must remain the same — only the number of write calls changes.
