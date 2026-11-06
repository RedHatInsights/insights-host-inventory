from datetime import UTC
from datetime import datetime
from datetime import timedelta
from random import choice
from unittest.mock import Mock
from unittest.mock import patch
from uuid import UUID
from uuid import uuid4

import pytest
from marshmallow import ValidationError

from app.config import DEFAULT_INSIGHTS_ID
from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.culling import Conditions
from app.exceptions import InputFormatException
from app.exceptions import ValidationException
from app.models import Host
from app.models import HostSchema
from app.serialization import _deserialize_canonical_facts
from app.serialization import _deserialize_facts
from app.serialization import _serialize_datetime
from app.serialization import _serialize_per_reporter_staleness
from app.serialization import deserialize_canonical_facts
from app.serialization import deserialize_host
from app.serialization import serialize_canonical_facts
from app.serialization import serialize_facts
from app.serialization import serialize_host
from app.serialization import serialize_host_system_profile
from app.serialization import serialize_uuid
from app.staleness_serialization import get_staleness_timestamps
from app.staleness_serialization import get_sys_default_staleness
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import add_seconds
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import now
from tests.helpers.test_utils import timestamp_to_str


def _format_uuid_with_hyphens(uuid_):
    return str(uuid_)


def _format_uuid_without_hyphens(uuid_):
    return uuid_.hex


def _randomly_formatted_uuid(uuid_):
    transformation = choice((_format_uuid_without_hyphens, _format_uuid_with_hyphens))
    return transformation(uuid_)


def _randomly_formatted_sequence(seq):
    transformation = choice((list, tuple))
    return transformation(seq)


def test_with_only_required_fields_serialization_deserialize_host_compound(subtests, flask_app):
    with flask_app.app.app_context():
        org_id = "some org_id"
        stale_timestamp = now()
        reporter = "puptoo"
        canonical_facts = {"subscription_manager_id": generate_uuid()}

        with subtests.test(schema=HostSchema):
            host = deserialize_host(
                {
                    "org_id": org_id,
                    "stale_timestamp": stale_timestamp.isoformat(),
                    "reporter": reporter,
                    **canonical_facts,
                }
            )

            assert Host is type(host)
            serialized_canonical = serialize_canonical_facts(host)
            for key, value in canonical_facts.items():
                assert value == serialized_canonical.get(key)
            assert host.display_name is None
            assert host.ansible_host is None
            assert org_id == host.org_id
            assert reporter == host.reporter
            assert host.facts == {}
            assert host.tags == {}
            # system_profile_facts no longer exists - check normalized tables instead
            assert host.static_system_profile is None
            assert host.dynamic_system_profile is None


def test_with_invalid_input_serialization_deserialize_host_compound(subtests, flask_app):
    with flask_app.app.app_context():
        stale_timestamp = now().isoformat()
        inputs = (
            {},
            {"org_id": "some org_id", "stale_timestamp": stale_timestamp},
            {"org_id": "some org_id", "reporter": "some reporter"},
            {"stale_timestamp": stale_timestamp, "reporter": "some reporter"},
            {"org_id": "", "stale_timestamp": stale_timestamp, "reporter": "some reporter"},
            {
                "org_id": "some org_id that's wayyyyyyyyyy too long",
                "fqdn": "some fqdn",
                "stale_timestamp": stale_timestamp,
                "reporter": "some reporter",
            },
            {"org_id": "some org_id", "fqdn": None, "stale_timestamp": stale_timestamp, "reporter": "some reporter"},
            {"org_id": "some org_id", "fqdn": "", "stale_timestamp": stale_timestamp, "reporter": "some reporter"},
            {
                "org_id": "some org_id",
                "fqdn": "x" * 256,
                "stale_timestamp": stale_timestamp,
                "reporter": "some reporter",
            },
            {
                "org_id": "some org_id",
                "fqdn": "some fqdn",
                "facts": {"some ns": {"some key": "some value"}},
                "stale_timestamp": stale_timestamp,
                "reporter": "some reporter",
            },
            {
                "org_id": "some org_id",
                "fqdn": "some fqdn",
                "mac_addresses": ["00:11:22:33:44:55:66:77:88:99:aa:bb:cc:dd:ee:ff:00:11:22:33:44"],
                "stale_timestamp": stale_timestamp,
                "reporter": "some reporter",
            },
            {
                "org_id": "some org_id",
                "fqdn": "some fqdn",
                "tags": [{"namespace": "namespace", "value": "value"}],
                "stale_timestamp": stale_timestamp,
                "reporter": "some reporter",
            },
            {
                "org_id": "some org_id",
                "insights_id": str(uuid4()) + str(uuid4()),  # longer than 36 chars
                "tags": [{"namespace": "namespace", "value": "value"}],
                "stale_timestamp": stale_timestamp,
                "reporter": "some reporter",
            },
            {
                "org_id": str(uuid4()) + str(uuid4()),  # longer than 36 chars
                "tags": [{"namespace": "namespace", "value": "value"}],
                "stale_timestamp": stale_timestamp,
                "reporter": "some reporter",
            },
            {
                "org_id": "some org_id",
                "bios_uuid": "01234567890abcd",  # test shorter than 36 chars
                "tags": [{"namespace": "namespace", "value": "value"}],
                "stale_timestamp": stale_timestamp,
                "reporter": "some reporter",
            },
            {
                "org_id": "some org_id",
                "subscription_manager_id": str(uuid4()).replace(
                    "-", ""
                ),  # uuid witout dashes not allowed for dedup control
                "stale_timestamp": stale_timestamp,
                "reporter": "some reporter",
            },
            {
                "org_id": "some org_id",
                "satellite_id": None,  # test for null
                "stale_timestamp": stale_timestamp,
                "reporter": "some reporter",
            },
        )
        for inp in inputs:
            with subtests.test(input=inp):
                with pytest.raises(ValidationException) as context:
                    deserialize_host(inp)

                    expected_errors = HostSchema().validate(inp)
                    assert str(expected_errors) == str(context.value)


