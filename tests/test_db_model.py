import uuid
from datetime import datetime
from datetime import timezone

import pytest
from marshmallow import ValidationError
from pytest import mark
from pytest import raises
from sqlalchemy.exc import DataError

from app import db
from app.models import Host
from app.models import HostSchema
from app.utils import Tag

"""
These tests are for testing the db model classes outside of the api.
"""


class HostTest(Host):
    def __init__(self, *args, **kwargs):
        super(Host, self).__init__(*args, **kwargs)


def _create_host(insights_id=None, fqdn=None, display_name=None, tags=None):
    if not insights_id:
        insights_id = str(uuid.uuid4())
    canonical_facts = {"insights_id": insights_id}
    if fqdn is not None:
        canonical_facts["fqdn"] = fqdn
    host = Host(canonical_facts, display_name=display_name, account="00102", tags=tags)
    db.session.add(host)
    db.session.commit()
    return host


def test_create_host_with_fqdn_and_display_name_as_empty_str(flask_app):
    # Verify that the display_name is populated from the fqdn
    fqdn = "spacely_space_sprockets.orbitcity.com"
    created_host = _create_host(fqdn=fqdn, display_name="")
    assert created_host.display_name == fqdn


def test_create_host_with_display_name_and_fqdn_as_empty_str(flask_app):
    # Verify that the display_name is populated from the id
    created_host = _create_host(fqdn="", display_name="")
    assert created_host.display_name == str(created_host.id)


def test_update_existing_host_fix_display_name_using_existing_fqdn(flask_app):
    expected_fqdn = "host1.domain1.com"
    insights_id = str(uuid.uuid4())
    existing_host = _create_host(insights_id=insights_id, fqdn=expected_fqdn, display_name=None)

    # Clear the display_name
    existing_host.display_name = None
    db.session.commit()
    assert existing_host.display_name is None

    # Update the host
    input_host = Host(
        {"insights_id": insights_id}, display_name="", reporter="puptoo", stale_timestamp=datetime.now(timezone.utc)
    )
    existing_host.update(input_host)

    assert existing_host.display_name == expected_fqdn


def test_update_existing_host_fix_display_name_using_input_fqdn(flask_app):
    # Create an "existing" host
    fqdn = "host1.domain1.com"
    existing_host = _create_host(fqdn=fqdn, display_name=None)

    # Clear the display_name
    existing_host.display_name = None
    db.session.commit()
    assert existing_host.display_name is None

    # Update the host
    expected_fqdn = "different.domain1.com"
    input_host = Host(
        {"fqdn": expected_fqdn}, display_name="", reporter="puptoo", stale_timestamp=datetime.now(timezone.utc)
    )
    existing_host.update(input_host)

    assert existing_host.display_name == expected_fqdn


def test_update_existing_host_fix_display_name_using_id(flask_app):
    # Create an "existing" host
    existing_host = _create_host(fqdn=None, display_name=None)

    # Clear the display_name
    existing_host.display_name = None
    db.session.commit()
    assert existing_host.display_name is None

    # Update the host
    input_host = Host(
        {"insights_id": existing_host.canonical_facts["insights_id"]},
        display_name="",
        reporter="puptoo",
        stale_timestamp=datetime.now(timezone.utc),
    )
    existing_host.update(input_host)

    assert existing_host.display_name == existing_host.id


# TODO: test for Sat 6.7 hotfix (remove, eventually) See RHCLOUD-5954
def test_update_existing_host_dont_change_display_name(flask_app):
    # Create an "existing" host
    fqdn = "host1.domain1.com"
    display_name = "foo"
    existing_host = _create_host(fqdn=fqdn, display_name=display_name)

    # Attempt to update the display name from Satellite reporter (shouldn't change)
    expected_fqdn = "different.domain1.com"
    input_host = Host(
        {"fqdn": expected_fqdn},
        display_name="dont_change_me",
        reporter="yupana",
        stale_timestamp=datetime.now(timezone.utc),
    )
    existing_host.update(input_host)

    # assert display name hasn't changed
    assert existing_host.display_name == display_name


def test_create_host_without_system_profile(flask_app):
    # Test the situation where the db/sqlalchemy sets the
    # system_profile_facts to None
    created_host = _create_host(fqdn="fred.flintstone.com", display_name="fred")
    assert created_host.system_profile_facts == {}


def test_create_host_with_system_profile(flask_app):
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


@pytest.mark.parametrize(
    "tags",
    [
        [{"namespace": "Sat", "key": "env", "value": "prod"}, {"namespace": "AWS", "key": "env", "value": "ci"}],
        [{"namespace": "Sat", "key": "env"}, {"namespace": "AWS", "key": "env"}],
    ],
)
def test_host_schema_valid_tags(tags):
    host = {
        "fqdn": "fred.flintstone.com",
        "display_name": "display_name",
        "account": "00102",
        "tags": tags,
        "stale_timestamp": "2019-12-16T10:10:06.754201+00:00",
        "reporter": "test",
    }
    validated_host = HostSchema(strict=True).load(host)

    assert validated_host.data["tags"] == tags


