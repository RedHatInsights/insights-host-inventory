from __future__ import annotations

import os
from collections.abc import Callable
from collections.abc import Generator
from typing import Any
from uuid import UUID

import pytest
from connexion import FlaskApp
from sqlalchemy.orm import Query
from sqlalchemy_utils import create_database
from sqlalchemy_utils import database_exists
from sqlalchemy_utils import drop_database

from app.common import inventory_config
from app.config import Config
from app.environment import RuntimeEnvironment
from app.models import Group
from app.models import Host
from app.models import HostGroupAssoc
from app.models import Staleness
from app.models import db
from lib.group_repository import serialize_group
from tests.helpers.db_utils import db_group
from tests.helpers.db_utils import db_host_with_custom_canonical_facts
from tests.helpers.db_utils import db_staleness_culling
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import now
from tests.helpers.test_utils import set_environment


@pytest.fixture(scope="session")
def database_name() -> Generator[None]:
    db_data = {
        "INVENTORY_DB_NAME": os.getenv("INVENTORY_DB_NAME", "insights"),
        "INVENTORY_DB_PASS": os.getenv("INVENTORY_DB_PASS", "insights"),
        "INVENTORY_DB_USER": os.getenv("INVENTORY_DB_USER", "insights"),
        "INVENTORY_DB_HOST": os.getenv("INVENTORY_DB_HOST", "localhost"),
        "INVENTORY_DB_PORT": os.getenv("INVENTORY_DB_PORT", "5432"),
    }
    db_data["INVENTORY_DB_NAME"] += "-test"
    with set_environment(db_data):
        yield


@pytest.fixture(scope="session")
def database(database_name: None) -> Generator[str]:  # noqa: ARG001
    config = Config(RuntimeEnvironment.TEST)
    if not database_exists(config.db_uri):
        create_database(config.db_uri)

    yield config.db_uri

    drop_database(config.db_uri)


@pytest.fixture(scope="function")
def db_get_host(flask_app: FlaskApp) -> Callable[[UUID], Host | None]:  # noqa: ARG001
    def _db_get_host(host_id: UUID, org_id: str | None = None) -> Host | None:
        org_id = org_id or SYSTEM_IDENTITY["org_id"]
        if inventory_config().hbi_db_refactoring_use_old_table:
            # Old code: filter by ID only
            return Host.query.filter(Host.id == host_id).one_or_none()
        else:
            # New code: filter by org_id and ID
            return Host.query.filter(Host.org_id == org_id, Host.id == host_id).one_or_none()

    return _db_get_host


@pytest.fixture(scope="function")
def db_get_hosts(flask_app: FlaskApp) -> Callable[[list[str], str | None], Query]:  # noqa: ARG001
    def _db_get_hosts(host_ids: list[str], org_id: str | None = None) -> Query:
        org_id = org_id or SYSTEM_IDENTITY["org_id"]
        return Host.query.filter(Host.org_id == org_id, Host.id.in_(host_ids))

    return _db_get_hosts


@pytest.fixture(scope="function")
def db_get_host_by_insights_id(flask_app):  # noqa: ARG001
    def _db_get_host_by_insights_id(insights_id):
        return Host.query.filter(Host.canonical_facts["insights_id"].astext == insights_id).one()

    return _db_get_host_by_insights_id


@pytest.fixture()
def db_get_hosts_by_subman_id(flask_app: FlaskApp) -> Callable[[str], list[Host]]:  # noqa: ARG001
    def _db_get_hosts_by_insights_id(subman_id: str) -> list[Host]:
        return Host.query.filter(Host.canonical_facts["subscription_manager_id"].astext == subman_id).all()

    return _db_get_hosts_by_insights_id


@pytest.fixture()
def db_get_hosts_by_display_name(flask_app: FlaskApp) -> Callable[[str], list[Host]]:  # noqa: ARG001
    def _db_get_hosts_by_display_name(display_name: str) -> list[Host]:
        return Host.query.filter(Host.display_name == display_name).all()

    return _db_get_hosts_by_display_name


@pytest.fixture(scope="function")
def db_get_group_by_id(flask_app):  # noqa: ARG001
    def _db_get_group_by_id(group_id):
        return db.session.get(Group, group_id)

    return _db_get_group_by_id


