import uuid

import pytest
from marshmallow import ValidationError

from app import db
from app.models import _deserialize_tags
from app.models import Host
from app.models import HostSchema

"""
These tests are for testing the db model classes outside of the api.
"""


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


def test_create_host_with_canonical_facts_as_None(flask_app_fixture):
    # Test to make sure canonical facts that are None or '' do
    # not get inserted into the db
    invalid_canonical_facts = {"fqdn": None, "insights_id": ""}
    valid_canonical_facts = {"bios_uuid": "1234"}

    host_dict = {**invalid_canonical_facts, **valid_canonical_facts}

    host = Host.from_json(host_dict)

    assert valid_canonical_facts == host.canonical_facts


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


def test_host_schema_valid_tags(flask_app_fixture):
    tags = ["Sat/env=prod", "AWS/env=ci"]
    host = {"fqdn": "fred.flintstone.com", "display_name": "display_name", "account": "00102", "tags": tags}
    validated_host = HostSchema(strict=True).load(host)

    assert validated_host.data["tags"] == tags

    tags = ["Sat/env", "AWS/env"]
    host = {"fqdn": "fred.flintstone.com", "display_name": "display_name", "account": "00102", "tags": tags}
    validated_host = HostSchema(strict=True).load(host)

    assert validated_host.data["tags"] == tags


def test_host_schema_invalid_tags(flask_app_fixture):
    tags = ["Sat/"]
    host = {"fqdn": "fred.flintstone.com", "display_name": "display_name", "account": "00102", "tags": tags}
    with pytest.raises(ValidationError) as excinfo:
        _ = HostSchema(strict=True).load(host)

    assert "Sat/" in str(excinfo.value)

    tags = ["Sat/env=prod", "bad_tag"]
    host = {"fqdn": "fred.flintstone.com", "display_name": "display_name", "account": "00102", "tags": tags}
    with pytest.raises(ValidationError) as excinfo:
        _ = HostSchema(strict=True).load(host)

    assert "bad_tag" in str(excinfo.value)


def test_tag_deserialization(flask_app_fixture):
    tags = ["Sat/env=prod", "Sat/env=test", "Sat/geo=somewhere", "AWS/env=ci", "AWS/env"]
    expected_tags = {"Sat": {"env": ["prod", "test"], "geo": ["somewhere"]}, "AWS": {"env": ["", "ci"]}}
    deserialized_tags = _deserialize_tags(tags)

    assert len(deserialized_tags["Sat"]["env"]) == len(expected_tags["Sat"]["env"])
    assert len(deserialized_tags["Sat"]["geo"]) == len(expected_tags["Sat"]["geo"])
    assert len(deserialized_tags["AWS"]["env"]) == len(expected_tags["AWS"]["env"])


def test_create_host_with_tags(flask_app_fixture):
    tags = ["Sat/env=prod", "AWS/env=ci"]
    host = Host({"fqdn": "fred.flintstone.com"}, display_name="display_name", account="00102", tags=tags)
    db.session.add(host)
    db.session.commit()

    assert host.tags == tags

    # Tags aren't required to have a value
    tags = ["Sat/env", "AWS/env"]
    host = Host({"fqdn": "fred.flintstone.com"}, display_name="display_name", account="00102", tags=tags)
    db.session.add(host)
    db.session.commit()

    assert host.tags == tags
