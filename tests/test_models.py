import uuid
from contextlib import suppress
from copy import deepcopy
from datetime import datetime
from datetime import timedelta

import pytest
from marshmallow import ValidationError as MarshmallowValidationError
from sqlalchemy.exc import DataError
from sqlalchemy.exc import IntegrityError

from api.host_query import staleness_timestamps
from app.exceptions import ValidationException
from app.models import MAX_CANONICAL_FACTS_VERSION
from app.models import MIN_CANONICAL_FACTS_VERSION
from app.models import ZERO_MAC_ADDRESS
from app.models import CanonicalFactsSchema
from app.models import Host
from app.models import HostSchema
from app.models import InputGroupSchema
from app.models import LimitedHost
from app.models import _create_staleness_timestamps_values
from app.models import db
from app.models.constants import FAR_FUTURE_STALE_TIMESTAMP
from app.models.system_profile import HostStaticSystemProfile
from app.models.system_profiles_dynamic import HostDynamicSystemProfile
from app.staleness_serialization import get_staleness_timestamps
from app.staleness_serialization import get_sys_default_staleness
from app.utils import Tag
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_sample_profile_data
from tests.helpers.test_utils import now

"""
These tests are for testing the db model classes outside of the api.
"""


def test_create_host_with_fqdn_and_display_name_as_empty_str(db_create_host):
    # Verify that the display_name is populated from the fqdn
    fqdn = "spacely_space_sprockets.orbitcity.com"

    created_host = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "canonical_facts": {"fqdn": fqdn, "subscription_manager_id": generate_uuid()},
            "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
        },
    )

    assert created_host.display_name == fqdn


def test_create_host_with_display_name_and_fqdn_as_empty_str(db_create_host):
    # Verify that the display_name is populated from the id
    created_host = db_create_host()

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
    input_host = Host(
        {"insights_id": insights_id},
        display_name="",
        reporter="puptoo",
        stale_timestamp=now(),
        org_id=USER_IDENTITY["org_id"],
    )
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
        {"fqdn": new_fqdn, "insights_id": insights_id},
        display_name="",
        reporter="puptoo",
        stale_timestamp=now(),
        org_id=USER_IDENTITY["org_id"],
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
    input_host = Host(
        {"insights_id": insights_id, "fqdn": expected_fqdn},
        reporter="puptoo",
        stale_timestamp=now(),
        org_id=USER_IDENTITY["org_id"],
    )
    existing_host.update(input_host)

    assert existing_host.display_name == expected_fqdn


def test_update_existing_host_fix_display_name_using_input_fqdn(db_create_host):
    # Create an "existing" host
    fqdn = "host1.domain1.com"
    subman_id = generate_uuid()

    existing_host = db_create_host(
        extra_data={"canonical_facts": {"fqdn": fqdn, "subscription_manager_id": subman_id}}
    )

    # Clear the display_name
    existing_host.display_name = None
    db.session.commit()
    assert existing_host.display_name is None

    # Update the host
    expected_fqdn = "different.domain1.com"
    input_host = Host(
        {"fqdn": expected_fqdn, "subscription_manager_id": subman_id},
        display_name="",
        reporter="puptoo",
        stale_timestamp=now(),
        org_id=USER_IDENTITY["org_id"],
    )
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
    input_host = Host(
        {"insights_id": insights_id},
        display_name="",
        reporter="puptoo",
        stale_timestamp=now(),
        org_id=USER_IDENTITY["org_id"],
    )
    existing_host.update(input_host)

    assert existing_host.display_name == existing_host.id


def test_create_host_without_system_profile(db_create_host):
    # Test the situation where the db/sqlalchemy sets the
    # system_profile_facts to None
    created_host = db_create_host()
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

    values = {**limited_values, "stale_timestamp": now(), "reporter": "reporter", "org_id": USER_IDENTITY["org_id"]}
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

    assert "Not a valid aware datetime" in str(exception.value)


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
            "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
            "display_name": "display_name",
            "tags": tags,
        },
    )

    assert created_host.tags == tags
    assert created_host.tags_alt == tags


def test_update_host_with_tags(db_create_host):
    insights_id = str(uuid.uuid4())
    old_tags = Tag("Sat", "env", "prod").to_nested()
    old_tags_alt = Tag.create_flat_tags_from_structured([Tag("Sat", "env", "prod")])
    existing_host = db_create_host(
        extra_data={"canonical_facts": {"insights_id": insights_id}, "display_name": "tagged", "tags": old_tags}
    )

    assert existing_host.tags == old_tags
    assert existing_host.tags_alt == old_tags_alt

    # On update each namespace in the input host's tags should be updated.
    new_tags = Tag.create_nested_from_tags([Tag("Sat", "env", "ci"), Tag("AWS", "env", "prod")])
    new_tags_alt = Tag.create_flat_tags_from_structured([Tag("Sat", "env", "ci"), Tag("AWS", "env", "prod")])
    input_host = db_create_host(
        extra_data={"canonical_facts": {"insights_id": insights_id}, "display_name": "tagged", "tags": new_tags}
    )

    existing_host.update(input_host)

    assert existing_host.tags == new_tags
    assert sorted(existing_host.tags_alt, key=lambda t: t["namespace"]) == sorted(
        new_tags_alt, key=lambda t: t["namespace"]
    )


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
        "org_id": USER_IDENTITY["org_id"],
        "display_name": "display_name",
        "ansible_host": "ansible_host",
        "facts": [{"namespace": "namespace", "facts": {"key": "value"}}],
        "tags": {"namespace": {"key": ["value"]}},
        "canonical_facts": {"subscription_manager_id": generate_uuid()},
        "system_profile_facts": {"number_of_cpus": 1},
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
        canonical_facts={"subscription_manager_id": generate_uuid()},
        reporter="yupana",
        stale_timestamp=now(),
        org_id=USER_IDENTITY["org_id"],
    )
    db_create_host(host=host)

    assert isinstance(host.id, uuid.UUID)


