from flask import current_app
from flask import g
from flask import has_request_context
from flask import request
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy.session import Session as FlaskSession
from sqlalchemy.exc import SQLAlchemyError


class RoutingSession(FlaskSession):
    """Use the read replica only for read-only HTTP requests.

    Sessions created by workers do not have a Flask request context and
    therefore always use the primary database.  A request is deliberately
    routed as a whole rather than routing individual SQL statements so a
    transaction cannot move between databases.
    """

    def _should_use_replica(self) -> bool:
        return (
            current_app.extensions.get("inventory_read_engine") is not None
            and has_request_context()
            and not g.get("inventory_use_primary", False)
            and request.method in {"GET", "HEAD"}
        )

    def get_bind(self, mapper=None, clause=None, bind=None, **kwargs):
        if bind is not None:
            return bind

        if self._should_use_replica():
            return current_app.extensions["inventory_read_engine"]

        return super().get_bind(mapper=mapper, clause=clause, bind=bind, **kwargs)

    def execute(self, *args, **kwargs):
        try:
            return super().execute(*args, **kwargs)
        except SQLAlchemyError:
            if not self._should_use_replica():
                raise

            # A failed replica connection or query must not take down a read
            # request while the primary is healthy.  Roll back any failed
            # transaction, pin this request to primary, and retry once.
            try:
                self.rollback()
            except SQLAlchemyError:
                self.close()
            g.inventory_use_primary = True
            return super().execute(*args, **kwargs)


db = SQLAlchemy(session_options={"class_": RoutingSession})
migrate = Migrate()


def use_primary_database() -> None:
    """Force the current request to use the primary database."""

    g.inventory_use_primary = True
