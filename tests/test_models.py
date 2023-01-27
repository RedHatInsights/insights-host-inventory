import uuid
from copy import deepcopy
from datetime import datetime
from datetime import timedelta

import pytest
from marshmallow import ValidationError as MarshmallowValidationError
from sqlalchemy.exc import DataError
from sqlalchemy.exc import IntegrityError

from app import db
from app.exceptions import ValidationException
from app.models import CanonicalFactsSchema
from app.models import Host
from app.models import HostSchema
from app.models import LimitedHost
from app.utils import Tag
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import now
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY


"""
These tests are for testing the db model classes outside of the api.
"""


def test_create_host_with_fqdn_and_display_name_as_empty_str(db_create_host):
    # Verify that the display_name is populated from the fqdn
    fqdn = "spacely_space_sprockets.orbitcity.com"

    created_host = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "canonical_facts": {"fqdn": fqdn},
            "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
        },
    )

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


def test_update_existing_host_display_name_changing_fqdn(db_create_host):
    old_fqdn = "host1.domain1.com"
    new_fqdn = "host2.domain2.com"
    insights_id = generate_uuid()

    existing_host = db_create_host(
        extra_data={"canonical_facts": {"fqdn": old_fqdn, "insights_id": insights_id}, "display_name": None}
    )

    # Set the display_name to the old FQDN
    existing_host.display_name = old_fqdn
    db.session.commit()
    assert existing_host.display_name == old_fqdn

    # Update the host
    input_host = Host(
        {"fqdn": new_fqdn, "insights_id": insights_id}, display_name="", reporter="puptoo", stale_timestamp=now()
    )
    existing_host.update(input_host)

    assert existing_host.display_name == new_fqdn


def test_update_existing_host_update_display_name_from_id_using_existing_fqdn(db_create_host):
    expected_fqdn = "host1.domain1.com"
    insights_id = generate_uuid()

    existing_host = db_create_host(extra_data={"canonical_facts": {"insights_id": insights_id}, "display_name": None})

    db.session.commit()
    assert existing_host.display_name == str(existing_host.id)

    # Update the host
    input_host = Host({"insights_id": insights_id, "fqdn": expected_fqdn}, reporter="puptoo", stale_timestamp=now())
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

    existing_host = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "canonical_facts": {"insights_id": insights_id},
            "display_name": None,
            "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
        },
    )

    # Clear the display_name
    existing_host.display_name = None
    db.session.commit()
    assert existing_host.display_name is None

    # Update the host
    input_host = Host({"insights_id": insights_id}, display_name="", reporter="puptoo", stale_timestamp=now())
    existing_host.update(input_host)

    assert existing_host.display_name == existing_host.id


def test_create_host_without_system_profile(db_create_host):
    # Test the situation where the db/sqlalchemy sets the
    # system_profile_facts to None
    created_host = db_create_host(
        extra_data={"canonical_facts": {"fqdn": "fred.flintstone.com"}, "display_name": "fred"}
    )
    assert created_host.system_profile_facts == {}


def test_create_host_with_system_profile(db_create_host):
    system_profile_facts = {"number_of_cpus": 1, "owner_id": SYSTEM_IDENTITY["system"]["cn"]}

    created_host = db_create_host(SYSTEM_IDENTITY, extra_data={"system_profile_facts": system_profile_facts})

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
        "org_id": USER_IDENTITY["org_id"],
        "tags": tags,
        "stale_timestamp": now().isoformat(),
        "reporter": "test",
    }
    validated_host = HostSchema().load(host)

    assert validated_host["tags"] == tags


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
    with pytest.raises(MarshmallowValidationError) as exception:
        HostSchema().load(host)

    error_messages = exception.value.normalized_messages()
    assert "tags" in error_messages
    assert error_messages["tags"] == {0: {"key": ["Missing data for required field."]}}


@pytest.mark.parametrize("missing_field", ["canonical_facts", "stale_timestamp", "reporter"])
def test_host_models_missing_fields(missing_field):
    limited_values = {
        "account": USER_IDENTITY["account_number"],
        "canonical_facts": {"fqdn": "foo.qoo.doo.noo"},
        "system_profile_facts": {"number_of_cpus": 1},
    }
    if missing_field in limited_values:
        limited_values[missing_field] = None

    # LimitedHost should be fine with these missing values
    LimitedHost(**limited_values)

    values = {**limited_values, "stale_timestamp": now(), "reporter": "reporter"}
    if missing_field in values:
        values[missing_field] = None

    # Host should complain about the missing values
    with pytest.raises(ValidationException):
        Host(**values)


def test_host_schema_timezone_enforced():
    host = {
        "fqdn": "scooby.doo.com",
        "display_name": "display_name",
        "account": USER_IDENTITY["account_number"],
        "stale_timestamp": now().replace(tzinfo=None).isoformat(),
        "reporter": "test",
    }
    with pytest.raises(MarshmallowValidationError) as exception:
        HostSchema().load(host)

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
        SYSTEM_IDENTITY,
        extra_data={
            "canonical_facts": {"fqdn": "fred.flintstone.com"},
            "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
            "display_name": "display_name",
            "tags": tags,
        },
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
    db_create_host(host=inserted_host)

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
    db_create_host(host=host)

    assert isinstance(host.id, uuid.UUID)


def test_host_model_default_timestamps(db_create_host):
    host = Host(
        account=USER_IDENTITY["account_number"],
        canonical_facts={"fqdn": "fqdn"},
        reporter="yupana",
        stale_timestamp=now(),
    )

    before_commit = now()
    db_create_host(host=host)
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
    db_create_host(host=host)
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

    db_create_host(host=host)

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
        db_create_host(host=host)