def test_host_model_default_timestamps(db_create_host):
    host = Host(
        account=USER_IDENTITY["account_number"],
        canonical_facts={"subscription_manager_id": generate_uuid()},
        reporter="yupana",
        stale_timestamp=now(),
        org_id=USER_IDENTITY["org_id"],
    )

    before_commit = now()
    db_create_host(host=host)
    after_commit = now()

    assert isinstance(host.created_on, datetime)
    assert before_commit < host.created_on < after_commit
    assert isinstance(host.modified_on, datetime)
    assert host.modified_on < after_commit


def test_host_model_updated_timestamp(db_create_host):
    host = Host(
        account=USER_IDENTITY["account_number"],
        canonical_facts={"subscription_manager_id": generate_uuid()},
        reporter="yupana",
        stale_timestamp=now(),
        org_id=USER_IDENTITY["org_id"],
    )

    before_insert_commit = now()
    db_create_host(host=host)
    after_insert_commit = now()

    host.canonical_facts = {"fqdn": "ndqf"}

    db.session.commit()
    after_update_commit = now()

    assert before_insert_commit < host.created_on < after_insert_commit
    assert host.modified_on < after_update_commit


def test_host_model_timestamp_timezones(db_create_host):
    host = Host(
        account=USER_IDENTITY["account_number"],
        canonical_facts={"subscription_manager_id": generate_uuid()},
        stale_timestamp=now(),
        reporter="ingress",
        org_id=USER_IDENTITY["org_id"],
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
        "canonical_facts": {"subscription_manager_id": generate_uuid()},
        "stale_timestamp": now(),
        "org_id": USER_IDENTITY["org_id"],
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
        {"subscription_manager_id": generate_uuid()},
        display_name="display_name",
        reporter="puptoo",
        stale_timestamp=stale_timestamp,
        org_id=USER_IDENTITY["org_id"],
    )
    created_host = db_create_host(host=input_host)
    staleness = get_sys_default_staleness()
    st = staleness_timestamps()
    timestamps = get_staleness_timestamps(created_host, st, staleness)

    assert created_host.per_reporter_staleness == {
        "puptoo": {
            "last_check_in": models_datetime_mock.isoformat(),
            "stale_timestamp": timestamps["stale_timestamp"].isoformat(),
            "check_in_succeeded": True,
            "culled_timestamp": timestamps["culled_timestamp"].isoformat(),
            "stale_warning_timestamp": timestamps["stale_warning_timestamp"].isoformat(),
        }
    }


def test_update_per_reporter_staleness(db_create_host, models_datetime_mock):
    puptoo_stale_timestamp = models_datetime_mock + timedelta(days=1)

    subman_id = generate_uuid()
    input_host = Host(
        {"subscription_manager_id": subman_id},
        display_name="display_name",
        reporter="puptoo",
        stale_timestamp=puptoo_stale_timestamp,
        org_id=USER_IDENTITY["org_id"],
    )

    existing_host = db_create_host(host=input_host)
    staleness = get_sys_default_staleness()
    st = staleness_timestamps()
    timestamps = get_staleness_timestamps(existing_host, st, staleness)

    assert existing_host.per_reporter_staleness == {
        "puptoo": {
            "last_check_in": models_datetime_mock.isoformat(),
            "stale_timestamp": timestamps["stale_timestamp"].isoformat(),
            "check_in_succeeded": True,
            "culled_timestamp": timestamps["culled_timestamp"].isoformat(),
            "stale_warning_timestamp": timestamps["stale_warning_timestamp"].isoformat(),
        }
    }

    puptoo_stale_timestamp += timedelta(days=1)

    update_host = Host(
        {"subscription_manager_id": subman_id},
        display_name="display_name",
        reporter="puptoo",
        stale_timestamp=puptoo_stale_timestamp,
        org_id=USER_IDENTITY["org_id"],
    )
    existing_host.update(update_host)

    # datetime will not change because the datetime.now() method is patched
    assert existing_host.per_reporter_staleness == {
        "puptoo": {
            "last_check_in": models_datetime_mock.isoformat(),
            "stale_timestamp": timestamps["stale_timestamp"].isoformat(),
            "check_in_succeeded": True,
            "culled_timestamp": timestamps["culled_timestamp"].isoformat(),
            "stale_warning_timestamp": timestamps["stale_warning_timestamp"].isoformat(),
        }
    }

    yupana_stale_timestamp = puptoo_stale_timestamp + timedelta(days=1)

    update_host = Host(
        {"subscription_manager_id": subman_id},
        display_name="display_name",
        reporter="yupana",
        stale_timestamp=yupana_stale_timestamp,
        org_id=USER_IDENTITY["org_id"],
    )
    existing_host.update(update_host)

    # datetime will not change because the datetime.now() method is patched
    assert existing_host.per_reporter_staleness == {
        "puptoo": {
            "last_check_in": models_datetime_mock.isoformat(),
            "stale_timestamp": timestamps["stale_timestamp"].isoformat(),
            "check_in_succeeded": True,
            "culled_timestamp": timestamps["culled_timestamp"].isoformat(),
            "stale_warning_timestamp": timestamps["stale_warning_timestamp"].isoformat(),
        },
        "yupana": {
            "last_check_in": models_datetime_mock.isoformat(),
            "stale_timestamp": timestamps["stale_timestamp"].isoformat(),
            "check_in_succeeded": True,
            "culled_timestamp": timestamps["culled_timestamp"].isoformat(),
            "stale_warning_timestamp": timestamps["stale_warning_timestamp"].isoformat(),
        },
    }


