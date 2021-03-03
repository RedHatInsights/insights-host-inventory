import uuid
from datetime import datetime
from datetime import timedelta

import pytest
from marshmallow import ValidationError
from sqlalchemy.exc import DataError

from app import db
from app.models import Host
from app.models import HostSchema
from app.utils import Tag
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import now
from tests.helpers.test_utils import USER_IDENTITY

"""
These tests are for testing the db model classes outside of the api.
"""


def test_create_host_with_fqdn_and_display_name_as_empty_str(db_create_host):
    # Verify that the display_name is populated from the fqdn
    fqdn = "spacely_space_sprockets.orbitcity.com"

    created_host = db_create_host(extra_data={"canonical_facts": {"fqdn": fqdn}})

    assert created_host.display_name == fqdn


def test_create_host_with_display_name_and_fqdn_as_empty_str(db_create_host):
    # Verify that the display_name is populated from the id
    created_host = db_create_host(extra_data={"canonical_facts": {"fqdn": ""}, "display_name": ""})

    assert created_host.display_name == str(created_host.id)


def test_update_existing_host_fix_display_name_using_existing_fqdn(db_create_host):
    expected_fqdn = "host1.domain1.com"
    insights_id = generate_uuid()

    existing_host = db_create_host(
        extra_data={"canonical_facts": {"fqdn": expected_fqdn, "insights_id": insights_id}, "display_name": None}
    )

    # Clear the display_name
    existing_host.display_name = None
    db.session.commit()
    assert existing_host.display_name is None

    # Update the host
    input_host = Host({"insights_id": insights_id}, display_name="", reporter="puptoo", stale_timestamp=now())
    existing_host.update(input_host)

    assert existing_host.display_name == expected_fqdn


def test_update_existing_host_fix_display_name_using_input_fqdn(db_create_host):
    # Create an "existing" host
    fqdn = "host1.domain1.com"

    existing_host = db_create_host(extra_data={"canonical_facts": {"fqdn": fqdn}, "display_name": None})

    # Clear the display_name
    existing_host.display_name = None
    db.session.commit()
    assert existing_host.display_name is None

    # Update the host
    expected_fqdn = "different.domain1.com"
    input_host = Host({"fqdn": expected_fqdn}, display_name="", reporter="puptoo", stale_timestamp=now())
    existing_host.update(input_host)

    assert existing_host.display_name == expected_fqdn


def test_update_existing_host_fix_display_name_using_id(db_create_host):
    # Create an "existing" host
    insights_id = generate_uuid()

    existing_host = db_create_host(extra_data={"canonical_facts": {"insights_id": insights_id}, "display_name": None})

    # Clear the display_name
    existing_host.display_name = None
    db.session.commit()
    assert existing_host.display_name is None

    # Update the host
    input_host = Host({"insights_id": insights_id}, display_name="", reporter="puptoo", stale_timestamp=now())
    existing_host.update(input_host)

    assert existing_host.display_name == existing_host.id


# TODO: test for Sat 6.7 hotfix (remove, eventually) See RHCLOUD-5954
def test_update_existing_host_dont_change_display_name(db_create_host):
    # Create an "existing" host
    fqdn = "host1.domain1.com"
    display_name = "foo"
    existing_host = db_create_host(extra_data={"canonical_facts": {"fqdn": fqdn}, "display_name": display_name})

    # Attempt to update the display name from Satellite reporter (shouldn't change)
    expected_fqdn = "different.domain1.com"
    input_host = Host({"fqdn": expected_fqdn}, display_name="dont_change_me", reporter="yupana", stale_timestamp=now())
    existing_host.update(input_host)

    # assert display name hasn't changed
    assert existing_host.display_name == display_name


def test_create_host_without_system_profile(db_create_host):
    # Test the situation where the db/sqlalchemy sets the
    # system_profile_facts to None
    created_host = db_create_host(
        extra_data={"canonical_facts": {"fqdn": "fred.flintstone.com"}, "display_name": "fred"}
    )
    assert created_host.system_profile_facts == {}


def test_create_host_with_system_profile(db_create_host):
    system_profile_facts = {"number_of_cpus": 1}

    created_host = db_create_host(extra_data={"system_profile_facts": system_profile_facts})

    assert created_host.system_profile_facts == system_profile_facts


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
        "account": USER_IDENTITY["account_number"],
        "tags": tags,
        "stale_timestamp": now().isoformat(),
        "reporter": "test",
    }
    validated_host = HostSchema(strict=True).load(host)

    assert validated_host.data["tags"] == tags