@pytest.mark.parametrize("tags", [[{"namespace": "Sat/"}], [{"value": "bad_tag"}]])
def test_host_schema_invalid_tags(tags):
    host = {"fqdn": "fred.flintstone.com", "display_name": "display_name", "account": "00102", "tags": tags}
    with pytest.raises(ValidationError) as excinfo:
        _ = HostSchema(strict=True).load(host)

    assert "Missing data for required field" in str(excinfo.value)


def test_host_schema_timezone_enforced():
    host = {
        "fqdn": "scooby.doo.com",
        "display_name": "display_name",
        "account": "00102",
        "stale_timestamp": "2020-03-31T10:10:06.754201",
        "reporter": "test",
    }
    with pytest.raises(ValidationError) as excinfo:
        _ = HostSchema(strict=True).load(host)

    assert "Timestamp must contain timezone info" in str(excinfo.value)


@pytest.mark.parametrize(
    "tags",
    [
        [{"namespace": "Sat", "key": "env", "value": "prod"}, {"namespace": "AWS", "key": "env", "value": "ci"}],
        [{"namespace": "Sat", "key": "env"}, {"namespace": "AWS", "key": "env"}],
    ],
)
def test_create_host_with_tags(flask_app, tags):
    host = _create_host(fqdn="fred.flintstone.com", display_name="display_name", tags=tags)

    assert host.tags == tags


def test_update_host_with_tags(flask_app):
    insights_id = str(uuid.uuid4())
    old_tags = Tag("Sat", "env", "prod").to_nested()
    existing_host = _create_host(insights_id=insights_id, display_name="tagged", tags=old_tags)

    assert existing_host.tags == old_tags

    # On update each namespace in the input host's tags should be updated.
    new_tags = Tag.create_nested_from_tags([Tag("Sat", "env", "ci"), Tag("AWS", "env", "prod")])
    input_host = _create_host(insights_id=insights_id, display_name="tagged", tags=new_tags)
    existing_host.update(input_host)

    assert existing_host.tags == new_tags


def test_update_host_with_no_tags(flask_app):
    insights_id = str(uuid.uuid4())
    old_tags = Tag("Sat", "env", "prod").to_nested()
    existing_host = _create_host(insights_id=insights_id, display_name="tagged", tags=old_tags)

    # Updating a host should not remove any existing tags if tags are missing from the input host
    input_host = _create_host(insights_id=insights_id, display_name="tagged")
    existing_host.update(input_host)

    assert existing_host.tags == old_tags


def test_host_model_assigned_values(flask_app):
    values = {
        "account": "00102",
        "display_name": "display_name",
        "ansible_host": "ansible_host",
        "facts": [{"namespace": "namespace", "facts": {"key": "value"}}],
        "tags": {"namespace": {"key": ["value"]}},
        "canonical_facts": {"fqdn": "fqdn"},
        "system_profile_facts": {"number_of_cpus": 1},
        "stale_timestamp": datetime.now(timezone.utc),
        "reporter": "reporter",
    }

    inserted_host = HostTest(**values)
    db.session.add(inserted_host)
    db.session.commit()

    selected_host = Host.query.filter(Host.id == inserted_host.id).first()
    for key, value in values.items():
        assert getattr(selected_host, key) == value


def test_host_model_default_id(flask_app):
    host = HostTest(account="00102", canonical_facts={"fqdn": "fqdn"})
    db.session.add(host)
    db.session.commit()

    assert isinstance(host.id, uuid.UUID)


def test_host_model_default_timestamps(flask_app):
    host = HostTest(account="00102", canonical_facts={"fqdn": "fqdn"})
    db.session.add(host)

    before_commit = datetime.now(timezone.utc)
    db.session.commit()
    after_commit = datetime.now(timezone.utc)

    assert isinstance(host.created_on, datetime)
    assert before_commit < host.created_on < after_commit
    assert isinstance(host.modified_on, datetime)
    assert before_commit < host.modified_on < after_commit


def test_host_model_updated_timestamp(flask_app):
    host = HostTest(account="00102", canonical_facts={"fqdn": "fqdn"})
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


def test_host_model_timestamp_timezones(flask_app):
    host = HostTest(account="00102", canonical_facts={"fqdn": "fqdn"}, stale_timestamp=datetime.now(timezone.utc))
    db.session.add(host)
    db.session.commit()

    assert host.created_on.tzinfo
    assert host.modified_on.tzinfo
    assert host.stale_timestamp.tzinfo


@mark.parametrize(
    ("field", "value"),
    (("account", "00000000102"), ("display_name", "x" * 201), ("ansible_host", "x" * 256), ("reporter", "x" * 256)),
)
def test_host_model_constraints(flask_app, field, value):
    values = {"account": "00102", "canonical_facts": {"fqdn": "fqdn"}, **{field: value}}
    host = HostTest(**values)
    db.session.add(host)

    with raises(DataError):
        db.session.commit()