@pytest.mark.parametrize(
    "new_reporter",
    ["satellite", "discovery"],
)
def test_update_per_reporter_staleness_yupana_replacement(db_create_host, models_datetime_mock, new_reporter):
    yupana_stale_timestamp = models_datetime_mock + timedelta(days=1)
    subman_id = generate_uuid()
    input_host = Host(
        {"subscription_manager_id": subman_id},
        display_name="display_name",
        reporter="yupana",
        stale_timestamp=yupana_stale_timestamp,
        org_id=USER_IDENTITY["org_id"],
    )
    existing_host = db_create_host(host=input_host)

    staleness = get_sys_default_staleness()
    st = staleness_timestamps()
    timestamps = get_staleness_timestamps(existing_host, st, staleness)
    assert existing_host.per_reporter_staleness == {
        "yupana": {
            "last_check_in": models_datetime_mock.isoformat(),
            "stale_timestamp": timestamps["stale_timestamp"].isoformat(),
            "check_in_succeeded": True,
            "culled_timestamp": timestamps["culled_timestamp"].isoformat(),
            "stale_warning_timestamp": timestamps["stale_warning_timestamp"].isoformat(),
        }
    }

    yupana_stale_timestamp += timedelta(days=1)

    update_host = Host(
        {"subscription_manager_id": subman_id},
        display_name="display_name",
        reporter=new_reporter,
        stale_timestamp=yupana_stale_timestamp,
        org_id=USER_IDENTITY["org_id"],
    )
    existing_host.update(update_host)

    # datetime will not change because the datetime.now() method is patched
    assert existing_host.per_reporter_staleness == {
        new_reporter: {
            "last_check_in": models_datetime_mock.isoformat(),
            "stale_timestamp": timestamps["stale_timestamp"].isoformat(),
            "check_in_succeeded": True,
            "culled_timestamp": timestamps["culled_timestamp"].isoformat(),
            "stale_warning_timestamp": timestamps["stale_warning_timestamp"].isoformat(),
        }
    }


def test_canonical_facts_version_default():
    canonical_facts = {"insights_id": generate_uuid()}
    validated_host = CanonicalFactsSchema().load(canonical_facts)

    assert validated_host["canonical_facts_version"] == MIN_CANONICAL_FACTS_VERSION


def test_canonical_facts_version_min():
    canonical_facts = {"canonical_facts_version": MIN_CANONICAL_FACTS_VERSION, "insights_id": generate_uuid()}
    validated_host = CanonicalFactsSchema().load(canonical_facts)

    assert validated_host["canonical_facts_version"] == MIN_CANONICAL_FACTS_VERSION


def test_canonical_facts_version_max():
    canonical_facts = {
        "canonical_facts_version": MAX_CANONICAL_FACTS_VERSION,
        "is_virtual": False,
        "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
        "insights_id": generate_uuid(),
    }
    validated_host = CanonicalFactsSchema().load(canonical_facts)

    assert validated_host["canonical_facts_version"] == MAX_CANONICAL_FACTS_VERSION


def test_canonical_facts_version_toolow():
    canonical_facts = {"canonical_facts_version": MIN_CANONICAL_FACTS_VERSION - 1, "insights_id": generate_uuid()}

    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


def test_canonical_facts_version_toohigh():
    canonical_facts = {"canonical_facts_version": MAX_CANONICAL_FACTS_VERSION + 1, "insights_id": generate_uuid()}

    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


@pytest.mark.parametrize(
    "canonical_facts",
    (
        #
        # canonical_facts_version = 0
        #
        {"provider_type": "alibaba", "provider_id": generate_uuid()},
        {"provider_type": "aws", "provider_id": "i-05d2313e6b9a42b16"},
        {"provider_type": "azure", "provider_id": generate_uuid()},
        {"provider_type": "gcp", "provider_id": generate_uuid()},
        {"provider_type": "ibm", "provider_id": generate_uuid()},
        #
        # canonical_facts_version = 1
        #
        {
            "canonical_facts_version": 1,
            "is_virtual": True,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "alibaba",
            "provider_id": generate_uuid(),
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": True,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "aws",
            "provider_id": "i-05d2313e6b9a42b16",
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": True,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "azure",
            "provider_id": generate_uuid(),
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": True,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "gcp",
            "provider_id": generate_uuid(),
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": True,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "ibm",
            "provider_id": generate_uuid(),
        },
    ),
)
def test_valid_providers(canonical_facts):
    validated_host = CanonicalFactsSchema().load(canonical_facts)

    assert validated_host["provider_id"] == canonical_facts.get("provider_id")
    assert validated_host["provider_type"] == canonical_facts.get("provider_type")


@pytest.mark.parametrize(
    "canonical_facts",
    (
        #
        # canonical_facts_version = 0
        #
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
        {"provider_type": "aws", "provider_id": "\t"},  # invalid provider_id (tab),
        #
        # canonical_facts_version = 1
        #
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "invalid",
            "provider_id": "i-05d2313e6b9a42b16",
        },  # invalid provider_type (value not in enum)
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_id": generate_uuid(),
        },  # missing provider_type
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "azure",
        },  # missing provider_id
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "aws",
            "provider_id": None,
        },  # invalid provider_id (None)
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": None,
            "provider_id": generate_uuid(),
        },  # invalid provider_type (None)
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "azure",
            "provider_id": "",
        },  # invalid provider_id (empty string)
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "aws",
            "provider_id": "  ",
        },  # invalid provider_id (blank space)
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "aws",
            "provider_id": "\t",
        },  # invalid provider_id (tab)
    ),
)
def test_invalid_providers(canonical_facts):
    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


@pytest.mark.parametrize(
    "canonical_facts",
    (
        #
        # canonical_facts_version = 0
        #
        {"ip_addresses": ["127.0.0.1"]},
        {"ip_addresses": ["1.2.3.4"]},
        {"ip_addresses": ["2001:db8:3333:4444:5555:6666:7777:8888"]},
        {"ip_addresses": ["::"]},
        {"ip_addresses": ["2001:db8::"]},
        #
        # canonical_facts_version = 1
        #
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "ip_addresses": ["127.0.0.1"],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "ip_addresses": ["1.2.3.4"],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "ip_addresses": ["2001:db8:3333:4444:5555:6666:7777:8888"],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "ip_addresses": ["::"],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "ip_addresses": ["2001:db8::"],
        },
    ),
)
def test_valid_ip_addresses(canonical_facts):
    CanonicalFactsSchema().load(canonical_facts)


