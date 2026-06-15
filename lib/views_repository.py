from __future__ import annotations

from copy import deepcopy

from sqlalchemy import and_
from sqlalchemy import or_

from app.exceptions import InventoryException
from app.logging import get_logger
from app.models import InventoryView
from app.models import db
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
)

CLONE_NAME_PREFIX = "Copy of "


class ViewNotFoundError(InventoryException):
    def __init__(self, detail: str = "View not found."):
        super().__init__(status=404, title="Not Found", detail=detail)


class ViewPermissionError(InventoryException):
    def __init__(self, detail: str):
        super().__init__(status=403, title="Forbidden", detail=detail)


def _visibility_filter(org_id: str, username: str):
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
                InventoryView.created_by == username,
                InventoryView.org_wide.is_(True),
            ),
        ),
    )


def _get_visible_view(view_id: str, org_id: str, username: str) -> InventoryView:
    view = InventoryView.query.filter(
        InventoryView.id == view_id,
        _visibility_filter(org_id, username),
    ).one_or_none()

    if view is None:
        raise ViewNotFoundError()

    return view


def get_views_list(org_id: str, username: str, page: int = 1, per_page: int = 50) -> tuple[list[InventoryView], int]:
    query = InventoryView.query.filter(_visibility_filter(org_id, username)).order_by(InventoryView.modified_on.desc())

    total = query.count()
    views = query.offset((page - 1) * per_page).limit(per_page).all()

    return views, total


def get_view_by_id(view_id: str, org_id: str, username: str) -> InventoryView:
    return _get_visible_view(view_id, org_id, username)


def create_view(data: dict, org_id: str, username: str) -> InventoryView:
    view = InventoryView(
        org_id=org_id,
        name=data["name"],
        description=data.get("description"),
        configuration=data["configuration"],
        org_wide=data.get("org_wide", False),
        created_by=username,
    )

    with session_guard(db.session, close=False):
        db.session.add(view)

    db.session.refresh(view)
    logger.info("Created view %s for org %s by %s", view.id, org_id, username)
    return view


def update_view(view_id: str, data: dict, org_id: str, username: str) -> InventoryView:
    view = _get_visible_view(view_id, org_id, username)

    if view.is_system_view:
        raise ViewPermissionError("System views cannot be modified.")

    if view.created_by != username:
        raise ViewPermissionError("Only the view creator can update this view.")

    with session_guard(db.session, close=False):
        view.patch(data)

    db.session.refresh(view)
    logger.info("Updated view %s by %s", view_id, username)
    return view


def delete_view(view_id: str, org_id: str, username: str) -> None:
    view = _get_visible_view(view_id, org_id, username)

    if view.is_system_view:
        raise ViewPermissionError("System views cannot be deleted.")

    if view.created_by != username:
        raise ViewPermissionError("Only the view creator can delete this view.")

    with session_guard(db.session):
        db.session.delete(view)

    logger.info("Deleted view %s by %s", view_id, username)


def clone_view(view_id: str, org_id: str, username: str) -> InventoryView:
    source = _get_visible_view(view_id, org_id, username)

    clone_name = f"{CLONE_NAME_PREFIX}{source.name}"[:MAX_VIEW_NAME_LENGTH]

    cloned = InventoryView(
        org_id=org_id,
        name=clone_name,
        description=source.description,
        configuration=deepcopy(source.configuration),
        org_wide=False,
        created_by=username,
    )

    with session_guard(db.session, close=False):
        db.session.add(cloned)

    db.session.refresh(cloned)
    logger.info("Cloned view %s -> %s by %s", view_id, cloned.id, username)
    return cloned
