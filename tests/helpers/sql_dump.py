import json

from sqlalchemy import event as sqlevent

try:
    from sqlparse import format as sql_formatter
except ModuleNotFoundError:

    def sql_formatter(sql_str, reindent=True, keyword_case="upper"):
        return sql_str


from app import db


class SQLDump:
    def __init__(self, dump_method=None, write_method=print):
        if dump_method is None:
            self.dump_method = self.dump_sql
        self.write_method = write_method

    def __enter__(self):
        sqlevent.listen(db.engine, "before_execute", self.dump_method)

    def __exit__(self, exc_type, exc_value, exc_traceback):
        sqlevent.remove(db.engine, "before_execute", self.dump_method)

    def dump_sql(self, conn, clauseelement, multiparams, params, execution_options):
        self.write_method("**** QUERY:\n")
        self.write_method(sql_formatter(str(clauseelement.compile()), reindent=True, keyword_case="upper"))
        self.write_method("\n**** PARAMETERS:\n")
        self.write_method(json.dumps(clauseelement.compile().params, sort_keys=True, indent=4, default=str))
        self.write_method("\n****************\n")