def test_with_all_common_fields_serialization_deserialize_host_compound(subtests, flask_app):
    with flask_app.app.app_context():
        canonical_facts = {
            "insights_id": str(uuid4()),
            "subscription_manager_id": str(uuid4()),
            "satellite_id": str(uuid4()),
            "bios_uuid": str(uuid4()),
            "ip_addresses": ["10.10.0.1", "10.0.0.2"],
            "fqdn": "some fqdn",
            "mac_addresses": ["c2:00:d0:c8:61:01"],
        }
        unchanged_input = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "org_id": "some org_id",
            "reporter": "puptoo",
        }
        stale_timestamp = now()
        full_input = {
            **canonical_facts,
            **unchanged_input,
            "stale_timestamp": stale_timestamp.isoformat(),
            "facts": [
                {"namespace": "some namespace", "facts": {"some key": "some value"}},
                {"namespace": "another namespace", "facts": {"another key": "another value"}},
            ],
            "system_profile": {
                "number_of_cpus": 1,
                "number_of_sockets": 2,
                "cores_per_socket": 3,
                "system_memory_bytes": 4,
            },
        }

        with subtests.test(schema=HostSchema):
            actual = deserialize_host(full_input)
            expected = {
                **canonical_facts,
                **unchanged_input,
                "facts": {item["namespace"]: item["facts"] for item in full_input["facts"]},
            }

            assert Host is type(actual)
            for key, value in expected.items():
                assert value == getattr(actual, key)


@patch("app.models.schemas.Host")
@patch("app.serialization._deserialize_tags")
@patch("app.serialization._deserialize_facts")
@patch("app.serialization._deserialize_canonical_facts")
def test_with_all_fields_serialization_deserialize_host_mocked(
    deserialize_canonical_facts, deserialize_facts, deserialize_tags, host, flask_app
):
    with flask_app.app.app_context():
        host_input = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "some acct",
            "org_id": "3340851",
            "insights_id": str(uuid4()),
            "subscription_manager_id": str(uuid4()),
            "satellite_id": str(uuid4()),
            "bios_uuid": str(uuid4()),
            "ip_addresses": ["10.10.0.1", "10.0.0.2"],
            "fqdn": "some fqdn",
            "mac_addresses": ["c2:00:d0:c8:61:01"],
            "provider_id": "i-05d2313e6b9a42b16",
            "provider_type": "aws",
            "facts": {
                "some namespace": {"some key": "some value"},
                "another namespace": {"another key": "another value"},
            },
            "tags": {
                "some namespace": {"some key": ["some value", "another value"], "another key": ["value"]},
                "another namespace": {"key": ["value"]},
            },
            "system_profile": {
                "number_of_cpus": 1,
                "number_of_sockets": 2,
                "cores_per_socket": 3,
                "system_memory_bytes": 4,
            },
            "stale_timestamp": now().isoformat(),
            "reporter": "some reporter",
            "groups": [
                {
                    "id": str(uuid4()),
                    "org_id": "3340851",
                    "account": "some acct",
                    "name": "group 1",
                    "created": now().isoformat(),
                    "updated": now().isoformat(),
                },
                {
                    "id": str(uuid4()),
                    "org_id": "3340851",
                    "account": "some acct",
                    "name": "group 2",
                    "created": now().isoformat(),
                    "updated": now().isoformat(),
                },
            ],
            "openshift_cluster_id": str(uuid4()),
        }
        host_schema = Mock(**{"return_value.load.return_value": host_input, "build_model": HostSchema.build_model})
        result = deserialize_host({}, host_schema)
        assert host.return_value == result

        deserialize_canonical_facts.assert_called_once_with(host_input)
        deserialize_facts.assert_called_once_with(host_input["facts"])
        deserialize_tags.assert_called_once_with(host_input["tags"])
        host.assert_called_once_with(
            display_name=host_input["display_name"],
            ansible_host=host_input["ansible_host"],
            account=host_input["account"],
            org_id=host_input["org_id"],
            facts=deserialize_facts.return_value,
            tags=deserialize_tags.return_value,
            tags_alt=[],
            system_profile_facts=host_input["system_profile"],
            reporter=host_input["reporter"],
            groups=host_input["groups"],
            insights_id=host_input.get("insights_id"),
            subscription_manager_id=host_input.get("subscription_manager_id"),
            satellite_id=host_input.get("satellite_id"),
            fqdn=host_input.get("fqdn"),
            bios_uuid=host_input.get("bios_uuid"),
            ip_addresses=host_input.get("ip_addresses"),
            mac_addresses=host_input.get("mac_addresses"),
            provider_id=host_input.get("provider_id"),
            provider_type=host_input.get("provider_type"),
            openshift_cluster_id=host_input["openshift_cluster_id"],
        )