@pytest.mark.parametrize("tags", [[{"namespace": "Sat/"}], [{"value": "bad_tag"}]])
def test_host_schema_invalid_tags(tags):
    host = {
        "fqdn": "fred.flintstone.com",
        "display_name": "display_name",
        "account": USER_IDENTITY["account_number"],
        "tags": tags,
        "stale_timestamp": now().isoformat(),
        "reporter": "test",
    }
    with pytest.raises(ValidationError) as exception:
        HostSchema(strict=True).load(host)

    error_messages = exception.value.normalized_messages()
    assert "tags" in error_messages
    assert error_messages["tags"] == {0: {"key": ["Missing data for required field."]}}


def test_host_schema_timezone_enforced():
    host = {
        "fqdn": "scooby.doo.com",
        "display_name": "display_name",
        "account": USER_IDENTITY["account_number"],
        "stale_timestamp": now().replace(tzinfo=None).isoformat(),
        "reporter": "test",
    }
    with pytest.raises(ValidationError) as exception:
        HostSchema(strict=True).load(host)

    assert "Timestamp must contain timezone info" in str(exception.value)


@pytest.mark.parametrize(
    "tags",
    [
        [{"namespace": "Sat", "key": "env", "value": "prod"}, {"namespace": "AWS", "key": "env", "value": "ci"}],
        [{"namespace": "Sat", "key": "env"}, {"namespace": "AWS", "key": "env"}],
    ],
)
def test_create_host_with_tags(tags, db_create_host):
    created_host = db_create_host(
        extra_data={"canonical_facts": {"fqdn": "fred.flintstone.com"}, "display_name": "display_name", "tags": tags}
    )

    assert created_host.tags == tags


def test_update_host_with_tags(db_create_host):
    insights_id = str(uuid.uuid4())
    old_tags = Tag("Sat", "env", "prod").to_nested()
    existing_host = db_create_host(
        extra_data={"canonical_facts": {"insights_id": insights_id}, "display_name": "tagged", "tags": old_tags}
    )

    assert existing_host.tags == old_tags

    # On update each namespace in the input host's tags should be updated.
    new_tags = Tag.create_nested_from_tags([Tag("Sat", "env", "ci"), Tag("AWS", "env", "prod")])
    input_host = db_create_host(
        extra_data={"canonical_facts": {"insights_id": insights_id}, "display_name": "tagged", "tags": new_tags}
    )

    existing_host.update(input_host)

    assert existing_host.tags == new_tags


def test_update_host_with_no_tags(db_create_host):
    insights_id = str(uuid.uuid4())
    old_tags = Tag("Sat", "env", "prod").to_nested()
    existing_host = db_create_host(
        extra_data={"canonical_facts": {"insights_id": insights_id}, "display_name": "tagged", "tags": old_tags}
    )

    # Updating a host should not remove any existing tags if tags are missing from the input host
    input_host = db_create_host(extra_data={"canonical_facts": {"insights_id": insights_id}, "display_name": "tagged"})
    existing_host.update(input_host)

    assert existing_host.tags == old_tags


def test_host_model_assigned_values(db_create_host, db_get_host):
    values = {
        "account": USER_IDENTITY["account_number"],
        "display_name": "display_name",
        "ansible_host": "ansible_host",
        "facts": [{"namespace": "namespace", "facts": {"key": "value"}}],
        "tags": {"namespace": {"key": ["value"]}},
        "canonical_facts": {"fqdn": "fqdn"},
        "system_profile_facts": {"number_of_cpus": 1},
        "stale_timestamp": now(),
        "reporter": "reporter",
    }

    inserted_host = Host(**values)
    db_create_host(inserted_host)

    selected_host = db_get_host(inserted_host.id)
    for key, value in values.items():
        assert getattr(selected_host, key) == value


def test_host_model_default_id(db_create_host):
    host = Host(
        account=USER_IDENTITY["account_number"],
        canonical_facts={"fqdn": "fqdn"},
        reporter="yupana",
        stale_timestamp=now(),
    )
    db_create_host(host)

    assert isinstance(host.id, uuid.UUID)


def test_host_model_default_timestamps(db_create_host):
    host = Host(
        account=USER_IDENTITY["account_number"],
        canonical_facts={"fqdn": "fqdn"},
        reporter="yupana",
        stale_timestamp=now(),
    )

    before_commit = now()
    db_create_host(host)
    after_commit = now()

    assert isinstance(host.created_on, datetime)
    assert before_commit < host.created_on < after_commit
    assert isinstance(host.modified_on, datetime)
    assert before_commit < host.modified_on < after_commit


