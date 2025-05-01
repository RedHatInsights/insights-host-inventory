import uuid
from contextlib import suppress
from copy import deepcopy
from datetime import datetime
from datetime import timedelta
from unittest.mock import patch

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
from app.staleness_serialization import get_staleness_timestamps
from app.staleness_serialization import get_sys_default_staleness
from app.utils import Tag
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid
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

    existing_host = db_create_host(extra_data={"canonical_facts": {"fqdn": fqdn}, "display_name": None})

    # Clear the display_name
    existing_host.display_name = None
    db.session.commit()
    assert existing_host.display_name is None

    # Update the host
    expected_fqdn = "different.domain1.com"
    input_host = Host(
        {"fqdn": expected_fqdn},
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
            "canonical_facts": {"fqdn": "fred.flintstone.com"},
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
        org_id=USER_IDENTITY["org_id"],
    )
    db_create_host(host=host)

    assert isinstance(host.id, uuid.UUID)


def test_host_model_default_timestamps(db_create_host):
    host = Host(
        account=USER_IDENTITY["account_number"],
        canonical_facts={"fqdn": "fqdn"},
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
        canonical_facts={"fqdn": "fqdn"},
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
        canonical_facts={"fqdn": "fqdn"},
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
        "canonical_facts": {"fqdn": "fqdn"},
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


@pytest.mark.parametrize("with_last_check_in", [True, False])
def test_create_host_sets_per_reporter_staleness(mocker, db_create_host, models_datetime_mock, with_last_check_in):
    with (
        mocker.patch("app.serialization.get_flag_value", return_value=with_last_check_in),
        mocker.patch("app.models.get_flag_value", return_value=with_last_check_in),
        mocker.patch("app.staleness_serialization.get_flag_value", return_value=with_last_check_in),
    ):
        stale_timestamp = models_datetime_mock + timedelta(days=1)

        input_host = Host(
            {"fqdn": "fqdn"},
            display_name="display_name",
            reporter="puptoo",
            stale_timestamp=stale_timestamp,
            org_id=USER_IDENTITY["org_id"],
        )
        created_host = db_create_host(host=input_host)
        staleness = get_sys_default_staleness()
        st = staleness_timestamps()
        timestamps = get_staleness_timestamps(created_host, st, staleness)

        if with_last_check_in:
            assert created_host.per_reporter_staleness == {
                "puptoo": {
                    "last_check_in": models_datetime_mock.isoformat(),
                    "stale_timestamp": timestamps["stale_timestamp"].isoformat(),
                    "check_in_succeeded": True,
                    "culled_timestamp": timestamps["culled_timestamp"].isoformat(),
                    "stale_warning_timestamp": timestamps["stale_warning_timestamp"].isoformat(),
                }
            }
        else:
            assert created_host.per_reporter_staleness == {
                "puptoo": {
                    "last_check_in": models_datetime_mock.isoformat(),
                    "stale_timestamp": stale_timestamp.isoformat(),
                    "check_in_succeeded": True,
                }
            }


@pytest.mark.parametrize("with_last_check_in", [True, False])
def test_update_per_reporter_staleness(mocker, db_create_host, models_datetime_mock, with_last_check_in):
    with (
        mocker.patch("app.serialization.get_flag_value", return_value=with_last_check_in),
        mocker.patch("app.models.get_flag_value", return_value=with_last_check_in),
        mocker.patch("app.staleness_serialization.get_flag_value", return_value=with_last_check_in),
    ):
        puptoo_stale_timestamp = models_datetime_mock + timedelta(days=1)

        input_host = Host(
            {"fqdn": "fqdn"},
            display_name="display_name",
            reporter="puptoo",
            stale_timestamp=puptoo_stale_timestamp,
            org_id=USER_IDENTITY["org_id"],
        )

        existing_host = db_create_host(host=input_host)
        staleness = get_sys_default_staleness()
        st = staleness_timestamps()
        timestamps = get_staleness_timestamps(existing_host, st, staleness)

        if with_last_check_in:
            assert existing_host.per_reporter_staleness == {
                "puptoo": {
                    "last_check_in": models_datetime_mock.isoformat(),
                    "stale_timestamp": timestamps["stale_timestamp"].isoformat(),
                    "check_in_succeeded": True,
                    "culled_timestamp": timestamps["culled_timestamp"].isoformat(),
                    "stale_warning_timestamp": timestamps["stale_warning_timestamp"].isoformat(),
                }
            }
        else:
            assert existing_host.per_reporter_staleness == {
                "puptoo": {
                    "last_check_in": models_datetime_mock.isoformat(),
                    "stale_timestamp": puptoo_stale_timestamp.isoformat(),
                    "check_in_succeeded": True,
                }
            }

        puptoo_stale_timestamp += timedelta(days=1)

        update_host = Host(
            {"fqdn": "fqdn"},
            display_name="display_name",
            reporter="puptoo",
            stale_timestamp=puptoo_stale_timestamp,
            org_id=USER_IDENTITY["org_id"],
        )
        existing_host.update(update_host)

        # datetime will not change because the datetime.now() method is patched
        if with_last_check_in:
            assert existing_host.per_reporter_staleness == {
                "puptoo": {
                    "last_check_in": models_datetime_mock.isoformat(),
                    "stale_timestamp": timestamps["stale_timestamp"].isoformat(),
                    "check_in_succeeded": True,
                    "culled_timestamp": timestamps["culled_timestamp"].isoformat(),
                    "stale_warning_timestamp": timestamps["stale_warning_timestamp"].isoformat(),
                }
            }
        else:
            assert existing_host.per_reporter_staleness == {
                "puptoo": {
                    "last_check_in": models_datetime_mock.isoformat(),
                    "stale_timestamp": puptoo_stale_timestamp.isoformat(),
                    "check_in_succeeded": True,
                }
            }

        yupana_stale_timestamp = puptoo_stale_timestamp + timedelta(days=1)

        update_host = Host(
            {"fqdn": "fqdn"},
            display_name="display_name",
            reporter="yupana",
            stale_timestamp=yupana_stale_timestamp,
            org_id=USER_IDENTITY["org_id"],
        )
        existing_host.update(update_host)

        # datetime will not change because the datetime.now() method is patched
        if with_last_check_in:
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
        else:
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
    "new_reporter",
    ["satellite", "discovery"],
)
@pytest.mark.parametrize("with_last_check_in", [True, False])
def test_update_per_reporter_staleness_yupana_replacement(
    mocker, db_create_host, models_datetime_mock, new_reporter, with_last_check_in
):
    with (
        mocker.patch("app.serialization.get_flag_value", return_value=with_last_check_in),
        mocker.patch("app.models.get_flag_value", return_value=with_last_check_in),
        mocker.patch("app.staleness_serialization.get_flag_value", return_value=with_last_check_in),
    ):
        yupana_stale_timestamp = models_datetime_mock + timedelta(days=1)
        input_host = Host(
            {"fqdn": "fqdn"},
            display_name="display_name",
            reporter="yupana",
            stale_timestamp=yupana_stale_timestamp,
            org_id=USER_IDENTITY["org_id"],
        )
        existing_host = db_create_host(host=input_host)

        staleness = get_sys_default_staleness()
        st = staleness_timestamps()
        timestamps = get_staleness_timestamps(existing_host, st, staleness)
        if with_last_check_in:
            assert existing_host.per_reporter_staleness == {
                "yupana": {
                    "last_check_in": models_datetime_mock.isoformat(),
                    "stale_timestamp": timestamps["stale_timestamp"].isoformat(),
                    "check_in_succeeded": True,
                    "culled_timestamp": timestamps["culled_timestamp"].isoformat(),
                    "stale_warning_timestamp": timestamps["stale_warning_timestamp"].isoformat(),
                }
            }
        else:
            assert existing_host.per_reporter_staleness == {
                "yupana": {
                    "last_check_in": models_datetime_mock.isoformat(),
                    "stale_timestamp": yupana_stale_timestamp.isoformat(),
                    "check_in_succeeded": True,
                }
            }

        yupana_stale_timestamp += timedelta(days=1)

        update_host = Host(
            {"fqdn": "fqdn"},
            display_name="display_name",
            reporter=new_reporter,
            stale_timestamp=yupana_stale_timestamp,
            org_id=USER_IDENTITY["org_id"],
        )
        existing_host.update(update_host)

        # datetime will not change because the datetime.now() method is patched
        if with_last_check_in:
            assert existing_host.per_reporter_staleness == {
                new_reporter: {
                    "last_check_in": models_datetime_mock.isoformat(),
                    "stale_timestamp": timestamps["stale_timestamp"].isoformat(),
                    "check_in_succeeded": True,
                    "culled_timestamp": timestamps["culled_timestamp"].isoformat(),
                    "stale_warning_timestamp": timestamps["stale_warning_timestamp"].isoformat(),
                }
            }
        else:
            assert existing_host.per_reporter_staleness == {
                new_reporter: {
                    "last_check_in": models_datetime_mock.isoformat(),
                    "stale_timestamp": yupana_stale_timestamp.isoformat(),
                    "check_in_succeeded": True,
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


@pytest.mark.parametrize("mac_addresses", (None, [], (), "c2:00:d0:c8:61:01", ["XXX"]))
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
    with (
        patch("app.staleness_serialization.get_flag_value", return_value=True),
        patch("app.models.get_flag_value", return_value=True),
    ):
        host_data = {
            "canonical_facts": {"fqdn": "test.example.com"},
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