@pytest.fixture(scope="function")
def db_get_ungrouped_group(flask_app):  # noqa: ARG001
    def _db_get_ungrouped_group(org_id):
        return Group.query.filter(Group.ungrouped.is_(True), Group.org_id == org_id).one_or_none()

    return _db_get_ungrouped_group


@pytest.fixture(scope="function")
def db_get_group_by_name(flask_app):  # noqa: ARG001
    def _db_get_group_by_name(group_name):
        return Group.query.filter(Group.name == group_name).first()

    return _db_get_group_by_name


@pytest.fixture(scope="function")
def db_get_hosts_for_group(flask_app):  # noqa: ARG001
    def _db_get_hosts_for_group(group_id):
        return Host.query.join(HostGroupAssoc).filter(HostGroupAssoc.group_id == group_id).all()

    return _db_get_hosts_for_group


@pytest.fixture(scope="function")
def db_get_groups_for_host(flask_app):  # noqa: ARG001
    def _db_get_groups_for_host(host_id, org_id=None):
        org_id = org_id or SYSTEM_IDENTITY["org_id"]
        return (
            Group.query.join(HostGroupAssoc)
            .filter(HostGroupAssoc.org_id == org_id, HostGroupAssoc.host_id == host_id)
            .all()
        )

    return _db_get_groups_for_host


@pytest.fixture(scope="function")
def db_create_host(flask_app: FlaskApp) -> Callable[..., Host]:  # noqa: ARG001
    def _db_create_host(
        identity: dict[str, Any] | None = None, host: Host | None = None, extra_data: dict[str, Any] | None = None
    ) -> Host:
        identity = identity or SYSTEM_IDENTITY
        extra_data = extra_data or {}
        org_id = extra_data.pop("org_id", None) or identity["org_id"]
        host = host or minimal_db_host(org_id=org_id, account=identity["account_number"], **extra_data)
        db.session.add(host)
        db.session.commit()
        return host

    return _db_create_host


@pytest.fixture(scope="function")
def db_create_host_custom_canonical_facts(flask_app: FlaskApp) -> Callable[..., Host]:  # noqa: ARG001
    def _create_host_custom_canonical_facts(
        identity: dict[str, Any] | None = None, host: Host | None = None, extra_data: dict[str, Any] | None = None
    ) -> Host:
        identity = identity or SYSTEM_IDENTITY
        extra_data = extra_data or {}
        org_id = extra_data.pop("org_id", None) or identity["org_id"]
        host = host or db_host_with_custom_canonical_facts(
            org_id=org_id, account=identity["account_number"], **extra_data
        )
        db.session.add(host)
        db.session.commit()
        return host

    return _create_host_custom_canonical_facts


@pytest.fixture(scope="function")
def db_create_multiple_hosts(flask_app: FlaskApp) -> Callable[..., list[Host]]:  # noqa: ARG001
    def _db_create_multiple_hosts(
        identity: dict[str, Any] | None = None,
        hosts: list[Host] | None = None,
        how_many: int = 10,
        extra_data: dict[str, Any] | None = None,
    ) -> list[Host]:
        identity = identity or SYSTEM_IDENTITY
        extra_data = extra_data or {}
        created_hosts = []
        if isinstance(hosts, list):
            for host in hosts:
                db.session.add(host)
                created_hosts.append(host)
        else:
            for _ in range(how_many):
                host = minimal_db_host(org_id=identity["org_id"], **extra_data)
                db.session.add(host)
                created_hosts.append(host)

        db.session.commit()

        return created_hosts

    return _db_create_multiple_hosts


@pytest.fixture(scope="function")
def db_create_host_in_unknown_state(db_create_host):
    host = minimal_db_host()
    host.stale_timestamp = None
    host.reporter = None
    return db_create_host(host=host)


@pytest.fixture(scope="function")
def models_datetime_mock(mocker):
    mock = mocker.patch("app.models.utils.datetime", **{"now.return_value": now()})
    return mock.now.return_value


@pytest.fixture(scope="function")
def db_create_group(flask_app):  # noqa: ARG001
    def _db_create_group(name, identity=None, ungrouped=False):
        identity = identity or SYSTEM_IDENTITY
        group = db_group(org_id=identity["org_id"], account=identity["account_number"], name=name, ungrouped=ungrouped)
        db.session.add(group)
        db.session.commit()
        return group

    return _db_create_group


