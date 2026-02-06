from __future__ import annotations

import logging
from collections.abc import Callable
from collections.abc import Collection
from datetime import UTC
from datetime import datetime
from typing import Any
from typing import Literal
from typing import TypeVar
from typing import overload

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import String
from sqlalchemy import bindparam
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session
from typing_extensions import ParamSpec

from iqe_host_inventory.schemas import PER_REPORTER_STALENESS
from iqe_host_inventory.schemas import per_reporter_staleness_from_dict
from iqe_host_inventory.utils.datagen_utils import DEFAULT_INSIGHTS_ID
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_uuid

T = TypeVar("T")
P = ParamSpec("P")

Base: type = declarative_base()
logger = logging.getLogger(__name__)


class Host(Base):
    __tablename__ = "hosts"

    id = Column(UUID(as_uuid=True), primary_key=True)
    account = Column(String())
    org_id = Column(String())
    display_name = Column(String())
    ansible_host = Column(String())
    insights_id = Column(UUID(as_uuid=True))
    subscription_manager_id = Column(String())
    satellite_id = Column(String())
    fqdn = Column(String())
    bios_uuid = Column(String())
    ip_addresses = Column(JSONB)
    mac_addresses = Column(JSONB)
    provider_id = Column(String())
    provider_type = Column(String())
    created_on = Column(DateTime(timezone=True))
    modified_on = Column(DateTime(timezone=True))
    facts = Column(JSONB)
    tags = Column(JSONB)
    tags_alt = Column(JSONB)
    groups = Column(JSONB)
    last_check_in = Column(DateTime(timezone=True))
    stale_timestamp = Column(DateTime(timezone=True))
    reporter = Column(String())
    per_reporter_staleness = Column(JSONB)


class Group(Base):
    __tablename__ = "groups"

    id = Column(UUID(as_uuid=True), primary_key=True)
    account = Column(String())
    org_id = Column(String())
    name = Column(String())
    created_on = Column(DateTime(timezone=True))
    modified_on = Column(DateTime(timezone=True))


class HostGroupAssoc(Base):
    __tablename__ = "hosts_groups"

    org_id = Column(UUID(as_uuid=True), primary_key=True)
    host_id = Column(UUID(as_uuid=True), primary_key=True)
    group_id = Column(UUID(as_uuid=True), primary_key=True)


class AsDictWrapper[T]:
    """
    Abstracts the as_dict pattern for database helpers.
    When as_dict is true, returns parameter dict instead of ORM type.
    """

    wrap_with: type[T]
    function: Callable[..., dict[str, Any]]

    def __init__(self, wrap_with: type[T], function: Callable[..., dict[str, Any]]) -> None:
        self.wrap_with = wrap_with
        self.function = function

    @classmethod
    def decorate(cls, wrap_with: type[T]) -> AsDictWrapperDecorator[T]:
        return AsDictWrapperDecorator(wrap_with)

    @overload
    def __call__(self, *args: Any, as_dict: Literal[False] = False, **kwargs: Any) -> T: ...

    @overload
    def __call__(self, *args: Any, as_dict: Literal[True], **kwargs: Any) -> dict[str, Any]: ...

    def __call__(self, *args: Any, as_dict: bool = False, **kwargs: Any) -> T | dict[str, Any]:
        result = self.function(*args, **kwargs)
        return result if as_dict else self.wrap_with(**result)


class AsDictWrapperDecorator[T]:
    """Decorator factory for AsDictWrapper."""

    def __init__(self, wrap_with: type[T]) -> None:
        self.wrap_with = wrap_with

    def __repr__(self) -> str:
        return f"<AsDictWrapperDecorator {self.wrap_with}>"

    def __call__(self, function: Callable[..., dict[str, Any]]) -> AsDictWrapper[T]:
        return AsDictWrapper(self.wrap_with, function)


@AsDictWrapper.decorate(Host)
def minimal_db_host(empty_strings: bool = False, **fields: Any) -> dict[str, Any]:
    result = {
        "id": generate_uuid(),
        "org_id": "" if empty_strings else generate_uuid(),
        "created_on": datetime.now(UTC),
        "modified_on": datetime.now(UTC),
        "last_check_in": datetime.now(UTC),
        "groups": [],
        "stale_timestamp": datetime.now(UTC),
        "reporter": "" if empty_strings else "iqe-hbi",
        **fields,
    }
    # Set insights_id to DEFAULT_INSIGHTS_ID if not provided or None, matching main app behavior
    if result.get("insights_id") is None:
        result["insights_id"] = DEFAULT_INSIGHTS_ID
    return result


@AsDictWrapper.decorate(Group)
def minimal_db_group(empty_strings: bool = False, **fields: Any) -> dict[str, Any]:
    return {
        "id": generate_uuid(),
        "org_id": generate_uuid(),
        "name": "" if empty_strings else generate_display_name(),
        "created_on": datetime.now(UTC),
        "modified_on": datetime.now(UTC),
        **fields,
    }


@AsDictWrapper.decorate(HostGroupAssoc)
def minimal_db_host_group_assoc(
    org_id: str, host_id: str, group_id: str, **fields: Any
) -> dict[str, Any]:
    """Org ID, Host ID and Group ID are foreign keys, so they must be provided"""
    return {
        "org_id": org_id,
        "host_id": host_id,
        "group_id": group_id,
        **fields,
    }


def query_hosts_ids_all(inventory_db_session: Session) -> list[str]:
    statement = select(Host.id)
    return inventory_db_session.execute(statement).scalars().all()


def query_host_staleness(inventory_db_session: Session, host_id: str) -> PER_REPORTER_STALENESS:
    statement = select(Host.per_reporter_staleness).filter_by(id=host_id)
    result = inventory_db_session.scalar(statement)
    return per_reporter_staleness_from_dict(result)


def query_hosts_by_ids(inventory_db_session: Session, host_ids: Collection[str]) -> list[Host]:
    statement = select(Host).filter(Host.id.in_(host_ids))
    return inventory_db_session.execute(statement).scalars().all()


def query_groups_ids_all(inventory_db_session: Session) -> list[str]:
    statement = select(Group.id)
    return inventory_db_session.execute(statement).scalars().all()


def query_groups_by_ids(inventory_db_session: Session, group_ids: Collection[str]) -> list[Group]:
    statement = select(Group).filter(Group.id.in_(group_ids))
    return inventory_db_session.execute(statement).scalars().all()


def query_groups_by_names(
    inventory_db_session: Session, group_names: Collection[str]
) -> list[Group]:
    statement = select(Group).filter(Group.name.in_(group_names))
    return inventory_db_session.execute(statement).scalars().all()


def query_associations_by_host_ids(
    inventory_db_session: Session, host_ids: Collection[str]
) -> list[HostGroupAssoc]:
    statement = select(HostGroupAssoc).filter(HostGroupAssoc.host_id.in_(host_ids))
    return inventory_db_session.execute(statement).scalars().all()


def query_associations_by_group_ids(
    inventory_db_session: Session, group_ids: Collection[str]
) -> list[HostGroupAssoc]:
    statement = select(HostGroupAssoc).filter(HostGroupAssoc.group_id.in_(group_ids))
    return inventory_db_session.execute(statement).scalars().all()


def query_hosts_by_insights_id(
    inventory_db_session: Session, host_insights_ids: Collection[str]
) -> Any:
    query = "SELECT id from hosts WHERE insights_id IN :ids;"
    t = text(query).bindparams(bindparam("ids", expanding=True))
    return inventory_db_session.execute(t, {"ids": host_insights_ids})