@patch("app.models.schemas.Host")
@patch("app.serialization._deserialize_tags")
@patch("app.serialization._deserialize_facts")
@patch("app.serialization._deserialize_canonical_facts")
def test_without_facts_serialization_deserialize_host_mocked(
    deserialize_canonical_facts, deserialize_facts, deserialize_tags, host, flask_app
):
    with flask_app.app.app_context():
        host_input = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "some account",
            "org_id": "3340851",
            "tags": {
                "some namespace": {"some key": ["some value", "another value"], "another key": ["value"]},
                "another namespace": {"key": ["value"]},
            },
            "system_profile": {
                "number_of_cpus": 1,
                "number_of_sockets": 2,
                "cores_per_socket": 3,
                "system_memory_bytes": 4,
            },
            "stale_timestamp": now().isoformat(),
            "reporter": "some reporter",
            "groups": [
                {
                    "id": str(uuid4()),
                    "org_id": "3340851",
                    "account": "some acct",
                    "name": "group 1",
                    "created": now().isoformat(),
                    "updated": now().isoformat(),
                },
                {
                    "id": str(uuid4()),
                    "org_id": "3340851",
                    "account": "some acct",
                    "name": "group 2",
                    "created": now().isoformat(),
                    "updated": now().isoformat(),
                },
            ],
            "openshift_cluster_id": str(uuid4()),
        }
        host_schema = Mock(**{"return_value.load.return_value": host_input, "build_model": HostSchema.build_model})

        result = deserialize_host({}, host_schema)
        assert host.return_value == result

        deserialize_canonical_facts.assert_called_once_with(host_input)
        deserialize_facts.assert_called_once_with(None)
        deserialize_tags.assert_called_once_with(host_input["tags"])
        host.assert_called_once_with(
            display_name=host_input["display_name"],
            ansible_host=host_input["ansible_host"],
            account=host_input["account"],
            org_id=host_input["org_id"],
            facts=deserialize_facts.return_value,
            tags=deserialize_tags.return_value,
            tags_alt=[],
            system_profile_facts=host_input["system_profile"],
            reporter=host_input["reporter"],
            groups=host_input["groups"],
            insights_id=host_input.get("insights_id"),
            subscription_manager_id=host_input.get("subscription_manager_id"),
            satellite_id=host_input.get("satellite_id"),
            fqdn=host_input.get("fqdn"),
            bios_uuid=host_input.get("bios_uuid"),
            ip_addresses=host_input.get("ip_addresses"),
            mac_addresses=host_input.get("mac_addresses"),
            provider_id=host_input.get("provider_id"),
            provider_type=host_input.get("provider_type"),
            openshift_cluster_id=host_input["openshift_cluster_id"],
        )


@patch("app.models.schemas.Host")
@patch("app.serialization._deserialize_tags")
@patch("app.serialization._deserialize_facts")
@patch("app.serialization._deserialize_canonical_facts")
def test_without_display_name_serialization_deserialize_host_mocked(
    deserialize_canonical_facts, deserialize_facts, deserialize_tags, host, flask_app
):
    with flask_app.app.app_context():
        host_input = {
            "ansible_host": "some ansible host",
            "account": "some account",
            "org_id": "3340851",
            "facts": {
                "some namespace": {"some key": "some value"},
                "another namespace": {"another key": "another value"},
            },
            "tags": [
                {"namespace": "NS1", "key": "key1", "value": "value1"},
                {"namespace": "NS2", "key": "key2", "value": "value2"},
            ],
            "system_profile": {
                "number_of_cpus": 1,
                "number_of_sockets": 2,
                "cores_per_socket": 3,
                "system_memory_bytes": 4,
            },
            "stale_timestamp": now().isoformat(),
            "reporter": "some reporter",
            "groups": [
                {
                    "id": str(uuid4()),
                    "org_id": "3340851",
                    "account": "some acct",
                    "name": "group 1",
                    "created": now().isoformat(),
                    "updated": now().isoformat(),
                },
                {
                    "id": str(uuid4()),
                    "org_id": "3340851",
                    "account": "some acct",
                    "name": "group 2",
                    "created": now().isoformat(),
                    "updated": now().isoformat(),
                },
            ],
            "openshift_cluster_id": str(uuid4()),
        }
        host_schema = Mock(**{"return_value.load.return_value": host_input, "build_model": HostSchema.build_model})

        result = deserialize_host({}, host_schema)
        assert host.return_value == result

        deserialize_canonical_facts.assert_called_once_with(host_input)
        deserialize_facts.assert_called_once_with(host_input["facts"])
        deserialize_tags.assert_called_once_with(host_input["tags"])
        host.assert_called_once_with(
            display_name=None,
            ansible_host=host_input["ansible_host"],
            account=host_input["account"],
            org_id=host_input["org_id"],
            facts=deserialize_facts.return_value,
            tags=deserialize_tags.return_value,
            tags_alt=[],
            system_profile_facts=host_input["system_profile"],
            reporter=host_input["reporter"],
            groups=host_input["groups"],
            insights_id=host_input.get("insights_id"),
            subscription_manager_id=host_input.get("subscription_manager_id"),
            satellite_id=host_input.get("satellite_id"),
            fqdn=host_input.get("fqdn"),
            bios_uuid=host_input.get("bios_uuid"),
            ip_addresses=host_input.get("ip_addresses"),
            mac_addresses=host_input.get("mac_addresses"),
            provider_id=host_input.get("provider_id"),
            provider_type=host_input.get("provider_type"),
            openshift_cluster_id=host_input["openshift_cluster_id"],
        )


