import uuid

import pytest
from marshmallow import ValidationError as MarshmallowValidationError

from app.models import HostSchema
from app.models import LimitedHost
from app.utils import Tag
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY


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
        "reporter": "test",
    }
    with pytest.raises(MarshmallowValidationError) as exception:
        HostSchema().load(host)

    error_messages = exception.value.normalized_messages()
    assert "tags" in error_messages
    assert error_messages["tags"] == {0: {"key": ["Missing data for required field."]}}


def test_tags_alt_deduplication_on_create():
    """tags_alt must never contain duplicate (namespace, key, value) entries."""
    # Simulate a reporter sending duplicate values in the tags list
    tags_with_dupes = {"ns1": {"key1": ["val1", "val1", "val2"], "key2": ["val3"]}}
    host = LimitedHost(
        account=USER_IDENTITY["account_number"],
        fqdn="dedup-test.example.com",
        tags=tags_with_dupes,
    )

    # Verify no duplicates in tags_alt
    tag_tuples = [(t["namespace"], t["key"], t.get("value")) for t in host.tags_alt]
    assert len(tag_tuples) == len(set(tag_tuples))
    assert ("ns1", "key1", "val1") in tag_tuples
    assert ("ns1", "key1", "val2") in tag_tuples
    assert ("ns1", "key2", "val3") in tag_tuples
    assert len(tag_tuples) == 3


def test_tags_alt_deduplication_on_update(db_create_host):
    """Updating tags must not introduce duplicates in tags or tags_alt."""
    host = db_create_host(extra_data={"tags": {"ns1": {"key1": ["val1"]}}})

    # Update with duplicates in the incoming data (via _update_tags, the public entry point)
    host._update_tags({"ns1": {"key1": ["val1", "val1", "val2"]}})

    # Verify tags_alt has no duplicates
    tag_tuples = [(t["namespace"], t["key"], t.get("value")) for t in host.tags_alt]
    assert len(tag_tuples) == len(set(tag_tuples))
    assert len(tag_tuples) == 2  # val1 + val2, no duplicate val1

    # Verify tags column also has no duplicate values
    assert host.tags["ns1"]["key1"] == ["val1", "val2"]


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
    existing_host = db_create_host(extra_data={"insights_id": insights_id, "display_name": "tagged", "tags": old_tags})

    assert existing_host.tags == old_tags
    assert existing_host.tags_alt == old_tags_alt

    # On update each namespace in the input host's tags should be updated.
    new_tags = Tag.create_nested_from_tags([Tag("Sat", "env", "ci"), Tag("AWS", "env", "prod")])
    new_tags_alt = Tag.create_flat_tags_from_structured([Tag("Sat", "env", "ci"), Tag("AWS", "env", "prod")])
    input_host = db_create_host(extra_data={"insights_id": insights_id, "display_name": "tagged", "tags": new_tags})

    existing_host.update(input_host)

    assert existing_host.tags == new_tags
    assert sorted(existing_host.tags_alt, key=lambda t: t["namespace"]) == sorted(
        new_tags_alt, key=lambda t: t["namespace"]
    )


def test_update_host_with_no_tags(db_create_host):
    insights_id = str(uuid.uuid4())
    old_tags = Tag("Sat", "env", "prod").to_nested()
    existing_host = db_create_host(extra_data={"insights_id": insights_id, "display_name": "tagged", "tags": old_tags})

    # Updating a host should not remove any existing tags if tags are missing from the input host
    input_host = db_create_host(extra_data={"insights_id": insights_id, "display_name": "tagged"})
    existing_host.update(input_host)

    assert existing_host.tags == old_tags
