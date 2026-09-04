from __future__ import annotations

from copy import deepcopy

from sqlalchemy import and_
from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import insert

from app.exceptions import InventoryException
from app.logging import get_logger
from app.models import InventoryView
from app.models import UserViewPreference
from app.models import db
from app.models.utils import _time_now
from app.models.views import MAX_VIEW_NAME_LENGTH
from lib.db import session_guard

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

_SYSTEM_DEFAULT_VIEW_ID: str | None = None


def _clear_system_default_view_cache() -> None:
    """Reset the cached All systems view ID. Intended for tests."""
    global _SYSTEM_DEFAULT_VIEW_ID
    _SYSTEM_DEFAULT_VIEW_ID = None


def _get_system_default_view_id() -> str:
    """Return the UUID of the seeded 'All systems' system view (cached after first lookup)."""
    global _SYSTEM_DEFAULT_VIEW_ID
    if _SYSTEM_DEFAULT_VIEW_ID is None:
        view = InventoryView.query.filter(
            InventoryView.org_id.is_(None),
            InventoryView.name == ALL_SYSTEMS_VIEW_NAME,
        ).one_or_none()
        if view is None:
            raise InventoryException(
                status=500,
                title="Internal Server Error",
                detail=f"System default view '{ALL_SYSTEMS_VIEW_NAME}' not found.",
            )
        _SYSTEM_DEFAULT_VIEW_ID = str(view.id)
    return _SYSTEM_DEFAULT_VIEW_ID


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


def create_view(data: dict, org_id: str, user_id: str) -> InventoryView:
    view = InventoryView(
        org_id=org_id,
        name=data["name"],
        description=data.get("description"),
        configuration=data["configuration"],
        org_wide=data.get("org_wide", False),
        created_by=user_id,
    )

    with session_guard(db.session, close=False):
        db.session.add(view)

    db.session.refresh(view)
    logger.info("Created view %s for org %s by %s", view.id, org_id, user_id)
    return view


def update_view(view_id: str, data: dict, org_id: str, user_id: str) -> InventoryView:
    view = _get_visible_view(view_id, org_id, user_id)

    if view.is_system_view:
        raise ViewPermissionError("System views cannot be modified.")

    if view.created_by != user_id:
        raise ViewPermissionError("Only the view creator can update this view.")

    with session_guard(db.session, close=False):
        view.patch(data)

    db.session.refresh(view)
    logger.info("Updated view %s by %s", view_id, user_id)
    return view


def delete_view(view_id: str, org_id: str, user_id: str) -> None:
    view = _get_visible_view(view_id, org_id, user_id)

    if view.is_system_view:
        raise ViewPermissionError("System views cannot be deleted.")

    if view.created_by != user_id:
        raise ViewPermissionError("Only the view creator can delete this view.")

    with session_guard(db.session):
        db.session.delete(view)

    logger.info("Deleted view %s by %s", view_id, user_id)


def clone_view(view_id: str, org_id: str, user_id: str) -> InventoryView:
    source = _get_visible_view(view_id, org_id, user_id)

    clone_name = f"{CLONE_NAME_PREFIX}{source.name}"[:MAX_VIEW_NAME_LENGTH]

    cloned = InventoryView(
        org_id=org_id,
        name=clone_name,
        description=source.description,
        configuration=deepcopy(source.configuration),
        org_wide=False,
        created_by=user_id,
    )

    with session_guard(db.session, close=False):
        db.session.add(cloned)

    db.session.refresh(cloned)
    logger.info("Cloned view %s -> %s by %s", view_id, cloned.id, user_id)
    return cloned


def get_default_view_id(org_id: str, user_id: str) -> str:
    """Return the user's pinned default view ID, or fall back to 'All systems'.

    If a preference exists but the pinned view is no longer visible to the user,
    falls back to the system default.
    """
    pref = UserViewPreference.query.filter_by(org_id=org_id, user_id=user_id).one_or_none()
    if pref is None:
        return _get_system_default_view_id()

    visible = InventoryView.query.filter(
        InventoryView.id == pref.default_view_id,
        _visibility_filter(org_id, user_id),
    ).one_or_none()

    if visible is None:
        return _get_system_default_view_id()

    return str(pref.default_view_id)


def set_default_view(org_id: str, user_id: str, view_id: str) -> InventoryView:
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
            "updated_on": _time_now(),
        },
    )

    with session_guard(db.session, close=False):
        db.session.execute(stmt)

    logger.info("Set default view %s for org %s user %s", view_id, org_id, user_id)
    return view


def delete_default_view(org_id: str, user_id: str) -> None:
    """Unpin the user's default view. Idempotent if no preference exists."""
    pref = UserViewPreference.query.filter_by(org_id=org_id, user_id=user_id).one_or_none()
    if pref is None:
        return

    with session_guard(db.session):
        db.session.delete(pref)

    logger.info("Deleted default view preference for org %s user %s", org_id, user_id)