@patch("app.models.schemas.Host")
@patch("app.serialization._deserialize_tags")
@patch("app.serialization._deserialize_facts")
@patch("app.serialization._deserialize_canonical_facts")
def test_without_system_profile_serialization_deserialize_host_mocked(
    deserialize_canonical_facts, deserialize_facts, deserialize_tags, host, flask_app
):
    with flask_app.app.app_context():
        host_input = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "some account",
            "org_id": "3340851",
            "tags": [
                {"namespace": "NS1", "key": "key1", "value": "value1"},
                {"namespace": "NS2", "key": "key2", "value": "value2"},
            ],
            "facts": {
                "some namespace": {"some key": "some value"},
                "another namespace": {"another key": "another value"},
            },
            "stale_timestamp": now().isoformat(),
            "reporter": "some reporter",
            "groups": [
                {
                    "id": str(uuid4()),
                    "org_id": "3340851",
                    "account": "some acct",
                    "name": "group 1",
                    "created": now().isoformat(),
                    "updated": now().isoformat(),
                },
                {
                    "id": str(uuid4()),
                    "org_id": "3340851",
                    "account": "some acct",
                    "name": "group 2",
                    "created": now().isoformat(),
                    "updated": now().isoformat(),
                },
            ],
            "openshift_cluster_id": str(uuid4()),
        }
        host_schema = Mock(**{"return_value.load.return_value": host_input, "build_model": HostSchema.build_model})

        result = deserialize_host({}, host_schema)
        assert host.return_value == result

        deserialize_canonical_facts.assert_called_once_with(host_input)
        deserialize_facts.assert_called_once_with(host_input["facts"])
        deserialize_tags.assert_called_once_with(host_input["tags"])
        host.assert_called_once_with(
            display_name=host_input["display_name"],
            ansible_host=host_input["ansible_host"],
            account=host_input["account"],
            org_id=host_input["org_id"],
            facts=deserialize_facts.return_value,
            tags=deserialize_tags.return_value,
            tags_alt=[],
            system_profile_facts={},
            reporter=host_input["reporter"],
            groups=host_input["groups"],
            insights_id=host_input.get("insights_id"),
            subscription_manager_id=host_input.get("subscription_manager_id"),
            satellite_id=host_input.get("satellite_id"),
            fqdn=host_input.get("fqdn"),
            bios_uuid=host_input.get("bios_uuid"),
            ip_addresses=host_input.get("ip_addresses"),
            mac_addresses=host_input.get("mac_addresses"),
            provider_id=host_input.get("provider_id"),
            provider_type=host_input.get("provider_type"),
            openshift_cluster_id=host_input["openshift_cluster_id"],
        )


@patch("app.models.schemas.Host")
@patch("app.serialization._deserialize_tags")
@patch("app.serialization._deserialize_facts")
@patch("app.serialization._deserialize_canonical_facts")
def test_without_groups_serialization_deserialize_host_mocked(
    deserialize_canonical_facts, deserialize_facts, deserialize_tags, host, flask_app
):
    with flask_app.app.app_context():
        host_input = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "some account",
            "org_id": "3340851",
            "tags": [
                {"namespace": "NS1", "key": "key1", "value": "value1"},
                {"namespace": "NS2", "key": "key2", "value": "value2"},
            ],
            "system_profile": {
                "number_of_cpus": 1,
                "number_of_sockets": 2,
                "cores_per_socket": 3,
                "system_memory_bytes": 4,
            },
            "facts": {
                "some namespace": {"some key": "some value"},
                "another namespace": {"another key": "another value"},
            },
            "stale_timestamp": now().isoformat(),
            "reporter": "some reporter",
            "openshift_cluster_id": str(uuid4()),
        }
        host_schema = Mock(**{"return_value.load.return_value": host_input, "build_model": HostSchema.build_model})

        result = deserialize_host({}, host_schema)
        assert host.return_value == result

        deserialize_canonical_facts.assert_called_once_with(host_input)
        deserialize_facts.assert_called_once_with(host_input["facts"])
        deserialize_tags.assert_called_once_with(host_input["tags"])
        host.assert_called_once_with(
            display_name=host_input["display_name"],
            ansible_host=host_input["ansible_host"],
            account=host_input["account"],
            org_id=host_input["org_id"],
            facts=deserialize_facts.return_value,
            tags=deserialize_tags.return_value,
            tags_alt=[],
            system_profile_facts=host_input["system_profile"],
            reporter=host_input["reporter"],
            groups=[],
            insights_id=host_input.get("insights_id"),
            subscription_manager_id=host_input.get("subscription_manager_id"),
            satellite_id=host_input.get("satellite_id"),
            fqdn=host_input.get("fqdn"),
            bios_uuid=host_input.get("bios_uuid"),
            ip_addresses=host_input.get("ip_addresses"),
            mac_addresses=host_input.get("mac_addresses"),
            provider_id=host_input.get("provider_id"),
            provider_type=host_input.get("provider_type"),
            openshift_cluster_id=host_input["openshift_cluster_id"],
        )


