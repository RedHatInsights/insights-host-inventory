from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from functools import cache
from uuid import uuid4

from sqlalchemy import and_
from sqlalchemy import delete
from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import insert

from app.audit import AuditContext
from app.audit import AuditEvent
from app.audit import audit_operation
from app.audit import capture_audit_context
from app.exceptions import InventoryException
from app.logging import get_logger
from app.models import InventoryView
from app.models import UserViewPreference
from app.models import db
from app.models.utils import _time_now
from app.models.views import MAX_VIEW_NAME_LENGTH
from lib.db import session_guard
from lib.metrics import system_default_view_missing

logger = get_logger(__name__)

__all__ = (
    "get_views_list",
    "get_view_by_id",
    "create_view",
    "update_view",
    "delete_view",
    "clone_view",
    "get_default_view_id",
    "set_default_view",
    "delete_default_view",
)

CLONE_NAME_PREFIX = "Copy of "
ALL_SYSTEMS_VIEW_NAME = "All systems"


@cache
def _get_system_default_view_id() -> str:
    """Return the UUID of the seeded 'All systems' system view (cached after first lookup)."""
    view_id = (
        db.session.query(InventoryView.id)
        .filter(
            InventoryView.org_id.is_(None),
            InventoryView.name == ALL_SYSTEMS_VIEW_NAME,
        )
        .scalar()
    )
    if view_id is None:
        system_default_view_missing.inc()
        logger.error("System default view '%s' not found – returning HTTP 500", ALL_SYSTEMS_VIEW_NAME)
        raise InventoryException(
            status=500,
            title="Internal Server Error",
            detail=f"System default view '{ALL_SYSTEMS_VIEW_NAME}' not found.",
        )
    return str(view_id)


class ViewNotFoundError(InventoryException):
    def __init__(self, detail: str = "View not found."):
        super().__init__(status=404, title="Not Found", detail=detail)


class ViewPermissionError(InventoryException):
    def __init__(self, detail: str):
        super().__init__(status=403, title="Forbidden", detail=detail)


def _visibility_filter(org_id: str, user_id: str):
    """Return a SQLAlchemy filter for views visible to the given user.

    Visible views are:
    - System views (org_id IS NULL)
    - Org-wide views in the same org
    - Private views created by the user in the same org
    """
    return or_(
        InventoryView.org_id.is_(None),
        and_(
            InventoryView.org_id == org_id,
            or_(
                InventoryView.created_by == user_id,
                InventoryView.org_wide.is_(True),
            ),
        ),
    )


def _get_visible_view(view_id: str, org_id: str, user_id: str) -> InventoryView:
    view = InventoryView.query.filter(
        InventoryView.id == view_id,
        _visibility_filter(org_id, user_id),
    ).one_or_none()

    if view is None:
        raise ViewNotFoundError()

    return view


def get_views_list(org_id: str, user_id: str, page: int = 1, per_page: int = 50) -> tuple[list[InventoryView], int]:
    query = InventoryView.query.filter(_visibility_filter(org_id, user_id)).order_by(
        InventoryView.is_system_view.desc(),
        InventoryView.modified_on.desc(),
    )

    total = query.count()
    views = query.offset((page - 1) * per_page).limit(per_page).all()

    return views, total


def get_view_by_id(view_id: str, org_id: str, user_id: str) -> InventoryView:
    return _get_visible_view(view_id, org_id, user_id)


def _view_audit_context(org_id: str, user_id: str, context: AuditContext | None) -> AuditContext:
    # API callers pass the complete validated identity; legacy internal callers know only these IDs.
    return context or replace(capture_audit_context(), org_id=org_id, principal=user_id)


def create_view(data: dict, org_id: str, user_id: str, *, audit_context: AuditContext | None = None) -> InventoryView:
    view = InventoryView(
        id=uuid4(),
        org_id=org_id,
        name=data["name"],
        description=data.get("description"),
        configuration=data["configuration"],
        org_wide=data.get("org_wide", False),
        created_by=user_id,
    )

    events = [AuditEvent("CREATE", "saved_view", str(view.id), _view_audit_context(org_id, user_id, audit_context))]
    with audit_operation(events), session_guard(db.session, close=False):
        db.session.add(view)

    db.session.refresh(view)
    logger.info("Created view %s for org %s by %s", view.id, org_id, user_id)
    return view


def update_view(
    view_id: str, data: dict, org_id: str, user_id: str, *, audit_context: AuditContext | None = None
) -> InventoryView:
    view = _get_visible_view(view_id, org_id, user_id)

    if view.is_system_view:
        raise ViewPermissionError("System views cannot be modified.")

    if view.created_by != user_id:
        raise ViewPermissionError("Only the view creator can update this view.")

    events = [AuditEvent("UPDATE", "saved_view", view_id, _view_audit_context(org_id, user_id, audit_context))]
    with audit_operation(events), session_guard(db.session, close=False):
        view.patch(data)
        if not db.session.is_modified(view):
            events.clear()

    db.session.refresh(view)
    logger.info("Updated view %s by %s", view_id, user_id)
    return view