@pytest.fixture(scope="function")
def db_create_host_group_assoc(flask_app, db_get_group_by_id):  # noqa: ARG001
    def _db_create_host_group_assoc(host_id, group_id):
        # Get the group to obtain the org_id (same as host's org_id in test fixtures)
        group = db_get_group_by_id(group_id)
        if group is None:
            raise ValueError(f"Group with id {group_id} not found")
        host_group = HostGroupAssoc(host_id=host_id, group_id=group_id, org_id=group.org_id)
        db.session.add(host_group)
        serialized_groups = [serialize_group(group)]
        db.session.query(Host).filter(Host.org_id == group.org_id, Host.id == host_id).update(
            {"groups": serialized_groups}
        )

        db.session.commit()
        return host_group

    return _db_create_host_group_assoc


@pytest.fixture(scope="function")
def db_remove_hosts_from_group(flask_app):  # noqa: ARG001
    def _db_remove_hosts_from_group(host_id_list, group_id):
        # Get the org_id from the group to ensure we use the composite primary key
        group = db.session.query(Group).filter(Group.id == group_id).first()
        if not group:
            raise ValueError(f"Group with id {group_id} not found")
        db.session.query(Host).filter(Host.org_id == group.org_id, Host.id.in_(host_id_list)).update(
            {"groups": []}, synchronize_session=False
        )
        delete_query = db.session.query(HostGroupAssoc).filter(
            HostGroupAssoc.group_id == group_id, HostGroupAssoc.host_id.in_(host_id_list)
        )
        delete_query.delete(synchronize_session="fetch")
        db.session.commit()

    return _db_remove_hosts_from_group


@pytest.fixture(scope="function")
def db_delete_group(flask_app):  # noqa: ARG001
    def _db_delete_group(group_id):
        delete_query = db.session.query(Group).filter(Group.id == group_id)
        delete_query.delete(synchronize_session="fetch")
        delete_query.session.commit()

    return _db_delete_group


@pytest.fixture(scope="function")
def db_create_group_with_hosts(db_create_group, db_create_host, db_create_host_group_assoc, db_get_group_by_id):
    def _db_create_group_with_hosts(group_name, num_hosts, ungrouped=False):
        group_id = db_create_group(group_name, ungrouped=ungrouped).id
        host_id_list = [str(db_create_host().id) for _ in range(num_hosts)]
        for host_id in host_id_list:
            db_create_host_group_assoc(host_id, group_id)

        return db_get_group_by_id(group_id)

    return _db_create_group_with_hosts


@pytest.fixture(scope="function")
def db_create_staleness_culling(flask_app):  # noqa: ARG001
    def _db_create_staleness_culling(
        conventional_time_to_stale=None,
        conventional_time_to_stale_warning=None,
        conventional_time_to_delete=None,
        immutable_time_to_stale=None,
        immutable_time_to_stale_warning=None,
        immutable_time_to_delete=None,
    ):
        staleness_culling = db_staleness_culling(
            conventional_time_to_stale=conventional_time_to_stale,
            conventional_time_to_stale_warning=conventional_time_to_stale_warning,
            conventional_time_to_delete=conventional_time_to_delete,
            immutable_time_to_stale=immutable_time_to_stale,
            immutable_time_to_stale_warning=immutable_time_to_stale_warning,
            immutable_time_to_delete=immutable_time_to_delete,
        )
        db.session.add(staleness_culling)
        db.session.commit()
        return staleness_culling

    return _db_create_staleness_culling


@pytest.fixture(scope="function")
def db_delete_staleness_culling(flask_app):  # noqa: ARG001
    def _db_delete_staleness_culling(org_id):
        delete_query = db.session.query(Staleness).filter(Staleness.org_id == org_id)
        delete_query.delete(synchronize_session="fetch")
        delete_query.session.commit()

    return _db_delete_staleness_culling


@pytest.fixture(scope="function")
def db_get_staleness_culling(flask_app):  # noqa: ARG001
    def _db_get_staleness_culling(org_id):
        return Staleness.query.filter(Staleness.org_id == org_id).first()

    return _db_get_staleness_culling