def test_host_model_updated_timestamp(db_create_host):
    host = Host(
        account=USER_IDENTITY["account_number"],
        canonical_facts={"fqdn": "fqdn"},
        reporter="yupana",
        stale_timestamp=now(),
    )

    before_insert_commit = now()
    db_create_host(host)
    after_insert_commit = now()

    host.canonical_facts = {"fqdn": "ndqf"}

    before_update_commit = now()
    db.session.commit()
    after_update_commit = now()

    assert before_insert_commit < host.created_on < after_insert_commit
    assert before_update_commit < host.modified_on < after_update_commit


def test_host_model_timestamp_timezones(db_create_host):
    host = Host(
        account=USER_IDENTITY["account_number"],
        canonical_facts={"fqdn": "fqdn"},
        stale_timestamp=now(),
        reporter="ingress",
    )

    db_create_host(host)

    assert host.created_on.tzinfo
    assert host.modified_on.tzinfo
    assert host.stale_timestamp.tzinfo


@pytest.mark.parametrize(
    "field,value",
    [("account", "00000000102"), ("display_name", "x" * 201), ("ansible_host", "x" * 256), ("reporter", "x" * 256)],
)
def test_host_model_constraints(field, value, db_create_host):
    values = {
        "account": USER_IDENTITY["account_number"],
        "canonical_facts": {"fqdn": "fqdn"},
        "stale_timestamp": now(),
        **{field: value},
    }
    # add reporter if it's missing because it is now required all the time
    if not values.get("reporter"):
        values["reporter"] = "yupana"

    host = Host(**values)

    with pytest.raises(DataError):
        db_create_host(host)


def test_create_host_sets_per_reporter_staleness(db_create_host, models_datetime_mock):
    stale_timestamp = models_datetime_mock + timedelta(days=1)

    input_host = Host(
        {"fqdn": "fqdn"}, display_name="display_name", reporter="puptoo", stale_timestamp=stale_timestamp
    )
    created_host = db_create_host(input_host)

    assert created_host.per_reporter_staleness == {
        "puptoo": {
            "last_check_in": models_datetime_mock.isoformat(),
            "stale_timestamp": stale_timestamp.isoformat(),
            "check_in_succeeded": True,
        }
    }


def test_update_per_reporter_staleness(db_create_host, models_datetime_mock):
    puptoo_stale_timestamp = models_datetime_mock + timedelta(days=1)
    input_host = Host(
        {"fqdn": "fqdn"}, display_name="display_name", reporter="puptoo", stale_timestamp=puptoo_stale_timestamp
    )
    existing_host = db_create_host(input_host)

    assert existing_host.per_reporter_staleness == {
        "puptoo": {
            "last_check_in": models_datetime_mock.isoformat(),
            "stale_timestamp": puptoo_stale_timestamp.isoformat(),
            "check_in_succeeded": True,
        }
    }

    puptoo_stale_timestamp += timedelta(days=1)

    update_host = Host(
        {"fqdn": "fqdn"}, display_name="display_name", reporter="puptoo", stale_timestamp=puptoo_stale_timestamp
    )
    existing_host.update(update_host)

    # datetime will not change because the datetime.now() method is patched
    assert existing_host.per_reporter_staleness == {
        "puptoo": {
            "last_check_in": models_datetime_mock.isoformat(),
            "stale_timestamp": puptoo_stale_timestamp.isoformat(),
            "check_in_succeeded": True,
        }
    }

    yupana_stale_timestamp = puptoo_stale_timestamp + timedelta(days=1)

    update_host = Host(
        {"fqdn": "fqdn"}, display_name="display_name", reporter="yupana", stale_timestamp=yupana_stale_timestamp
    )
    existing_host.update(update_host)

    # datetime will not change because the datetime.now() method is patched
    assert existing_host.per_reporter_staleness == {
        "puptoo": {
            "last_check_in": models_datetime_mock.isoformat(),
            "stale_timestamp": puptoo_stale_timestamp.isoformat(),
            "check_in_succeeded": True,
        },
        "yupana": {
            "last_check_in": models_datetime_mock.isoformat(),
            "stale_timestamp": yupana_stale_timestamp.isoformat(),
            "check_in_succeeded": True,
        },
    }
