import uuid
from datetime import datetime

import pytest
from marshmallow import ValidationError
from sqlalchemy.exc import DataError

from app import db
from app.models import Host
from app.models import HttpHostSchema
from app.models import MqHostSchema
from app.serialization import deserialize_host_mq
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
        [
            {"namespace": "satellite", "key": "env", "value": "prod"},
            {"namespace": "insights-client", "key": "env", "value": "ci"},
        ],
        [{"namespace": "satellite", "key": "env"}, {"namespace": "insights-client", "key": "env"}],
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
    validated_host = MqHostSchema(strict=True).load(host)

    assert validated_host.data["tags"] == tags


@pytest.mark.parametrize("tags", [[{"key": "good_tag"}], [{"value": "bad_tag"}]])
def test_host_schema_ignored_tags(tags):
    host = {
        "fqdn": "fred.flintstone.com",
        "display_name": "display_name",
        "account": USER_IDENTITY["account_number"],
        "tags": tags,
        "stale_timestamp": now().isoformat(),
        "reporter": "test",
    }

    validated_host = HttpHostSchema(strict=True).load(host)
    assert "tags" not in validated_host.data


@pytest.mark.parametrize("tags", [[{"namespace": "satellite"}], [{"value": "bad_tag"}]])
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
        MqHostSchema(strict=True).load(host)

    error_messages = exception.value.normalized_messages()
    assert "tags" in error_messages


@pytest.mark.parametrize("schema", [MqHostSchema, HttpHostSchema])
def test_host_schema_timezone_enforced(schema):
    host = {
        "fqdn": "scooby.doo.com",
        "display_name": "display_name",
        "account": USER_IDENTITY["account_number"],
        "stale_timestamp": now().replace(tzinfo=None).isoformat(),
        "reporter": "test",
    }
    with pytest.raises(ValidationError) as exception:
        schema(strict=True).load(host)

    assert "Timestamp must contain timezone info" in str(exception.value)


@pytest.mark.parametrize(
    "tags",
    [
        [
            {"namespace": "satellite", "key": "env", "value": "prod"},
            {"namespace": "insights-client", "key": "env", "value": "ci"},
        ],
        [{"namespace": "satellitez", "key": "env"}, {"namespace": "insights-client", "key": "env"}],
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
        "tags": {"satellite": {"key": ["value"]}},
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
    host = Host(account=USER_IDENTITY["account_number"], canonical_facts={"fqdn": "fqdn"})
    db_create_host(host)

    assert isinstance(host.id, uuid.UUID)


def test_host_model_default_timestamps(db_create_host):
    host = Host(account=USER_IDENTITY["account_number"], canonical_facts={"fqdn": "fqdn"})

    before_commit = now()
    db_create_host(host)
    after_commit = now()

    assert isinstance(host.created_on, datetime)
    assert before_commit < host.created_on < after_commit
    assert isinstance(host.modified_on, datetime)
    assert before_commit < host.modified_on < after_commit


def test_host_model_updated_timestamp(db_create_host):
    host = Host(account=USER_IDENTITY["account_number"], canonical_facts={"fqdn": "fqdn"})

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
    values = {"account": USER_IDENTITY["account_number"], "canonical_facts": {"fqdn": "fqdn"}, **{field: value}}
    if field == "reporter":
        values["stale_timestamp"] = now()

    host = Host(**values)

    with pytest.raises(DataError):
        db_create_host(host)


def test_host_schema_tags_always_lowercase():
    tags = [
        {"namespace": "SatEllIte", "key": "env", "value": "prod"},
        {"namespace": "INsIghTs-ClIenT", "key": "ALLCAPS", "value": "MixEd_CapS"},
    ]
    tags_lowercase_namespaces = {"satellite": {"env": ["prod"]}, "insights-client": {"ALLCAPS": ["MixEd_CapS"]}}

    host = {
        "fqdn": "fred.flintstone.com",
        "display_name": "display_name",
        "account": USER_IDENTITY["account_number"],
        "tags": tags,
        "stale_timestamp": now().isoformat(),
        "reporter": "test",
        "system_profile": {
            "owner_id": "1b36b20f-7fa0-4454-a6d2-008294e06378",
            "number_of_cpus": 1,
            "number_of_sockets": 2,
            "cores_per_socket": 4,
        },
        "subscription_manager_id": "044e36dc-4e2b-4e69-8948-9c65a7bf4976",
    }

    deserialized_host = deserialize_host_mq(host)
    assert deserialized_host.tags == tags_lowercase_namespaces
