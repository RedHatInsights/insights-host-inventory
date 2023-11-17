import os

import pytest
from sqlalchemy_utils import create_database
from sqlalchemy_utils import database_exists
from sqlalchemy_utils import drop_database

from app import db
from app.auth.identity import Identity
from app.config import Config
from app.config import RuntimeEnvironment
from app.models import AssignmentRule
from app.models import Group
from app.models import Host
from app.models import HostGroupAssoc
from app.models import Staleness
from app.serialization import serialize_group
from tests.helpers.db_utils import db_assignment_rule
from tests.helpers.db_utils import db_group
from tests.helpers.db_utils import db_staleness_culling
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.db_utils import minimal_db_host_dict
from tests.helpers.test_utils import now
from tests.helpers.test_utils import set_environment
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY


@pytest.fixture(scope="session")
def database_name():
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
def database(database_name):
    config = Config(RuntimeEnvironment.TEST)
    if not database_exists(config.db_uri):
        create_database(config.db_uri)

    yield config.db_uri

    drop_database(config.db_uri)


@pytest.fixture(scope="function")
def db_get_host(flask_app):
    def _db_get_host(host_id):
        return Host.query.get(host_id)

    return _db_get_host


@pytest.fixture(scope="function")
def db_get_hosts(flask_app):
    def _db_get_hosts(host_ids):
        return Host.query.filter(Host.id.in_(host_ids))

    return _db_get_hosts


@pytest.fixture(scope="function")
def db_get_host_by_insights_id(flask_app):
    def _db_get_host_by_insights_id(insights_id):
        return Host.query.filter(Host.canonical_facts["insights_id"].astext == insights_id).one()

    return _db_get_host_by_insights_id


@pytest.fixture(scope="function")
def db_get_group_by_id(flask_app):
    def _db_get_group_by_id(group_id):
        return Group.query.get(group_id)

    return _db_get_group_by_id


@pytest.fixture(scope="function")
def db_get_group_by_name(flask_app):
    def _db_get_group_by_name(group_name):
        return Group.query.filter(Group.name == group_name).first()

    return _db_get_group_by_name


@pytest.fixture(scope="function")
def db_get_hosts_for_group(flask_app):
    def _db_get_hosts_for_group(group_id):
        return Host.query.join(HostGroupAssoc).filter(HostGroupAssoc.group_id == group_id).all()

    return _db_get_hosts_for_group


@pytest.fixture(scope="function")
def db_get_groups_for_host(flask_app):
    def _db_get_groups_for_host(host_id):
        return Group.query.join(HostGroupAssoc).filter(HostGroupAssoc.host_id == host_id).all()

    return _db_get_groups_for_host


@pytest.fixture(scope="function")
def db_get_assignment_rule(flask_app):
    def _db_get_assignment_rule(ar_id):
        return AssignmentRule.query.get(ar_id)

    return _db_get_assignment_rule


@pytest.fixture(scope="function")
def db_create_host(flask_app):
    def _db_create_host(identity=SYSTEM_IDENTITY, host=None, extra_data=None):
        extra_data = extra_data or {}
        host = host or minimal_db_host(org_id=identity["org_id"], account=identity["account_number"], **extra_data)
        db.session.add(host)
        db.session.commit()
        return host

    return _db_create_host


@pytest.fixture(scope="function")
def db_create_multiple_hosts(flask_app):
    def _db_create_multiple_hosts(identity=SYSTEM_IDENTITY, hosts=None, how_many=10, extra_data=None):
        extra_data = extra_data or {}
        created_hosts = []
        if hosts is not None:
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
def db_create_bulk_hosts(flask_app):
    def _db_create_bulk_hosts(identity=SYSTEM_IDENTITY, how_many=10, extra_data=None):
        extra_data = extra_data or {}
        host_dicts = []

        for _ in range(how_many):
            hd = minimal_db_host_dict(org_id=identity["org_id"], **extra_data)
            host_dicts.append(hd)

        db.engine.execute(Host.__table__.insert(), host_dicts)

    return _db_create_bulk_hosts