def delete_view(view_id: str, org_id: str, user_id: str, *, audit_context: AuditContext | None = None) -> None:
    view = _get_visible_view(view_id, org_id, user_id)

    if view.is_system_view:
        raise ViewPermissionError("System views cannot be deleted.")

    if view.created_by != user_id:
        raise ViewPermissionError("Only the view creator can delete this view.")

    events = [AuditEvent("DELETE", "saved_view", view_id, _view_audit_context(org_id, user_id, audit_context))]
    with audit_operation(events), session_guard(db.session):
        # Prevent deletion/new FK references while deleting actual preferences with RETURNING.
        locked = InventoryView.query.filter_by(id=view.id, org_id=org_id).with_for_update().one_or_none()
        if locked is None:
            events.clear()
            raise ViewNotFoundError()
        preferences = db.session.execute(
            delete(UserViewPreference)
            .where(UserViewPreference.default_view_id == view.id)
            .returning(UserViewPreference.org_id, UserViewPreference.user_id)
        ).all()
        events.extend(
            AuditEvent("DELETE", "view_preference", f"{pref_org}:{pref_user}", events[0].context)
            for pref_org, pref_user in preferences
        )
        db.session.delete(view)

    logger.info("Deleted view %s by %s", view_id, user_id)


def clone_view(view_id: str, org_id: str, user_id: str, *, audit_context: AuditContext | None = None) -> InventoryView:
    source = _get_visible_view(view_id, org_id, user_id)

    clone_name = f"{CLONE_NAME_PREFIX}{source.name}"[:MAX_VIEW_NAME_LENGTH]

    cloned = InventoryView(
        id=uuid4(),
        org_id=org_id,
        name=clone_name,
        description=source.description,
        configuration=deepcopy(source.configuration),
        org_wide=False,
        created_by=user_id,
    )

    events = [AuditEvent("CREATE", "saved_view", str(cloned.id), _view_audit_context(org_id, user_id, audit_context))]
    with audit_operation(events), session_guard(db.session, close=False):
        db.session.add(cloned)

    db.session.refresh(cloned)
    logger.info("Cloned view %s -> %s by %s", view_id, cloned.id, user_id)
    return cloned


def get_default_view_id(org_id: str, user_id: str) -> str:
    """Return the user's pinned default view ID, or fall back to 'All systems'.

    If a preference exists but the pinned view is no longer visible to the user,
    falls back to the system default.
    """
    view_id = (
        db.session.query(UserViewPreference.default_view_id)
        .join(
            InventoryView,
            InventoryView.id == UserViewPreference.default_view_id,
        )
        .filter(
            UserViewPreference.org_id == org_id,
            UserViewPreference.user_id == user_id,
            _visibility_filter(org_id, user_id),
        )
        .scalar()
    )
    if view_id is not None:
        return str(view_id)
    return _get_system_default_view_id()


def set_default_view(
    org_id: str, user_id: str, view_id: str, *, audit_context: AuditContext | None = None
) -> InventoryView:
    """Pin a visible view as the user's default. Upserts the preference row."""
    view = _get_visible_view(view_id, org_id, user_id)

    stmt = insert(UserViewPreference).values(
        org_id=org_id,
        user_id=user_id,
        default_view_id=view.id,
        updated_on=_time_now(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["org_id", "user_id"],
        set_={
            "default_view_id": stmt.excluded.default_view_id,
            "updated_on": stmt.excluded.updated_on,
        },
        where=UserViewPreference.default_view_id.is_distinct_from(stmt.excluded.default_view_id),
    )

    events = [
        AuditEvent(
            "SET_DEFAULT",
            "view_preference",
            f"{org_id}:{user_id}",
            _view_audit_context(org_id, user_id, audit_context),
        )
    ]
    with audit_operation(events), session_guard(db.session, close=False):
        # SQL decides whether a business value changes atomically, including concurrent upserts.
        if db.session.execute(stmt.returning(UserViewPreference.default_view_id)).one_or_none() is None:
            events.clear()

    logger.info("Set default view %s for org %s user %s", view_id, org_id, user_id)
    return view


def delete_default_view(org_id: str, user_id: str, *, audit_context: AuditContext | None = None) -> None:
    """Unpin the user's default view. Idempotent if no preference exists."""
    events = [
        AuditEvent(
            "DELETE", "view_preference", f"{org_id}:{user_id}", _view_audit_context(org_id, user_id, audit_context)
        )
    ]
    with audit_operation(events), session_guard(db.session):
        deleted = UserViewPreference.query.filter_by(org_id=org_id, user_id=user_id).delete()
        if not deleted:
            events.clear()

    if deleted:
        logger.info("Deleted default view preference for org %s user %s", org_id, user_id)