@pytest.mark.parametrize(
    "canonical_facts",
    (
        #
        # canonical_facts_version = 0
        #
        {"ip_addresses": ["just_a_string"]},
        {"ip_addresses": ["1.2.3"]},
        {"ip_addresses": ["1.2.3.4.5"]},
        {"ip_addresses": ["1.2.256.0"]},
        {"ip_addresses": ["2001:db8:3333:4444:5555:6666:7777:8888:9999"]},
        {"ip_addresses": ["1111:2222:3333:4444:5555:6666:7777:gb8"]},
        #
        # canonical_facts_version = 1
        #
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "ip_addresses": ["just_a_string"],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "ip_addresses": ["1.2.3"],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "ip_addresses": ["1.2.3.4.5"],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "ip_addresses": ["1.2.256.0"],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "ip_addresses": ["2001:db8:3333:4444:5555:6666:7777:8888:9999"],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "ip_addresses": ["1111:2222:3333:4444:5555:6666:7777:gb8"],
        },
    ),
)
def test_invalid_ip_addresses(canonical_facts):
    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


@pytest.mark.parametrize(
    "canonical_facts",
    (
        {
            "canonical_facts_version": 0,
            "is_virtual": False,
            "mac_addresses": [ZERO_MAC_ADDRESS],
        },
        {
            "canonical_facts_version": 0,
            "is_virtual": False,
            "mac_addresses": [ZERO_MAC_ADDRESS, ZERO_MAC_ADDRESS],
        },
    ),
)
def test_zero_mac_address_only_v0(canonical_facts):
    #
    # For version 0 canonical facts, the zero mac address should be filtered out.
    # If the list is then empty it should proceed as though mac_addresses weren't provided.
    #
    validated_host = CanonicalFactsSchema().load(canonical_facts)
    assert "mac_addresses" not in validated_host


@pytest.mark.parametrize(
    "canonical_facts",
    (
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": [ZERO_MAC_ADDRESS],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": [ZERO_MAC_ADDRESS, ZERO_MAC_ADDRESS],
        },
    ),
)
def test_zero_mac_address_only_v1(canonical_facts):
    #
    # For version 1 canonical facts, the zero mac address should be filtered out.
    # If the list is then empty it should fail as though it was an empty list.
    #
    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


@pytest.mark.parametrize(
    "canonical_facts",
    (
        {
            "canonical_facts_version": 0,
            "mac_addresses": ["c2:00:d0:c8:61:01", ZERO_MAC_ADDRESS],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", ZERO_MAC_ADDRESS],
        },
        {
            "canonical_facts_version": 0,
            "mac_addresses": [ZERO_MAC_ADDRESS, "c2:00:d0:c8:61:01", ZERO_MAC_ADDRESS],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": [ZERO_MAC_ADDRESS, "c2:00:d0:c8:61:01", ZERO_MAC_ADDRESS],
        },
    ),
)
def test_zero_mac_address_filtered(canonical_facts):
    validated_host = CanonicalFactsSchema().load(canonical_facts)

    #
    # If the zero mac address isn't the only element in the list,
    # it should succeed but the zero mac addresses should be removed.
    #
    assert len(validated_host["mac_addresses"]) == 1
    assert "c2:00:d0:c8:61:01" in validated_host["mac_addresses"]


@pytest.mark.parametrize(
    "canonical_facts",
    (
        {
            "canonical_facts_version": 0,
            "mac_addresses": [ZERO_MAC_ADDRESS],
        },
        {
            "canonical_facts_version": 1,
            "mac_addresses": [ZERO_MAC_ADDRESS],
        },
        {
            "canonical_facts_version": 0,
            "mac_addresses": ["c2:00:d0:c8:61:01", ZERO_MAC_ADDRESS],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", ZERO_MAC_ADDRESS],
        },
        {
            "canonical_facts_version": 0,
            "mac_addresses": [ZERO_MAC_ADDRESS, "c2:00:d0:c8:61:01", ZERO_MAC_ADDRESS],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": [ZERO_MAC_ADDRESS, "c2:00:d0:c8:61:01", ZERO_MAC_ADDRESS],
        },
    ),
)
def test_zero_mac_address_warning(mocker, canonical_facts):
    mock_logger_warn = mocker.patch("app.models.logger.warning")

    with suppress(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)

    assert mock_logger_warn.call_count >= 1


def test_canonical_facts_v1_is_virtual_required():
    canonical_facts = {"canonical_facts_version": 1, "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"]}
    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


@pytest.mark.parametrize("is_virtual", (None, "", "XXX", 1))
def test_canonical_facts_v1_is_virtual_badvalues(is_virtual):
    canonical_facts = {
        "canonical_facts_version": 1,
        "is_virtual": is_virtual,
        "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
    }
    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


@pytest.mark.parametrize(
    "canonical_facts",
    (
        {
            "canonical_facts_version": 1,
            "is_virtual": True,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "ibm",
            "provider_id": generate_uuid(),
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": "True",
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
            "provider_type": "ibm",
            "provider_id": generate_uuid(),
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": False,
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
        },
        {
            "canonical_facts_version": 1,
            "is_virtual": "False",
            "mac_addresses": ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"],
        },
    ),
)
def test_canonical_facts_v1_is_virtual_goodvalues(canonical_facts):
    validated_host = CanonicalFactsSchema().load(canonical_facts)
    assert validated_host["is_virtual"] is True or validated_host["is_virtual"] is False


def test_canonical_facts_v1_mac_addresses_required():
    canonical_facts = {"canonical_facts_version": 1, "is_virtual": False}
    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


@pytest.mark.parametrize("mac_addresses", ([], (), "c2:00:d0:c8:61:01", ["XXX"]))
def test_canonical_facts_v1_mac_addresses_badvalues(mac_addresses):
    canonical_facts = {"canonical_facts_version": 1, "is_virtual": False, "mac_addresses": mac_addresses}
    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


@pytest.mark.parametrize("mac_addresses", (["c2:00:d0:c8:61:01"], ["c2:00:d0:c8:61:01", "aa:bb:cc:dd:ee:ff"]))
def test_canonical_facts_v1_mac_addresses_goodvalues(mac_addresses):
    canonical_facts = {"canonical_facts_version": 1, "is_virtual": False, "mac_addresses": mac_addresses}
    CanonicalFactsSchema().load(canonical_facts)