@patch("app.models.schemas.Host")
@patch("app.serialization._deserialize_tags")
@patch("app.serialization._deserialize_facts")
@patch("app.serialization._deserialize_canonical_facts")
def test_invalid_host_error_serialization_deserialize_host_mocked(
    deserialize_canonical_facts, deserialize_facts, deserialize_tags, host, flask_app
):
    with flask_app.app.app_context():
        data = {"field_1": "data_1"}
        messages = {"field_1": "Invalid value.", "field_2": "Missing required field."}
        caught_exception = ValidationError(messages)
        caught_exception.data = data
        host_schema = Mock(**{"return_value.load.side_effect": caught_exception})

        with pytest.raises(ValidationException) as raises_context:
            deserialize_host({}, host_schema)

        raised_exception = raises_context.value

        assert str(caught_exception.messages) in str(raised_exception)

        deserialize_canonical_facts.assert_not_called()
        deserialize_facts.assert_not_called()
        deserialize_tags.assert_not_called()
        host.assert_not_called()

        host_schema.return_value.load.return_value.get.assert_not_called()


def test_with_all_fields_serialization_serialize_host_compound(flask_app):
    with flask_app.app.app_context():
        canonical_facts = {
            "insights_id": generate_uuid(),
            "subscription_manager_id": generate_uuid(),
            "satellite_id": generate_uuid(),
            "bios_uuid": generate_uuid(),
            "ip_addresses": ["10.10.0.1", "10.0.0.2"],
            "fqdn": "some fqdn",
            "mac_addresses": ["c2:00:d0:c8:61:01"],
            "provider_id": "i-05d2313e6b9a42b16",
            "provider_type": "aws",
        }
        unchanged_data = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "some acct",
            "org_id": "3340851",
            "reporter": "insights",
            "groups": [],
            "openshift_cluster_id": str(uuid4()),
        }
        host_init_data = {
            **canonical_facts,
            **unchanged_data,
            "facts": {
                "some namespace": {"some key": "some value"},
                "another namespace": {"another key": "another value"},
            },
            "tags": {
                "some namespace": {"some key": ["some value", "another value"], "another key": ["value"]},
                "another namespace": {"key": ["value"]},
            },
        }
        host = Host(**host_init_data)

        host_attr_data = {
            "id": uuid4(),
            "created_on": now(),
            "modified_on": now(),
            "last_check_in": now(),
            "per_reporter_staleness": host.per_reporter_staleness,
        }
        for k, v in host_attr_data.items():
            setattr(host, k, v)

        staleness = get_sys_default_staleness()
        actual = serialize_host(host, staleness, False, ("tags",))

        expected = {
            **canonical_facts,
            **unchanged_data,
            "workspace": None,
            "facts": [
                {"namespace": namespace, "facts": facts} for namespace, facts in host_init_data["facts"].items()
            ],
            "tags": [
                {"namespace": namespace, "key": key, "value": value}
                for namespace, ns_tags in host_init_data["tags"].items()
                for key, values in ns_tags.items()
                for value in values
            ],
            "id": str(host_attr_data["id"]),
            "created": timestamp_to_str(host_attr_data["created_on"]),
            "updated": timestamp_to_str(host_attr_data["modified_on"]),
            "last_check_in": timestamp_to_str(host_attr_data["last_check_in"]),
            "stale_timestamp": timestamp_to_str(
                add_seconds(host_attr_data["last_check_in"], CONVENTIONAL_TIME_TO_STALE_SECONDS)
            ),
            "stale_warning_timestamp": timestamp_to_str(
                add_seconds(host_attr_data["last_check_in"], CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS)
            ),
            "culled_timestamp": timestamp_to_str(
                add_seconds(host_attr_data["last_check_in"], CONVENTIONAL_TIME_TO_DELETE_SECONDS)
            ),
            "per_reporter_staleness": _serialize_per_reporter_staleness(host, staleness),
        }
        expected["insights_id"] = str(expected["insights_id"])
        expected["subscription_manager_id"] = str(expected["subscription_manager_id"])
        expected["satellite_id"] = str(expected["satellite_id"])
        expected["bios_uuid"] = str(expected["bios_uuid"])

        assert expected == actual


def test_workspace_field_serialization(flask_app):
    with flask_app.app.app_context():
        group_data = [{"id": "11111111-1111-1111-1111-111111111111", "name": "test-workspace", "ungrouped": False}]
        host = Host(
            org_id="some org_id",
            subscription_manager_id=generate_uuid(),
            reporter="puptoo",
            groups=group_data,
        )
        host.id = uuid4()
        host.created_on = now()
        host.modified_on = now()
        host.last_check_in = now()

        staleness = get_sys_default_staleness()

        actual = serialize_host(host, staleness, False)
        assert actual["workspace"] == group_data[0]
        assert actual["groups"] == group_data

        actual_mq = serialize_host(host, staleness, True)
        assert actual_mq["workspace"]["id"] == group_data[0]["id"]
        assert actual_mq["workspace"]["name"] == group_data[0]["name"]

        empty_host = Host(
            org_id="some org_id",
            subscription_manager_id=generate_uuid(),
            reporter="puptoo",
            groups=[],
        )
        empty_host.id = uuid4()
        empty_host.created_on = now()
        empty_host.modified_on = now()
        empty_host.last_check_in = now()

        actual_empty = serialize_host(empty_host, staleness, False)
        assert actual_empty["workspace"] is None
        assert actual_empty["groups"] == []

        actual_empty_mq = serialize_host(empty_host, staleness, True)
        assert actual_empty_mq["workspace"] is None
        assert actual_empty_mq["groups"] == []