def test_create_host_sets_per_reporter_staleness(db_create_host, models_datetime_mock):
    stale_timestamp = models_datetime_mock + timedelta(days=1)

    input_host = Host(
        {"fqdn": "fqdn"}, display_name="display_name", reporter="puptoo", stale_timestamp=stale_timestamp
    )
    created_host = db_create_host(host=input_host)

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
    existing_host = db_create_host(host=input_host)

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


@pytest.mark.parametrize(
    "provider",
    (
        {"type": "alibaba", "id": generate_uuid()},
        {"type": "aws", "id": "i-05d2313e6b9a42b16"},
        {"type": "azure", "id": generate_uuid()},
        {"type": "gcp", "id": generate_uuid()},
        {"type": "ibm", "id": generate_uuid()},
    ),
)
def test_valid_providers(provider):
    canonical_facts = {"provider_id": provider.get("id"), "provider_type": provider.get("type")}
    validated_host = CanonicalFactsSchema().load(canonical_facts)

    assert validated_host["provider_id"] == provider.get("id")
    assert validated_host["provider_type"] == provider.get("type")


@pytest.mark.parametrize(
    "canonical_facts",
    (
        {
            "provider_type": "invalid",
            "provider_id": "i-05d2313e6b9a42b16",
        },  # invalid provider_type (value not in enum)
        {"provider_id": generate_uuid()},  # missing provider_type
        {"provider_type": "azure"},  # missing provider_id
        {"provider_type": "aws", "provider_id": None},  # invalid provider_id (None)
        {"provider_type": None, "provider_id": generate_uuid()},  # invalid provider_type (None)
        {"provider_type": "azure", "provider_id": ""},  # invalid provider_id (empty string)
        {"provider_type": "aws", "provider_id": "  "},  # invalid provider_id (blank space)
        {"provider_type": "aws", "provider_id": "\t"},  # invalid provider_id (tab)
    ),
)
def test_invalid_providers(canonical_facts):
    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


@pytest.mark.parametrize(
    "ip_addresses", (["127.0.0.1"], ["1.2.3.4"], ["2001:db8:3333:4444:5555:6666:7777:8888"], ["::"], ["2001:db8::"])
)
def test_valid_ip_addresses(ip_addresses):
    CanonicalFactsSchema().load({"ip_addresses": ip_addresses})


@pytest.mark.parametrize(
    "ip_addresses",
    (
        ["just_a_string"],
        ["1.2.3"],
        ["1.2.3.4.5"],
        ["1.2.256.0"],
        ["2001:db8:3333:4444:5555:6666:7777:8888:9999"],
        ["1111:2222:3333:4444:5555:6666:7777:gb8"],
    ),
)
def test_invalid_ip_addresses(ip_addresses):
    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load({"ip_addresses": ip_addresses})


def test_create_delete_group_happy(db_create_group, db_get_group, db_delete_group):
    group_name = "Host Group 1"

    # Verify that the group is created successfully
    created_group = db_create_group(name=group_name)
    assert db_get_group(created_group.id).name == group_name

    # Verify that the same group is deleted successfully
    db_delete_group(created_group.id)
    assert db_get_group(created_group.id) is None


def test_create_group_no_name(db_create_group):
    # Make sure we can't create a group with an empty name

    with pytest.raises(ValidationException):
        db_create_group(name=None)


def test_create_group_existing_name_diff_org(db_create_group, db_get_group):
    # Make sure we can't create two groups with the same name in the same org
    group_name = "TestGroup_diff_org"

    group1 = db_create_group(name=group_name)
    assert db_get_group(group1.id).name == group_name

    diff_identity = deepcopy(SYSTEM_IDENTITY)
    diff_identity["org_id"] = "diff_id"
    diff_identity["account"] = "diff_id"

    group2 = db_create_group(
        diff_identity,
        name=group_name,
    )

    assert db_get_group(group2.id).name == group_name


def test_create_group_existing_name_same_org(db_create_group):
    # Make sure we can't create two groups with the same name in the same org
    group_name = "TestGroup"
    db_create_group(name=group_name)
    with pytest.raises(IntegrityError):
        db_create_group(name=group_name)


def test_add_delete_host_group_happy(
    db_create_host,
    db_create_group,
    db_create_host_group_assoc,
    db_get_hosts_for_group,
    db_get_groups_for_host,
    db_remove_hosts_from_group,
):
    hosts_to_create = 3
    host_display_name_base = "hostgroup test host"
    group_name = "Test Group Happy"

    # Create a group to associate with the hosts
    created_group = db_create_group(name=group_name)
    created_host_list = []

    for index in range(hosts_to_create):
        created_host = db_create_host(
            SYSTEM_IDENTITY,
            extra_data={
                "display_name": f"{host_display_name_base}_{index}",
                "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
            },
        )

        # Put the created host in the created group
        db_create_host_group_assoc(host_id=created_host.id, group_id=created_group.id)

        # Assert that the host that was just inserted has the correct group
        retrieved_group = db_get_groups_for_host(created_host.id)[0]
        assert retrieved_group.name == group_name
        created_host_list.append(created_host)

    # Fetch the list of hosts that we just created
    retrieved_host_list = db_get_hosts_for_group(created_group.id)

    # Verify that each host we created is present in the retrieved list
    for host in created_host_list:
        assert host in retrieved_host_list

    # Remove all hosts but one from the group
    host_ids_to_remove = [host.id for host in created_host_list][1:hosts_to_create]
    db_remove_hosts_from_group(host_ids_to_remove, created_group.id)

    # Assert that the first host is still in the group (and that the others are not)
    retrieved_host_list = db_get_hosts_for_group(created_group.id)
    assert len(retrieved_host_list) == 1
    assert created_host_list[0].id == retrieved_host_list[0].id