def test_canonical_facts_v1_provider_required_for_virtual():
    canonical_facts = {"canonical_facts_version": 1, "is_virtual": True, "mac_addresses": ["c2:00:d0:c8:61:01"]}
    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


def test_canonical_facts_v1_noprovider_when_notvirtual():
    canonical_facts = {
        "canonical_facts_version": 1,
        "is_virtual": False,
        "mac_addresses": ["c2:00:d0:c8:61:01"],
        "provider_type": "ibm",
        "provider_id": generate_uuid(),
    }
    with pytest.raises(MarshmallowValidationError):
        CanonicalFactsSchema().load(canonical_facts)


def test_create_delete_group_happy(db_create_group, db_get_group_by_id, db_delete_group):
    group_name = "Host Group 1"

    # Verify that the group is created successfully
    created_group = db_create_group(group_name)
    assert db_get_group_by_id(created_group.id).name == group_name

    # Verify that the same group is deleted successfully
    db_delete_group(created_group.id)
    assert db_get_group_by_id(created_group.id) is None


def test_create_group_no_name(db_create_group):
    # Make sure we can't create a group with an empty name

    with pytest.raises(ValidationException):
        db_create_group(None)


def test_create_group_existing_name_diff_org(db_create_group, db_get_group_by_id):
    # Make sure we can't create two groups with the same name in the same org
    group_name = "TestGroup_diff_org"

    group1 = db_create_group(group_name)
    assert db_get_group_by_id(group1.id).name == group_name

    diff_identity = deepcopy(SYSTEM_IDENTITY)
    diff_identity["org_id"] = "diff_id"
    diff_identity["account"] = "diff_id"

    group2 = db_create_group(group_name, diff_identity)

    assert db_get_group_by_id(group2.id).name == group_name


def test_create_group_existing_name_same_org(db_create_group):
    # Make sure we can't create two groups with the same name in the same org
    group_name = "TestGroup"
    db_create_group(group_name)
    with pytest.raises(IntegrityError):
        db_create_group(group_name)


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
    created_group = db_create_group(group_name)
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


@pytest.mark.parametrize(
    "data",
    [
        {"name": ""},  # Name cannot be blank
        {"name": "a" * 256},  # Name must be 255 chars or less
        {"host_ids": ["asdf", "foobar"]},  # Host IDs must be in UUID format
        {"foo": "bar"},  # Field does not exist
    ],
)
def test_group_schema_validation(data):
    with pytest.raises(MarshmallowValidationError):
        InputGroupSchema().load(data)


def test_create_default_staleness_culling(db_create_staleness_culling, db_get_staleness_culling):
    acc_st_cull = db_create_staleness_culling()

    created_acc_st_cull = db_get_staleness_culling(acc_st_cull.org_id)

    assert created_acc_st_cull
    assert created_acc_st_cull.conventional_time_to_stale == acc_st_cull.conventional_time_to_stale
    assert created_acc_st_cull.conventional_time_to_stale_warning == acc_st_cull.conventional_time_to_stale_warning
    assert created_acc_st_cull.conventional_time_to_delete == acc_st_cull.conventional_time_to_delete
    assert created_acc_st_cull.immutable_time_to_stale == acc_st_cull.immutable_time_to_stale
    assert created_acc_st_cull.immutable_time_to_stale_warning == acc_st_cull.immutable_time_to_stale_warning
    assert created_acc_st_cull.immutable_time_to_delete == acc_st_cull.immutable_time_to_delete


def test_create_staleness_culling(db_create_staleness_culling, db_get_staleness_culling):
    acc_st_cull = db_create_staleness_culling(
        conventional_time_to_stale=2 * 86400,
        conventional_time_to_stale_warning=4 * 86400,
        conventional_time_to_delete=20 * 86400,
    )

    created_acc_st_cull = db_get_staleness_culling(acc_st_cull.org_id)
    assert created_acc_st_cull
    assert created_acc_st_cull.conventional_time_to_stale == acc_st_cull.conventional_time_to_stale
    assert created_acc_st_cull.conventional_time_to_stale_warning == acc_st_cull.conventional_time_to_stale_warning
    assert created_acc_st_cull.conventional_time_to_delete == acc_st_cull.conventional_time_to_delete


def test_delete_staleness_culling(db_create_staleness_culling, db_delete_staleness_culling, db_get_staleness_culling):
    acc_st_cull = db_create_staleness_culling()

    created_acc_st_cull = db_get_staleness_culling(acc_st_cull.org_id)
    assert created_acc_st_cull
    db_delete_staleness_culling(created_acc_st_cull.org_id)
    assert not db_get_staleness_culling(acc_st_cull.org_id)


def test_create_host_validate_staleness(db_create_host, db_get_host):
    host_data = {
        "canonical_facts": {"subscription_manager_id": generate_uuid()},
        "stale_timestamp": now(),
        "reporter": "test_reporter",
    }

    created_host = db_create_host(SYSTEM_IDENTITY, extra_data=host_data)
    staleness_timestamps = _create_staleness_timestamps_values(created_host, created_host.org_id)
    retrieved_host = db_get_host(created_host.id)

    assert retrieved_host.stale_timestamp == staleness_timestamps["stale_timestamp"]
    assert retrieved_host.stale_warning_timestamp == staleness_timestamps["stale_warning_timestamp"]
    assert retrieved_host.deletion_timestamp == staleness_timestamps["culled_timestamp"]
    assert retrieved_host.reporter == host_data["reporter"]