def test_with_only_required_fields_serialization_serialize_host_compound(subtests, flask_app):
    with flask_app.app.app_context():
        for group_data in ({"groups": None}, {"groups": []}, {}):
            with subtests.test(group_data=group_data):
                unchanged_data = {
                    "display_name": None,
                    "org_id": "some org_id",
                    "account": None,
                    "reporter": "yupana",
                }
                host_init_data = {
                    "subscription_manager_id": generate_uuid(),
                    **unchanged_data,
                    "facts": {},
                }
                host = Host(**host_init_data)

                host_attr_data = {
                    "id": uuid4(),
                    "created_on": now(),
                    "modified_on": now(),
                    "last_check_in": now(),
                    "per_reporter_staleness": host.per_reporter_staleness,
                    **group_data,
                }
                for k, v in host_attr_data.items():
                    setattr(host, k, v)

                staleness = get_sys_default_staleness()
                actual = serialize_host(host, staleness, False, ("tags",))
                expected = {
                    "insights_id": DEFAULT_INSIGHTS_ID,
                    "fqdn": None,
                    "satellite_id": None,
                    "bios_uuid": None,
                    "ip_addresses": None,
                    "mac_addresses": None,
                    "ansible_host": None,
                    "provider_id": None,
                    "provider_type": None,
                    "openshift_cluster_id": None,
                    "subscription_manager_id": str(host_init_data.get("subscription_manager_id")),
                    **unchanged_data,
                    "facts": [],
                    "groups": [],
                    "workspace": None,
                    "tags": [],
                    "id": str(host_attr_data["id"]),
                    "created": timestamp_to_str(host_attr_data["created_on"]),
                    "updated": timestamp_to_str(host_attr_data["modified_on"]),
                    "last_check_in": timestamp_to_str(host_attr_data["last_check_in"]),
                    "stale_timestamp": timestamp_to_str(
                        add_seconds(host_attr_data["last_check_in"], CONVENTIONAL_TIME_TO_STALE_SECONDS)
                    ),
                    "stale_warning_timestamp": timestamp_to_str(
                        add_seconds(host_attr_data["last_check_in"], CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS)
                    ),
                    "culled_timestamp": timestamp_to_str(
                        add_seconds(host_attr_data["last_check_in"], CONVENTIONAL_TIME_TO_DELETE_SECONDS)
                    ),
                    "per_reporter_staleness": _serialize_per_reporter_staleness(host, staleness),
                }

                assert expected == actual


def test_serialize_host_lifecycle_fields_from_last_check_in(flask_app):
    """Serialize API lifecycle timestamps from last_check_in + org offsets (compute-on-read)."""
    with flask_app.app.app_context():
        ref = datetime(2019, 6, 15, 8, 30, 0, tzinfo=UTC)
        host = Host(
            subscription_manager_id=generate_uuid(),
            facts={},
            reporter="test-reporter",
            org_id=USER_IDENTITY["org_id"],
        )
        host.id = uuid4()
        host.created_on = now()
        host.modified_on = now()
        host.last_check_in = ref

        staleness = get_sys_default_staleness()
        expected = get_staleness_timestamps(host, staleness)

        expected_state = Conditions.find_host_state(
            expected["stale_timestamp"],
            expected["stale_warning_timestamp"],
        )
        serialized = serialize_host(host, staleness, False, additional_fields=("state",))
        assert serialized["stale_timestamp"] == timestamp_to_str(expected["stale_timestamp"])
        assert serialized["stale_warning_timestamp"] == timestamp_to_str(expected["stale_warning_timestamp"])
        assert serialized["culled_timestamp"] == timestamp_to_str(expected["culled_timestamp"])
        assert serialized["state"] == expected_state


@patch("app.serialization._serialize_tags")
@patch("app.serialization.serialize_facts")
@patch("app.serialization.serialize_canonical_facts")
def test_with_all_fields_serialization_serialize_host_mocked(
    serialize_canonical_facts, serialize_facts, serialize_tags, flask_app
):
    insights_id = generate_uuid()
    fqdn = "some fqdn"
    with flask_app.app.app_context():
        canonical_facts = {"insights_id": insights_id, "fqdn": fqdn}
        serialized_canonical_facts = {
            "insights_id": str(insights_id),
            "fqdn": fqdn,
        }
        serialize_canonical_facts.return_value = serialized_canonical_facts
        facts = [
            {"namespace": "some namespace", "facts": {"some key": "some value"}},
            {"namespace": "another namespace", "facts": {"another key": "another value"}},
        ]
        serialize_facts.return_value = facts
        serialize_tags.return_value = [
            {"namespace": "some namespace", "key": "some key", "value": "some value"},
            {"namespace": "some namespace", "key": "some key", "value": "another value"},
            {"namespace": "some namespace", "key": "another key", "value": "value"},
            {"namespace": "another namespace", "key": "key", "value": "value"},
        ]
        unchanged_data = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "some acct",
            "org_id": "3340851",
            "reporter": "some reporter",
            "groups": [],
            "openshift_cluster_id": str(uuid4()),
        }
        host_init_data = {
            **canonical_facts,
            **unchanged_data,
            "facts": facts,
            "tags": {
                "some namespace": {"some key": ["some value", "another value"], "another key": ["value"]},
                "another namespace": {"key": ["value"]},
            },
        }
        host = Host(**host_init_data)

        host_attr_data = {
            "id": uuid4(),
            "created_on": now(),
            "modified_on": now(),
            "last_check_in": now(),
            "per_reporter_staleness": host.per_reporter_staleness,
        }
        for k, v in host_attr_data.items():
            setattr(host, k, v)

        staleness = get_sys_default_staleness()
        actual = serialize_host(host, staleness, False, ("tags",))
        expected = {
            **serialized_canonical_facts,
            **unchanged_data,
            "workspace": None,
            "facts": serialize_facts.return_value,
            "tags": serialize_tags.return_value,
            "id": str(host_attr_data["id"]),
            "created": timestamp_to_str(host_attr_data["created_on"]),
            "updated": timestamp_to_str(host_attr_data["modified_on"]),
            "last_check_in": timestamp_to_str(host_attr_data["last_check_in"]),
            "stale_timestamp": timestamp_to_str(
                host_attr_data["last_check_in"] + timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_SECONDS)
            ),
            "stale_warning_timestamp": timestamp_to_str(
                host_attr_data["last_check_in"] + timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS)
            ),
            "culled_timestamp": timestamp_to_str(
                host_attr_data["last_check_in"] + timedelta(seconds=CONVENTIONAL_TIME_TO_DELETE_SECONDS)
            ),
            "per_reporter_staleness": _serialize_per_reporter_staleness(host, staleness),
        }

        assert expected == actual

        # It is called twice, because we have 2 test cases
        serialize_canonical_facts.assert_called_with(host)
        serialize_facts.assert_called_with(host_init_data["facts"])
        serialize_tags.assert_called_with(host_init_data["tags"])


