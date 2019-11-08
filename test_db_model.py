import uuid
from datetime import datetime
from datetime import timezone

from pytest import mark
from pytest import raises
from sqlalchemy.exc import DataError

from app import db
from app.models import Host

"""
These tests are for testing the db model classes outside of the api.
"""


class TestHost(Host):
    def __init__(self, *args, **kwargs):
        super(Host, self).__init__(*args, **kwargs)


def _create_host(insights_id=None, fqdn=None, display_name=None):
    if not insights_id:
        insights_id = str(uuid.uuid4())
    canonical_facts = {"insights_id": insights_id}
    if fqdn is not None:
        canonical_facts["fqdn"] = fqdn
    host = Host(canonical_facts, display_name=display_name, account="00102")
    db.session.add(host)
    db.session.commit()
    return host


def test_create_host_with_fqdn_and_display_name_as_empty_str(flask_app_fixture):
    # Verify that the display_name is populated from the fqdn
    fqdn = "spacely_space_sprockets.orbitcity.com"
    created_host = _create_host(fqdn=fqdn, display_name="")
    assert created_host.display_name == fqdn


def test_create_host_with_display_name_and_fqdn_as_empty_str(flask_app_fixture):
    # Verify that the display_name is populated from the id
    created_host = _create_host(fqdn="", display_name="")
    assert created_host.display_name == str(created_host.id)


def test_update_existing_host_fix_display_name_using_existing_fqdn(flask_app_fixture):
    expected_fqdn = "host1.domain1.com"
    insights_id = str(uuid.uuid4())
    existing_host = _create_host(insights_id=insights_id, fqdn=expected_fqdn, display_name=None)

    # Clear the display_name
    existing_host.display_name = None
    db.session.commit()
    assert existing_host.display_name is None

    # Update the host
    input_host = Host({"insights_id": insights_id}, display_name="")
    existing_host.update(input_host)

    assert existing_host.display_name == expected_fqdn


def test_update_existing_host_fix_display_name_using_input_fqdn(flask_app_fixture):
    # Create an "existing" host
    fqdn = "host1.domain1.com"
    existing_host = _create_host(fqdn=fqdn, display_name=None)

    # Clear the display_name
    existing_host.display_name = None
    db.session.commit()
    assert existing_host.display_name is None

    # Update the host
    expected_fqdn = "different.domain1.com"
    input_host = Host({"fqdn": expected_fqdn}, display_name="")
    existing_host.update(input_host)

    assert existing_host.display_name == expected_fqdn


def test_update_existing_host_fix_display_name_using_id(flask_app_fixture):
    # Create an "existing" host
    existing_host = _create_host(fqdn=None, display_name=None)

    # Clear the display_name
    existing_host.display_name = None
    db.session.commit()
    assert existing_host.display_name is None

    # Update the host
    input_host = Host({"insights_id": existing_host.canonical_facts["insights_id"]}, display_name="")
    existing_host.update(input_host)

    assert existing_host.display_name == existing_host.id


def test_create_host_without_system_profile(flask_app_fixture):
    # Test the situation where the db/sqlalchemy sets the
    # system_profile_facts to None
    created_host = _create_host(fqdn="fred.flintstone.com", display_name="fred")
    assert created_host.system_profile_facts == {}


def test_create_host_with_system_profile(flask_app_fixture):
    system_profile_facts = {"number_of_cpus": 1}
    host = Host(
        {"fqdn": "fred.flintstone.com"},
        display_name="display_name",
        account="00102",
        system_profile_facts=system_profile_facts,
    )
    db.session.add(host)
    db.session.commit()

    assert host.system_profile_facts == system_profile_facts


def test_host_model_assigned_values(flask_app_fixture):
    values = {
        "account": "00102",
        "display_name": "display_name",
        "ansible_host": "ansible_host",
        "facts": [{"namespace": "namespace", "facts": {"key": "value"}}],
        "tags": {"namespace": {"key": ["value"]}},
        "canonical_facts": {"fqdn": "fqdn"},
        "system_profile_facts": {"number_of_cpus": 1},
    }

    inserted_host = TestHost(**values)
    db.session.add(inserted_host)
    db.session.commit()

    selected_host = Host.query.filter(Host.id == inserted_host.id).first()
    for key, value in values.items():
        assert getattr(selected_host, key) == value


def test_host_model_default_id(flask_app_fixture):
    host = TestHost(account="00102", canonical_facts={"fqdn": "fqdn"})
    db.session.add(host)
    db.session.commit()

    assert isinstance(host.id, uuid.UUID)


def test_host_model_default_timestamps(flask_app_fixture):
    host = TestHost(account="00102", canonical_facts={"fqdn": "fqdn"})
    db.session.add(host)

    before_commit = datetime.now(timezone.utc)
    db.session.commit()
    after_commit = datetime.now(timezone.utc)

    assert isinstance(host.created_on, datetime)
    assert before_commit < host.created_on < after_commit
    assert isinstance(host.modified_on, datetime)
    assert before_commit < host.modified_on < after_commit


def test_host_model_updated_timestamp(flask_app_fixture):
    host = TestHost(account="00102", canonical_facts={"fqdn": "fqdn"})
    db.session.add(host)

    before_insert_commit = datetime.now(timezone.utc)
    db.session.commit()
    after_insert_commit = datetime.now(timezone.utc)

    host.canonical_facts = {"fqdn": "ndqf"}
    db.session.add(host)

    before_update_commit = datetime.now(timezone.utc)
    db.session.commit()
    after_update_commit = datetime.now(timezone.utc)

    assert before_insert_commit < host.created_on < after_insert_commit
    assert before_update_commit < host.modified_on < after_update_commit


def test_host_model_timestamp_timezones(flask_app_fixture):
    host = TestHost(account="00102", canonical_facts={"fqdn": "fqdn"})
    db.session.add(host)
    db.session.commit()

    assert host.created_on.tzinfo
    assert host.modified_on.tzinfo


@mark.parametrize(
    ("field", "value"), (("account", "00000000102"), ("display_name", "x" * 201), ("ansible_host", "x" * 256))
)
def test_host_model_constraints(flask_app_fixture, field, value):
    values = {"account": "00102", "canonical_facts": {"fqdn": "fqdn"}, **{field: value}}
    host = TestHost(**values)
    db.session.add(host)

    with raises(DataError):
        db.session.commit()