def test_create_host_with_canonical_facts(db_create_host_custom_canonical_facts, db_get_host):
    canonical_facts = {
        "insights_id": generate_uuid(),
        "subscription_manager_id": generate_uuid(),
        "satellite_id": generate_uuid(),
        "fqdn": "test.fqdn",
        "bios_uuid": generate_uuid(),
        "ip_addresses": ["192.168.1.1"],
        "mac_addresses": ["00:00:00:00:00:00"],
        "provider_id": "test_provider",
        "provider_type": "test_provider_type",
    }

    host_data = {"canonical_facts": canonical_facts, **canonical_facts}

    created_host = db_create_host_custom_canonical_facts(SYSTEM_IDENTITY, extra_data=host_data)
    retrieved_host = db_get_host(created_host.id)
    assert retrieved_host.canonical_facts == host_data["canonical_facts"]
    assert retrieved_host.insights_id == uuid.UUID(host_data["insights_id"])
    assert retrieved_host.subscription_manager_id == host_data["subscription_manager_id"]
    assert retrieved_host.satellite_id == host_data["satellite_id"]
    assert retrieved_host.fqdn == host_data["fqdn"]
    assert retrieved_host.bios_uuid == host_data["bios_uuid"]
    assert retrieved_host.ip_addresses == host_data["ip_addresses"]
    assert retrieved_host.mac_addresses == host_data["mac_addresses"]
    assert retrieved_host.provider_id == host_data["provider_id"]
    assert retrieved_host.provider_type == host_data["provider_type"]


def test_create_host_with_missing_canonical_facts(db_create_host_custom_canonical_facts, db_get_host):
    canonical_facts = {
        "insights_id": generate_uuid(),
        "subscription_manager_id": generate_uuid(),
        "satellite_id": generate_uuid(),
        "fqdn": "test.fqdn",
        "bios_uuid": generate_uuid(),
        "provider_id": "test_provider",
        "provider_type": "test_provider_type",
    }

    host_data = {"canonical_facts": canonical_facts, **canonical_facts}

    created_host = db_create_host_custom_canonical_facts(SYSTEM_IDENTITY, extra_data=host_data)
    retrieved_host = db_get_host(created_host.id)
    assert retrieved_host.canonical_facts == host_data["canonical_facts"]
    assert retrieved_host.insights_id == uuid.UUID(host_data["insights_id"])
    assert retrieved_host.subscription_manager_id == host_data["subscription_manager_id"]
    assert retrieved_host.satellite_id == host_data["satellite_id"]
    assert retrieved_host.fqdn == host_data["fqdn"]
    assert retrieved_host.bios_uuid == host_data["bios_uuid"]
    assert retrieved_host.provider_id == host_data["provider_id"]
    assert retrieved_host.provider_type == host_data["provider_type"]
    assert retrieved_host.ip_addresses is None
    assert retrieved_host.mac_addresses is None


def test_create_host_rhsm_only_sets_far_future_timestamps(db_create_host):
    """Test that creating a host with only rhsm-system-profile-bridge reporter sets far-future staleness timestamps."""
    stale_timestamp = datetime.now() + timedelta(days=1)

    input_host = Host(
        {"subscription_manager_id": generate_uuid()},
        display_name="display_name",
        reporter="rhsm-system-profile-bridge",
        stale_timestamp=stale_timestamp,
        org_id=USER_IDENTITY["org_id"],
    )
    created_host = db_create_host(host=input_host)

    # Check that main staleness timestamps are set to far future
    assert created_host.stale_timestamp == FAR_FUTURE_STALE_TIMESTAMP
    assert created_host.stale_warning_timestamp == FAR_FUTURE_STALE_TIMESTAMP
    assert created_host.deletion_timestamp == FAR_FUTURE_STALE_TIMESTAMP

    # Check per_reporter_staleness
    assert "rhsm-system-profile-bridge" in created_host.per_reporter_staleness
    prs = created_host.per_reporter_staleness["rhsm-system-profile-bridge"]
    assert prs["stale_timestamp"] == FAR_FUTURE_STALE_TIMESTAMP.isoformat()
    assert prs["stale_warning_timestamp"] == FAR_FUTURE_STALE_TIMESTAMP.isoformat()
    assert prs["culled_timestamp"] == FAR_FUTURE_STALE_TIMESTAMP.isoformat()


def test_host_with_rhsm_and_other_reporters_normal_behavior(db_create_host, models_datetime_mock):
    """Test that hosts with rhsm-system-profile-bridge AND other reporters behave normally."""
    stale_timestamp = models_datetime_mock + timedelta(days=1)

    input_host = Host(
        {"subscription_manager_id": generate_uuid()},
        display_name="display_name",
        reporter="puptoo",
        stale_timestamp=stale_timestamp,
        org_id=USER_IDENTITY["org_id"],
    )

    created_host = db_create_host(host=input_host)

    # Should NOT have far-future timestamps since it has multiple reporters
    assert created_host.stale_timestamp != FAR_FUTURE_STALE_TIMESTAMP

    # Update per_reporter_staleness for rhsm-system-profile-bridge - should behave normally
    created_host._update_per_reporter_staleness("rhsm-system-profile-bridge")

    # Should still not have far-future timestamps
    prs = created_host.per_reporter_staleness["rhsm-system-profile-bridge"]
    assert datetime.fromisoformat(prs["stale_timestamp"]) != FAR_FUTURE_STALE_TIMESTAMP


def test_create_host_static_system_profile(db_create_host):
    """Test creating a HostStaticSystemProfile record"""
    # Create a host first
    created_host = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
            "display_name": "test_host_for_static_profile",
        },
    )

    # Create static system profile data
    system_profile_data = {
        "org_id": created_host.org_id,
        "host_id": created_host.id,
        "arch": "x86_64",
        "basearch": "x86_64",
        "bios_vendor": "Dell Inc.",
        "bios_version": "2.15.0",
        "cloud_provider": "aws",
        "cores_per_socket": 4,
        "cpu_model": "Intel(R) Xeon(R) CPU E5-2686 v4 @ 2.30GHz",
        "host_type": "edge",
        "infrastructure_type": "virtual",
        "infrastructure_vendor": "aws",
        "insights_client_version": "3.1.7",
        "is_marketplace": False,
        "katello_agent_running": False,
        "number_of_cpus": 8,
        "number_of_sockets": 2,
        "operating_system": {"name": "RHEL", "major": 9, "minor": 1},
        "os_kernel_version": "5.14.0",
        "os_release": "Red Hat Enterprise Linux 9.1",
        "satellite_managed": False,
        "system_update_method": "yum",
        "threads_per_core": 2,
    }

    # Create the static system profile
    static_profile = HostStaticSystemProfile(**system_profile_data)
    db.session.add(static_profile)
    db.session.commit()

    # Verify the record was created
    retrieved_profile = (
        db.session.query(HostStaticSystemProfile)
        .filter_by(org_id=created_host.org_id, host_id=created_host.id)
        .first()
    )

    assert retrieved_profile is not None
    assert retrieved_profile.org_id == created_host.org_id
    assert retrieved_profile.host_id == created_host.id
    assert retrieved_profile.arch == "x86_64"
    assert retrieved_profile.bios_vendor == "Dell Inc."
    assert retrieved_profile.cores_per_socket == 4
    assert retrieved_profile.number_of_cpus == 8
    assert retrieved_profile.operating_system == {"name": "RHEL", "major": 9, "minor": 1}