def test_non_empty_profile_is_not_changed_serialization_serialize_host_system_profile(flask_app):
    with flask_app.app.app_context():
        system_profile_facts = {
            "number_of_cpus": 1,
            "number_of_sockets": 2,
            "cores_per_socket": 3,
            "system_memory_bytes": 4,
        }
        host = Host(
            subscription_manager_id=generate_uuid(),
            display_name="some display name",
            system_profile_facts=system_profile_facts,
            reporter="yupana",
            org_id=USER_IDENTITY["org_id"],
        )
        host.id = uuid4()

        actual = serialize_host_system_profile(host)
        expected = {"id": str(host.id), "system_profile": system_profile_facts}
        assert expected == actual


def test_empty_profile_is_empty_dict_serialization_serialize_host_system_profile(flask_app):
    with flask_app.app.app_context():
        host = Host(
            subscription_manager_id=generate_uuid(),
            display_name="some display name",
            reporter="yupana",
            org_id=USER_IDENTITY["org_id"],
        )
        host.id = uuid4()
        # No system profile data - should serialize to empty system_profile

        actual = serialize_host_system_profile(host)
        expected = {"id": str(host.id), "system_profile": {}}
        assert expected == actual


def test_values_are_stored_unchanged_serialization_deserialize_canonical_facts():
    input = {
        "insights_id": _randomly_formatted_uuid(uuid4()),
        "subscription_manager_id": _randomly_formatted_uuid(uuid4()),
        "satellite_id": _randomly_formatted_uuid(uuid4()),
        "bios_uuid": _randomly_formatted_uuid(uuid4()),
        "ip_addresses": _randomly_formatted_sequence(("10.10.0.1", "10.10.0.2")),
        "fqdn": "some fqdn",
        "mac_addresses": _randomly_formatted_sequence(("c2:00:d0:c8:61:01",)),
    }
    result = _deserialize_canonical_facts(input)
    assert result == input


def test_unknown_fields_are_rejected_serialization_deserialize_canonical_facts():
    canonical_facts = {
        "insights_id": str(uuid4()),
        "subscription_manager_id": str(uuid4()),
        "satellite_id": str(uuid4()),
        "bios_uuid": str(uuid4()),
        "ip_addresses": ("10.10.0.1", "10.10.0.2"),
        "fqdn": "some fqdn",
        "mac_addresses": ["c2:00:d0:c8:61:01"],
    }
    input = {**canonical_facts, "unknown": "something"}
    result = _deserialize_canonical_facts(input)
    assert result == canonical_facts


def test_empty_fields_are_rejected_serialization_deserialize_canonical_facts():
    canonical_facts = {"fqdn": "some fqdn"}
    input = {**canonical_facts, "insights_id": "", "ip_addresses": [], "mac_addresses": tuple()}
    result = _deserialize_canonical_facts(input)
    assert result == canonical_facts


def test_empty_fields_are_not_rejected_when_all_is_passed_serialization_deserialize_canonical_facts():
    canonical_facts = {"fqdn": "some fqdn", "insights_id": str(uuid4())}
    expected = {
        **canonical_facts,
        "ip_addresses": None,
        "mac_addresses": None,
        "bios_uuid": None,
        "provider_id": None,
        "provider_type": None,
        "satellite_id": None,
        "subscription_manager_id": None,
    }
    result = deserialize_canonical_facts(canonical_facts, all=True)
    assert result == expected


def test_contains_all_values_unchanged_serialization_serialize_canonical_facts():
    canonical_facts = {
        "insights_id": str(uuid4()),
        "subscription_manager_id": str(uuid4()),
        "satellite_id": str(uuid4()),
        "bios_uuid": str(uuid4()),
        "ip_addresses": ("10.10.0.1", "10.10.0.2"),
        "fqdn": "some fqdn",
        "mac_addresses": ("c2:00:d0:c8:61:01",),
        "provider_id": "i-05d2313e6b9a42b16",
        "provider_type": "aws",
    }
    assert canonical_facts == serialize_canonical_facts(minimal_host(**canonical_facts))


