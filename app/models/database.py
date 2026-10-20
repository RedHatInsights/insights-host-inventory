from flask import current_app
from flask import g
from flask import has_request_context
from flask import request
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy.session import Session as FlaskSession


class RoutingSession(FlaskSession):
    """Use the read replica only for read-only HTTP requests.

    Sessions created by workers do not have a Flask request context and
    therefore always use the primary database.  A request is deliberately
    routed as a whole rather than routing individual SQL statements so a
    transaction cannot move between databases.
    """

    def get_bind(self, mapper=None, clause=None, bind=None, **kwargs):
        if bind is not None:
            return bind

        replica = current_app.extensions.get("inventory_read_engine")
        if (
            replica is not None
            and has_request_context()
            and not g.get("inventory_use_primary", False)
            and request.method in {"GET", "HEAD"}
        ):
            return replica

        return super().get_bind(mapper=mapper, clause=clause, bind=bind, **kwargs)


db = SQLAlchemy(session_options={"class_": RoutingSession})
migrate = Migrate()


def use_primary_database() -> None:
    """Force the current request to use the primary database."""

    g.inventory_use_primary = True