def test_create_host_static_system_profile_minimal(db_create_host):
    """Test creating a HostStaticSystemProfile with minimal required data"""
    # Create a host first
    created_host = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
            "display_name": "test_host_minimal",
        },
    )

    # Create with only required fields
    minimal_data = {
        "org_id": created_host.org_id,
        "host_id": created_host.id,
    }

    static_profile = HostStaticSystemProfile(**minimal_data)
    db.session.add(static_profile)
    db.session.commit()

    # Verify the record was created
    retrieved_profile = (
        db.session.query(HostStaticSystemProfile)
        .filter_by(org_id=created_host.org_id, host_id=created_host.id)
        .first()
    )

    assert retrieved_profile is not None
    assert retrieved_profile.org_id == created_host.org_id
    assert retrieved_profile.host_id == created_host.id


def test_host_static_system_profile_validation_errors():
    """Test validation errors for HostStaticSystemProfile"""
    # Test missing org_id
    with pytest.raises(ValidationException, match="System org_id cannot be null"):
        HostStaticSystemProfile(org_id=None, host_id=generate_uuid())

    # Test missing host_id
    with pytest.raises(ValidationException, match="System host_id cannot be null"):
        HostStaticSystemProfile(org_id=USER_IDENTITY["org_id"], host_id=None)

    # Test empty org_id
    with pytest.raises(ValidationException, match="System org_id cannot be null"):
        HostStaticSystemProfile(org_id="", host_id=generate_uuid())


@pytest.mark.parametrize(
    "field,value",
    [
        ("cores_per_socket", -1),
        ("cores_per_socket", 2147483648),  # Max int + 1
        ("number_of_cpus", -1),
        ("number_of_cpus", 2147483648),
        ("number_of_sockets", -1),
        ("number_of_sockets", 2147483648),
        ("threads_per_core", -1),
        ("threads_per_core", 2147483648),
    ],
)
def test_host_static_system_profile_check_constraints(db_create_host, field, value):
    """Test check constraints on integer fields"""
    created_host = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
            "display_name": "test_host_constraints",
        },
    )

    data = {
        "org_id": created_host.org_id,
        "host_id": created_host.id,
        field: value,
    }

    static_profile = HostStaticSystemProfile(**data)
    db.session.add(static_profile)
    if value == -1:
        with pytest.raises(IntegrityError):
            db.session.commit()
    else:
        with pytest.raises(DataError):
            db.session.commit()


def test_update_host_static_system_profile(db_create_host):
    """Test updating a HostStaticSystemProfile record"""
    # Create a host first
    created_host = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
            "display_name": "test_host_update",
        },
    )

    # Create initial static system profile
    initial_data = {
        "org_id": created_host.org_id,
        "host_id": created_host.id,
        "arch": "x86_64",
        "number_of_cpus": 4,
        "host_type": "edge",
        "system_update_method": "yum",
    }

    static_profile = HostStaticSystemProfile(**initial_data)
    db.session.add(static_profile)
    db.session.commit()

    # Update the record
    static_profile.arch = "aarch64"
    static_profile.number_of_cpus = 8
    static_profile.host_type = "host"
    static_profile.system_update_method = "dnf"
    static_profile.bios_vendor = "Updated Vendor"
    db.session.commit()

    # Verify the updates
    retrieved_profile = (
        db.session.query(HostStaticSystemProfile)
        .filter_by(org_id=created_host.org_id, host_id=created_host.id)
        .first()
    )

    assert retrieved_profile.arch == "aarch64"
    assert retrieved_profile.number_of_cpus == 8
    assert retrieved_profile.host_type == "host"
    assert retrieved_profile.system_update_method == "dnf"
    assert retrieved_profile.bios_vendor == "Updated Vendor"


def test_delete_host_static_system_profile(db_create_host):
    """Test deleting a HostStaticSystemProfile record"""
    # Create a host first
    created_host = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
            "display_name": "test_host_delete",
        },
    )

    # Create static system profile
    static_profile_data = {
        "org_id": created_host.org_id,
        "host_id": created_host.id,
        "arch": "x86_64",
        "number_of_cpus": 4,
    }

    static_profile = HostStaticSystemProfile(**static_profile_data)
    db.session.add(static_profile)
    db.session.commit()

    # Verify it exists
    retrieved_profile = (
        db.session.query(HostStaticSystemProfile)
        .filter_by(org_id=created_host.org_id, host_id=created_host.id)
        .first()
    )
    assert retrieved_profile is not None

    # Delete the record
    db.session.delete(static_profile)
    db.session.commit()

    # Verify it's gone
    retrieved_profile = (
        db.session.query(HostStaticSystemProfile)
        .filter_by(org_id=created_host.org_id, host_id=created_host.id)
        .first()
    )
    assert retrieved_profile is None


