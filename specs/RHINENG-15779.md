# Spec: RHINENG-15779

## Summary
The `dumps_sql` decorator in `tests/helpers/sql_dump.py` fails to log SQL queries when applied to generator functions (functions that use `yield`), such as `get_hosts_to_export`.

## Root Cause
The decorator's `new_func` wrapper calls `results = old_func(*args, **kwargs)` and then immediately calls `sqld.__exit__(None, None, None)` to remove the SQLAlchemy event listener. When the decorated function is a generator (uses `yield`), calling it returns a generator object **without executing any of its body**. The event listener is therefore removed before any SQL queries are actually executed. When the generator is later iterated by the caller, all SQL queries fire without any active listener, producing no logs. Additionally, there are two secondary bugs: (1) `SQLDump.__init__` is missing an `else` branch — when a custom `dump_method` is provided, `self.dump_method` is never set, causing an `AttributeError` on `__enter__`; (2) the `new_func` wrapper has no `try/finally`, so if the decorated function raises an exception, `__exit__` is never called and the listener remains registered indefinitely.

## Plan

- `tests/helpers/sql_dump.py` (modify): Add `import inspect` at the top of the file. Fix `SQLDump.__init__` by adding the missing `else: self.dump_method = dump_method` branch so custom dump methods are actually stored. In `decorator_dumps_sql`, replace the bare `new_func` wrapper with two branches: when `inspect.isgeneratorfunction(old_func)` is true, define a generator wrapper that calls `sqld.__enter__()` then `yield from old_func(...)` inside a `try/finally` that calls `sqld.__exit__(None, None, None)`; for all other functions, wrap `old_func(...)` in a `try/finally` with the same enter/exit pattern. Return the appropriate wrapper.

- `tests/test_sql_dump.py` (create): Create a unit test file that mocks `sqlevent.listen` and `sqlevent.remove` (patching `tests.helpers.sql_dump.sqlevent`) to avoid needing a live database. Include three test cases: (1) assert that instantiating `SQLDump` with a custom `dump_method` stores it as `self.dump_method` without raising; (2) assert that decorating a regular function that raises still calls `sqlevent.remove` (listener cleanup on exception); (3) assert that decorating a generator function keeps `sqlevent.listen` active across all `yield` iterations and only calls `sqlevent.remove` after the generator is exhausted.

## Constraints
- The generator wrapper must use `yield from` (not collect results) so callers receive a true generator iterator, preserving lazy evaluation semantics.
- The `__exit__` call in `finally` must always pass `(None, None, None)` to match the existing intentional silent-exception-suppression behaviour documented with `noqa: ARG002`.
