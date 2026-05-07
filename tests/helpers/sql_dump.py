import inspect
import json
import sys
from functools import wraps

from sqlalchemy import event as sqlevent

try:
    # sqlparse if optional, but the output is much easier to read when it's installed.
    from sqlparse import format as sql_formatter
except ModuleNotFoundError:

    def sql_formatter(sql_str, reindent=True, keyword_case="upper"):  # noqa: ARG001
        return sql_str


from app.models import db

"""
Usage:
    from tests.helpers.sql_dump import SQLDump
    :
    :
    # In the test case "with" statement
        with SQLDump():
            assert_host_exists_in_db(created_host.id, subset_canonical_facts)

    ------

    from tests.helpers.sql_dump import dumps_sql
    :
    :
    # Or decorator for whole method (including generators and async functions)
    @dumps_sql
    def test_find_host_using_superset_canonical_fact_match(db_create_host):
"""


class SQLDump:
    def __init__(self, dump_method=None, write_method=print):
        self.dump_method = self.dump_sql if dump_method is None else dump_method
        self.write_method = write_method

    def __enter__(self):
        sqlevent.listen(db.engine, "before_execute", self.dump_method)

    def __exit__(self, exc_type, exc_value, exc_traceback):  # noqa: ARG002
        sqlevent.remove(db.engine, "before_execute", self.dump_method)

    def dump_sql(self, conn, clauseelement, multiparams, params, execution_options):  # noqa: ARG002
        self.write_method("**** QUERY:\n")
        self.write_method(sql_formatter(str(clauseelement.compile()), reindent=True, keyword_case="upper"))
        self.write_method("\n**** PARAMETERS:\n")
        self.write_method(json.dumps(clauseelement.compile().params, sort_keys=True, indent=4, default=str))
        self.write_method("\n****************\n")


def _sqldump_enter(dump_method, write_method):
    sqld = SQLDump(dump_method=dump_method, write_method=write_method)
    sqld.__enter__()
    return sqld


def _sqldump_exit(sqld):
    sqld.__exit__(*sys.exc_info())


def dumps_sql(_func=None, *, dump_method=None, write_method=print):
    def decorator_dumps_sql(old_func):
        if inspect.isgeneratorfunction(old_func):

            @wraps(old_func)
            def gen_wrapper(*args, **kwargs):
                sqld = _sqldump_enter(dump_method, write_method)
                try:
                    yield from old_func(*args, **kwargs)
                finally:
                    _sqldump_exit(sqld)

            return gen_wrapper

        if inspect.isasyncgenfunction(old_func):

            @wraps(old_func)
            async def asyncgen_wrapper(*args, **kwargs):
                sqld = _sqldump_enter(dump_method, write_method)
                try:
                    async for item in old_func(*args, **kwargs):
                        yield item
                finally:
                    _sqldump_exit(sqld)

            return asyncgen_wrapper

        if inspect.iscoroutinefunction(old_func):

            @wraps(old_func)
            async def async_wrapper(*args, **kwargs):
                sqld = _sqldump_enter(dump_method, write_method)
                try:
                    return await old_func(*args, **kwargs)
                finally:
                    _sqldump_exit(sqld)

            return async_wrapper

        @wraps(old_func)
        def new_func(*args, **kwargs):
            sqld = _sqldump_enter(dump_method, write_method)
            try:
                return old_func(*args, **kwargs)
            finally:
                _sqldump_exit(sqld)

        return new_func

    if _func is None:
        return decorator_dumps_sql
    else:
        return decorator_dumps_sql(_func)


# Alias for the name used in RHINENG-15779 and similar reports
sqldumps = dumps_sql