def test_missing_fields_are_filled_with_none_serialization_serialize_canonical_facts():
    canonical_fact_fields = (
        "insights_id",
        "subscription_manager_id",
        "satellite_id",
        "bios_uuid",
        "ip_addresses",
        "fqdn",
        "mac_addresses",
        "provider_id",
        "provider_type",
    )
    expected = {field: None for field in canonical_fact_fields}
    # insights_id should never be None - it defaults to zero UUID
    expected["insights_id"] = DEFAULT_INSIGHTS_ID
    assert expected == serialize_canonical_facts({})


def test_non_empty_namespaces_become_dict_items_serialization_deserialize_facts():
    input = [
        {"namespace": "first namespace", "facts": {"first key": "first value", "second key": "second value"}},
        {"namespace": "second namespace", "facts": {"third key": "third value"}},
    ]
    assert {item["namespace"]: item["facts"] for item in input} == _deserialize_facts(input)


def test_empty_namespaces_remain_unchanged_serialization_deserialize_facts(subtests):
    for empty_facts in ({}, None):
        with subtests.test(empty_facts=empty_facts):
            input = [
                {"namespace": "first namespace", "facts": {"first key": "first value"}},
                {"namespace": "second namespace", "facts": empty_facts},
            ]
            assert {item["namespace"]: item["facts"] for item in input} == _deserialize_facts(input)


def test_duplicate_namespaces_are_merged_serialization_deserialize_facts():
    input = [
        {"namespace": "first namespace", "facts": {"first key": "first value", "second key": "second value"}},
        {"namespace": "second namespace", "facts": {"third key": "third value"}},
        {"namespace": "first namespace", "facts": {"first key": "fourth value"}},
    ]
    actual = _deserialize_facts(input)
    expected = {
        "first namespace": {"first key": "fourth value", "second key": "second value"},
        "second namespace": {"third key": "third value"},
    }
    assert expected == actual


def test_none_becomes_empty_dict_serialization_deserialize_facts():
    assert _deserialize_facts(None) == {}


def test_missing_key_raises_exception_serialization_deserialize_facts(subtests):
    invalid_items = (
        {"spacename": "second namespace", "facts": {"second key": "second value"}},
        {"namespace": "second namespace", "fact": {"second key": "second value"}},
        {"namespace": "second namespace"},
        {},
    )
    for invalid_item in invalid_items:
        with subtests.test(invalid_item=invalid_item):
            input = [{"namespace": "first namespace", "facts": {"first key": "first value"}}, invalid_item]
            with pytest.raises(InputFormatException):
                _deserialize_facts(input)


def test_empty_dict_becomes_empty_list_serialization_serialize_facts():
    assert serialize_facts({}) == []


def test_non_empty_namespaces_become_list_of_dicts_serialization_serialize_facts():
    facts = {
        "first namespace": {"first key": "first value", "second key": "second value"},
        "second namespace": {"third key": "third value"},
    }
    assert [{"namespace": namespace, "facts": facts} for namespace, facts in facts.items()] == serialize_facts(facts)


def test_empty_namespaces_have_facts_as_empty_dicts_serialization_serialize_facts(subtests):
    for empty_value in {}, None:
        with subtests.test(empty_value=empty_value):
            facts = {
                "first namespace": empty_value or {},
                "second namespace": {"first key": "first value"},
            }
            assert [
                {"namespace": namespace, "facts": facts or {}} for namespace, facts in facts.items()
            ] == serialize_facts(facts)


def test_utc_timezone_is_used_serialization_serialize_datetime():
    _now = now()
    assert _now.isoformat() == _serialize_datetime(_now)


def test_iso_format_is_used_serialization_serialize_datetime():
    dt = datetime(2019, 7, 3, 1, 1, 4, 20647, UTC)
    assert _serialize_datetime(dt) == "2019-07-03T01:01:04.020647+00:00"


def test_uuid_has_hyphens_computed_serialization_serialize_uuid():
    u = uuid4()
    assert str(u) == serialize_uuid(u)


def test_uuid_has_hyphens_literal_serialization_serialize_uuid():
    u = "4950e534-bbef-4432-bde2-aa3dd2bd0a52"
    assert u == serialize_uuid(UUID(u))


def test_stale_timestamp_config_serialization_serialize_host_compound(subtests, flask_app):
    with flask_app.app.app_context():
        for stale_warning_offset_seconds, culled_offset_seconds in (
            (CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS, CONVENTIONAL_TIME_TO_DELETE_SECONDS),
        ):
            with subtests.test(
                stale_warning_offset_seconds=stale_warning_offset_seconds,
                culled_offset_seconds=culled_offset_seconds,
            ):
                host = Host(
                    subscription_manager_id=generate_uuid(),
                    facts={},
                    reporter="some reporter",
                    org_id=USER_IDENTITY["org_id"],
                )
                host.last_check_in = now() + timedelta(days=1)

                for k, v in (("id", uuid4()), ("created_on", now()), ("modified_on", now())):
                    setattr(host, k, v)

                staleness = get_sys_default_staleness()
                serialized = serialize_host(host, staleness, False)

                assert (
                    timestamp_to_str(add_seconds(host.last_check_in, stale_warning_offset_seconds))
                    == serialized["stale_warning_timestamp"]
                )
                assert (
                    timestamp_to_str(add_seconds(host.last_check_in, culled_offset_seconds))
                    == serialized["culled_timestamp"]
                )