@pytest.fixture(scope="function")
def db_create_host_in_unknown_state(db_create_host):
    host = minimal_db_host()
    host.stale_timestamp = None
    host.reporter = None
    return db_create_host(host=host)


@pytest.fixture(scope="function")
def models_datetime_mock(mocker):
    mock = mocker.patch("app.models.datetime", **{"now.return_value": now()})
    return mock.now.return_value


@pytest.fixture(scope="function")
def db_create_group(flask_app):
    def _db_create_group(name, identity=SYSTEM_IDENTITY):
        group = db_group(org_id=identity["org_id"], account=identity["account_number"], name=name)
        db.session.add(group)
        db.session.commit()
        return group

    return _db_create_group


@pytest.fixture(scope="function")
def db_create_host_group_assoc(flask_app, db_get_group_by_id):
    def _db_create_host_group_assoc(host_id, group_id):
        host_group = HostGroupAssoc(host_id=host_id, group_id=group_id)
        db.session.add(host_group)
        identity = Identity(USER_IDENTITY)
        serialized_groups = [serialize_group(db_get_group_by_id(group_id), identity)]
        db.session.query(Host).filter(Host.id == host_id).update({"groups": serialized_groups})

        db.session.commit()
        return host_group

    return _db_create_host_group_assoc


@pytest.fixture(scope="function")
def db_remove_hosts_from_group(flask_app):
    def _db_remove_hosts_from_group(host_id_list, group_id):
        db.session.query(Host).filter(Host.id.in_(host_id_list)).update({"groups": []}, synchronize_session=False)
        delete_query = db.session.query(HostGroupAssoc).filter(
            HostGroupAssoc.group_id == group_id, HostGroupAssoc.host_id.in_(host_id_list)
        )
        delete_query.delete(synchronize_session="fetch")
        db.session.commit()

    return _db_remove_hosts_from_group


@pytest.fixture(scope="function")
def db_delete_group(flask_app):
    def _db_delete_group(group_id):
        delete_query = db.session.query(Group).filter(Group.id == group_id)
        delete_query.delete(synchronize_session="fetch")
        delete_query.session.commit()

    return _db_delete_group


@pytest.fixture(scope="function")
def db_create_group_with_hosts(db_create_group, db_create_host, db_create_host_group_assoc, db_get_group_by_id):
    def _db_create_group_with_hosts(group_name, num_hosts):
        group_id = db_create_group(group_name).id
        host_id_list = [str(db_create_host().id) for _ in range(num_hosts)]
        for host_id in host_id_list:
            db_create_host_group_assoc(host_id, group_id)

        return db_get_group_by_id(group_id)

    return _db_create_group_with_hosts


@pytest.fixture(scope="function")
def db_create_assignment_rule(flask_app):
    def _db_create_assignment_rule(name, group_id, filter, enabled):
        assignment_rule = db_assignment_rule(name=name, group_id=group_id, filter=filter, enabled=enabled)
        db.session.add(assignment_rule)
        db.session.commit()
        return assignment_rule

    return _db_create_assignment_rule


@pytest.fixture(scope="function")
def db_delete_assignment_rule(flask_app):
    def _db_delete_assignment_rule(ar_id):
        delete_query = db.session.query(AssignmentRule).filter(AssignmentRule.id == ar_id)
        delete_query.delete(synchronize_session="fetch")
        delete_query.session.commit()

    return _db_delete_assignment_rule


@pytest.fixture(scope="function")
def db_create_staleness_culling(flask_app):
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
def db_delete_staleness_culling(flask_app):
    def _db_delete_staleness_culling(org_id):
        delete_query = db.session.query(Staleness).filter(Staleness.org_id == org_id)
        delete_query.delete(synchronize_session="fetch")
        delete_query.session.commit()

    return _db_delete_staleness_culling


@pytest.fixture(scope="function")
def db_get_staleness_culling(flask_app):
    def _db_get_staleness_culling(org_id):
        return Staleness.query.filter(Staleness.org_id == org_id).first()

    return _db_get_staleness_culling