def test_host_static_system_profile_complex_data_types(db_create_host):
    """Test HostStaticSystemProfile with complex JSONB and array data types"""
    # Create a host first
    created_host = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
            "display_name": "test_host_complex_data",
        },
    )

    # Create static system profile with complex data
    complex_data = {
        "org_id": created_host.org_id,
        "host_id": created_host.id,
        "operating_system": {
            "name": "Red Hat Enterprise Linux Server",
            "major": 9,
            "minor": 1,
            "version_id": "9.1",
        },
        "bootc_status": {
            "booted": {
                "image": "quay.io/example/bootc:latest",
                "incompatible": False,
                "pinned": False,
            },
            "rollback": {
                "image": "quay.io/example/bootc:previous",
                "incompatible": False,
                "pinned": True,
            },
        },
        "disk_devices": [
            {
                "device": "/dev/sda",
                "label": "disk1",
                "mount_point": "/",
                "type": "disk",
            },
            {
                "device": "/dev/sdb",
                "label": "disk2",
                "mount_point": "/home",
                "type": "disk",
            },
        ],
        "enabled_services": ["sshd", "chronyd", "NetworkManager"],
        "gpg_pubkeys": ["key1", "key2", "key3"],
        "public_dns": ["8.8.8.8", "8.8.4.4"],
        "public_ipv4_addresses": ["203.0.113.1", "203.0.113.2"],
        "conversions": {"activity": "Conversion completed successfully"},
        "rhsm": {
            "version": "1.29.26",
            "auto_registration": False,
        },
        "yum_repos": [
            {
                "id": "rhel-9-appstream-rpms",
                "name": "Red Hat Enterprise Linux 9 - AppStream",
                "enabled": True,
            }
        ],
    }

    static_profile = HostStaticSystemProfile(**complex_data)
    db.session.add(static_profile)
    db.session.commit()

    # Verify the complex data was stored correctly
    retrieved_profile = (
        db.session.query(HostStaticSystemProfile)
        .filter_by(org_id=created_host.org_id, host_id=created_host.id)
        .first()
    )

    assert retrieved_profile.operating_system["name"] == "Red Hat Enterprise Linux Server"
    assert retrieved_profile.operating_system["major"] == 9
    assert retrieved_profile.bootc_status["booted"]["image"] == "quay.io/example/bootc:latest"
    assert len(retrieved_profile.disk_devices) == 2
    assert retrieved_profile.disk_devices[0]["device"] == "/dev/sda"
    assert "sshd" in retrieved_profile.enabled_services
    assert "8.8.8.8" in retrieved_profile.public_dns
    assert retrieved_profile.rhsm["version"] == "1.29.26"
    assert len(retrieved_profile.yum_repos) == 1
    assert retrieved_profile.yum_repos[0]["id"] == "rhel-9-appstream-rpms"


def test_add_dynamic_profile(db_create_host):
    """
    Tests adding a HostDynamicSystemProfile record using a sample data dictionary.
    """
    host = db_create_host()
    sample_data = get_sample_profile_data(host.org_id, host.id)
    profile = HostDynamicSystemProfile(**sample_data)

    db.session.add(profile)
    db.session.commit()

    retrieved = db.session.query(HostDynamicSystemProfile).filter_by(org_id=host.org_id, host_id=host.id).one()

    assert retrieved is not None
    for key, value in sample_data.items():
        assert getattr(retrieved, key) == value


def test_delete_dynamic_profile(db_create_host):
    """
    Tests deleting a HostDynamicSystemProfile record from the database.
    """
    host = db_create_host()
    profile = HostDynamicSystemProfile(**get_sample_profile_data(host.org_id, host.id))
    db.session.add(profile)
    db.session.commit()

    db.session.delete(profile)
    db.session.commit()

    retrieved = db.session.query(HostDynamicSystemProfile).filter_by(org_id=host.org_id, host_id=host.id).one_or_none()

    assert retrieved is None


def test_update_dynamic_profile(db_create_host):
    """
    Tests updating a HostDynamicSystemProfile record in the database.
    """
    host = db_create_host()
    profile = HostDynamicSystemProfile(**get_sample_profile_data(host.org_id, host.id))
    db.session.add(profile)
    db.session.commit()

    profile.insights_egg_version = "2.1.4"
    db.session.commit()

    retrieved = db.session.query(HostDynamicSystemProfile).filter_by(org_id=host.org_id, host_id=host.id).one()

    assert retrieved.insights_egg_version == "2.1.4"


def test_add_profile_fails_without_parent_host():
    """
    Tests that adding a profile fails with an IntegrityError if the parent Host
    does not exist, validating the foreign key constraint.
    """

    org_id = "org-failure-case"
    non_existent_host_id = uuid.uuid4()
    sample_data = get_sample_profile_data(org_id, non_existent_host_id)

    profile = HostDynamicSystemProfile(org_id=org_id, host_id=non_existent_host_id)
    for key, value in sample_data.items():
        if key not in ["org_id", "host_id"]:
            setattr(profile, key, value)

    with pytest.raises(IntegrityError) as excinfo:
        db.session.add(profile)
        db.session.commit()

    db.session.rollback()

    assert "fk_system_profiles_dynamic_hosts" in str(excinfo.value)


def test_dynamic_profile_missing_required_field(db_create_host):
    """
    Tests that creating a HostDynamicSystemProfile with missing required fields raises an exception.
    """
    host = db_create_host()
    sample_data = get_sample_profile_data(host.org_id, host.id)
    # Remove a required field (e.g., 'org_id')
    sample_data.pop("org_id", None)
    with pytest.raises(TypeError):
        _ = HostDynamicSystemProfile(**sample_data)


def test_dynamic_profile_incorrect_type(db_create_host):
    """
    Tests that creating a HostDynamicSystemProfile with incorrect data types raises an exception.
    """
    host = db_create_host()
    sample_data = get_sample_profile_data(host.org_id, host.id)
    # Set a field to an incorrect type (e.g., 'host_id' as a string instead of UUID)
    sample_data["host_id"] = "not-a-uuid"
    profile = HostDynamicSystemProfile(**sample_data)
    db.session.add(profile)
    with pytest.raises(DataError):
        db.session.commit()
    db.session.rollback()


def test_dynamic_profile_constraint_violation(db_create_host):
    """
    Tests that creating a HostDynamicSystemProfile with duplicate primary key raises an exception.
    """
    host = db_create_host()
    sample_data = get_sample_profile_data(host.org_id, host.id)
    profile1 = HostDynamicSystemProfile(**sample_data)
    db.session.add(profile1)
    db.session.commit()
    # Attempt to add another profile with the same primary key
    profile2 = HostDynamicSystemProfile(**sample_data)
    db.session.add(profile2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
