from unittest.mock import Mock
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.exceptions import ValidationException
from app.models import Host
from app.models import HostSchema
from app.serialization import _deserialize_tags
from app.serialization import _deserialize_tags_dict
from app.serialization import _deserialize_tags_list
from app.serialization import deserialize_host
from app.utils import Tag
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import now


def _base_structured_to_filtered_test(structured_tags, expected_filtered_structured_tags, searchTerm):
    flat_tags = Tag.create_flat_tags_from_structured(structured_tags)
    expected_filtered_flat_tags = Tag.create_flat_tags_from_structured(expected_filtered_structured_tags)
    filtered_tags = Tag.filter_tags(flat_tags, searchTerm)
    assert len(filtered_tags) == len(expected_filtered_flat_tags)

    for i in range(len(filtered_tags)):
        assert filtered_tags[i]["namespace"] == expected_filtered_flat_tags[i]["namespace"]
        assert filtered_tags[i]["key"] == expected_filtered_flat_tags[i]["key"]
        assert filtered_tags[i]["value"] == expected_filtered_flat_tags[i]["value"]


def test_all_parts_tag_from_string():
    assert Tag.from_string("NS/key=value") == Tag("NS", "key", "value")


@pytest.mark.parametrize(
    "string_tag,expected",
    [
        ("NS/key=my/value", Tag("NS", "key", "my/value")),
        ("key=my/value", Tag(None, "key", "my/value")),
        ("NS/key=my/nested/value", Tag("NS", "key", "my/nested/value")),
        ("/key=my/value", Tag(None, "key", "my/value")),
        ("NS/my/key=my/nested/value", Tag("NS", "my/key", "my/nested/value")),
        ("NS/key=my/value/", Tag("NS", "key", "my/value/")),
    ],
)
def test_slash_in_value_tag_from_string(string_tag, expected):
    assert Tag.from_string(string_tag) == expected


def test_no_namespace_tag_from_string():
    assert Tag.from_string("key=value") == Tag(None, "key", "value")


def test_no_value_tag_from_string():
    assert Tag.from_string("NS/key") == Tag("NS", "key", None)


def test_only_key_tag_from_string():
    assert Tag.from_string("key") == Tag(None, "key", None)


@pytest.mark.parametrize(
    "string_tag,expected",
    [
        ("/my/key=myvalue", Tag(None, "my/key", "myvalue")),
        ("/key=value", Tag(None, "key", "value")),
        ("/key", Tag(None, "key", None)),
        ("/my/nested/path/key=myvalue", Tag(None, "my/nested/path/key", "myvalue")),
        ("/my/nested/path/key", Tag(None, "my/nested/path/key", None)),
        ("null/my/key=myvalue", Tag(None, "my/key", "myvalue")),
        ("null/my/key", Tag(None, "my/key", None)),
    ],
)
def test_empty_or_null_namespace_tag_from_string(string_tag, expected):
    assert Tag.from_string(string_tag) == expected


def test_special_characters_decode_tag_from_string():
    assert Tag.from_string("Ns%21%40%23%24%25%5E%26%28%29/k%2Fe%3Dy%5C=v%3A%7C%5C%7B%5C%7D%27%27-%2Bal") == Tag(
        "Ns!@#$%^&()", "k/e=y\\", r"v:|\{\}''-+al"
    )


def test_special_characters_allowed_tag_from_string():
    special_characters = ";,?:@&+$-_.!~*'()#"
    assert Tag.from_string(f"{special_characters}/{special_characters}={special_characters}") == Tag(
        special_characters, special_characters, special_characters
    )


def test_delimiters_tag_from_string():
    decoded = "a/b=c"
    encoded = "a%2Fb%3Dc"
    assert Tag.from_string(f"{encoded}/{encoded}={encoded}") == Tag(decoded, decoded, decoded)


def test_encoded_too_long_tag_from_string():
    decoded = "!" * 86
    encoded = "%21" * 86
    assert Tag.from_string(f"{encoded}/{encoded}={encoded}") == Tag(decoded, decoded, decoded)


def test_decoded_too_long_tag_from_string(subtests):
    too_long = "a" * 256
    for string_tag in (f"{too_long}/a=a", f"a/{too_long}=a", f"a/a={too_long}"):
        with subtests.test(string_tag=string_tag):
            with pytest.raises(ValidationException):
                Tag.from_string(f"{too_long}/{too_long}={too_long}")


def test_all_parts_tag_to_string():
    assert Tag("NS", "key", "value").to_string() == "NS/key=value"


def test_no_value_tag_to_string():
    assert Tag("namespace", "key").to_string() == "namespace/key"


def test_no_namespace_tag_to_string():
    assert Tag(key="key", value="value").to_string() == "key=value"


def test_only_key_tag_to_string():
    assert Tag(key="key").to_string() == "key"


def test_special_characters_tag_to_string():
    assert (
        Tag("Ns!@#$%^&()", "k/e=y\\", r"v:|\{\}''-+al").to_string()
        == "Ns%21%40%23%24%25%5E%26%28%29/k%2Fe%3Dy%5C=v%3A%7C%5C%7B%5C%7D%27%27-%2Bal"
    )


def test_all_parts_tag_from_nested():
    assert Tag.from_nested({"NS": {"key": ["value"]}}) == Tag("NS", "key", "value")


def test_no_value_tag_from_nested():
    assert Tag.from_nested({"NS": {"key": []}}) == Tag("NS", "key")


def test_all_parts_tag_to_nested():
    assert Tag("NS", "key", "value").to_nested() == {"NS": {"key": ["value"]}}


def test_no_value_tag_to_nested():
    assert Tag("NS", "key").to_nested() == {"NS": {"key": []}}


def test_simple_filter_tag_filter_tags():
    structured_tags = [Tag("NS1", "key", "val"), Tag(None, "key", "something"), Tag("NS2", "key2")]
    expected_filtered_tags = [Tag("NS1", "key", "val")]

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "val")


def test_empty_tags_tag_filter_tags():
    structured_tags = []
    expected_filtered_tags = []

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "val")


def test_search_matches_namesapce_tag_filter_tags():
    structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]
    expected_filtered_tags = [Tag("NS1", "key1", "val")]

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "NS1")


def test_search_matches_tag_key_tag_filter_tags():
    structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]
    expected_filtered_tags = [Tag("NS1", "key1", "val")]

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "key1")


def test_complex_filter_tag_filter_tags():
    structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "key2"), Tag("NS3", "key3", "Value3")]
    expected_filtered_tags = [Tag("NS1", "key1", "val"), Tag("NS3", "key3", "Value3")]

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "vA")


def test_empty_filter_tag_filter_tags():
    structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]
    expected_filtered_tags = [Tag("NS1", "key1", "val"), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "")


def test_space_tag_filter_tags():
    structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]
    expected_filtered_tags = []

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, " ")


def test_search_prefix_tag_filter_tags():
    # namespace
    structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]
    expected_filtered_tags = [Tag("NS1", "key1", "val"), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "N")

    # key
    structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "Key2"), Tag("NS3", "key3", "value3")]
    expected_filtered_tags = [Tag("NS1", "key1", "val"), Tag("NS2", "Key2"), Tag("NS3", "key3", "value3")]

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "K")

    # value
    structured_tags = [
        Tag("NS1", "key1", "val"),
        Tag(None),
        Tag("NS2", "Key2", "something"),
        Tag("NS3", "key3", "value3"),
    ]
    expected_filtered_tags = [Tag("NS1", "key1", "val"), Tag("NS3", "key3", "value3")]

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "val")


def test_search_suffix_tag_filter_tags():
    # namespace
    structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]
    expected_filtered_tags = [Tag("NS1", "key1", "val")]

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "S1")

    # key
    structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "Key2"), Tag("NS3", "key3", "value3")]
    expected_filtered_tags = [Tag("NS2", "Key2")]

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "y2")

    # value
    structured_tags = [
        Tag("NS1", "key1", "val"),
        Tag(None),
        Tag("NS2", "Key2", "something"),
        Tag("NS3", "key3", "value3"),
    ]
    expected_filtered_tags = [Tag("NS3", "key3", "value3")]

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "ue3")


def test_create_nested_combined_tag_create_nested_from_tags():
    tags = [Tag("NS1", "Key", "val"), Tag("NS2", "k2")]

    nested_tags = Tag.create_nested_from_tags(tags)

    expected_nested_tags = {"NS1": {"Key": ["val"]}, "NS2": {"k2": []}}

    assert nested_tags == expected_nested_tags


def test_create_nested_single_no_value_tag_create_nested_from_tags():
    tags = [Tag("NS2", "k2")]

    nested_tags = Tag.create_nested_from_tags(tags)

    expected_nested_tags = {"NS2": {"k2": []}}

    assert nested_tags == expected_nested_tags


def test_create_nested_from_tags_no_tags_tag_create_nested_from_tags():
    tags = []

    nested_tags = Tag.create_nested_from_tags(tags)

    expected_nested_tags = {}

    assert nested_tags == expected_nested_tags


def test_with_tags_serialization_deserialize_host_compound(flask_app):
    with flask_app.app.app_context():
        tags = {
            "some namespace": {"some key": ["some value", "another value"], "another key": ["value"]},
            "another namespace": {"key": ["value"]},
        }
        host = deserialize_host(
            {
                "org_id": "3340851",
                "stale_timestamp": now().isoformat(),
                "reporter": "puptoo",
                "subscription_manager_id": generate_uuid(),
                "tags": tags,
            }
        )

        assert Host is type(host)
        assert tags == host.tags


@patch("app.models.schemas.Host")
@patch("app.serialization._deserialize_tags")
@patch("app.serialization._deserialize_facts")
@patch("app.serialization._deserialize_canonical_facts")
def test_without_tags_serialization_deserialize_host_mocked(
    deserialize_canonical_facts, deserialize_facts, deserialize_tags, host, flask_app
):
    with flask_app.app.app_context():
        host_input = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "some account",
            "org_id": "3340851",
            "facts": {
                "some namespace": {"some key": "some value"},
                "another namespace": {"another key": "another value"},
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
        deserialize_tags.assert_called_once_with(None)
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


def test_deserialize_structured_serialization_deserialize_tags(subtests):
    for function in (_deserialize_tags, _deserialize_tags_list):
        with subtests.test(function=function):
            structured_tags = [
                {"namespace": "namespace1", "key": "key1", "value": "value1"},
                {"namespace": "namespace1", "key": "key1", "value": "value2"},
                {"namespace": "namespace1", "key": "key2", "value": "value3"},
                {"namespace": "namespace1", "key": "key2", "value": "value3"},
                {"namespace": "namespace2", "key": "key3", "value": None},
                {"namespace": "namespace2", "key": "key3", "value": ""},
                {"namespace": "namespace2", "key": "key3"},
                {"namespace": "namespace3", "key": "key4", "value": None},
                {"namespace": "namespace3", "key": "key4", "value": "value4"},
                {"namespace": None, "key": "key5", "value": "value5"},
                {"namespace": "", "key": "key5", "value": "value6"},
                {"namespace": "null", "key": "key5", "value": "value7"},
                {"key": "key5", "value": "value7"},
            ]
            nested_tags = function(structured_tags)

            assert sorted(["namespace1", "namespace2", "namespace3", "null"]) == sorted(nested_tags.keys())
            assert sorted(["key1", "key2"]) == sorted(nested_tags["namespace1"].keys())
            assert sorted(["value1", "value2"]) == sorted(nested_tags["namespace1"]["key1"])
            assert sorted(["value3"]) == sorted(nested_tags["namespace1"]["key2"])
            assert sorted(["key3"]) == sorted(nested_tags["namespace2"].keys())
            assert nested_tags["namespace2"]["key3"] == []
            assert sorted(["key4"]) == sorted(nested_tags["namespace3"].keys())
            assert sorted(["value4"]) == sorted(nested_tags["namespace3"]["key4"])
            assert sorted(["key5"]) == sorted(nested_tags["null"].keys())
            assert sorted(["value5", "value6", "value7"]) == sorted(nested_tags["null"]["key5"])


def test_deserialize_nested_serialization_deserialize_tags(subtests):
    for function in (_deserialize_tags, _deserialize_tags_dict):
        with subtests.test(function=function):
            input_tags = {
                "namespace1": {"key1": ["value1", "value2"], "key2": ["value3", "value3"]},
                "namespace2": {"key3": []},
                "namespace3": {"key4": [None, ""]},
                "namespace4": {},
                "": {"key5": ["value4"]},
                "null": {"key5": ["value5"]},
            }
            deserialized_tags = function(input_tags)

            assert sorted(["namespace1", "namespace2", "namespace3", "namespace4", "null"]) == sorted(
                deserialized_tags.keys()
            )
            assert sorted(["key1", "key2"]) == sorted(deserialized_tags["namespace1"].keys())
            assert sorted(["value1", "value2"]) == sorted(deserialized_tags["namespace1"]["key1"])
            assert sorted(["value3"]) == sorted(deserialized_tags["namespace1"]["key2"])
            assert sorted(["key3"]) == sorted(deserialized_tags["namespace2"].keys())
            assert deserialized_tags["namespace2"]["key3"] == []
            assert sorted(["key4"]) == sorted(deserialized_tags["namespace3"].keys())
            assert deserialized_tags["namespace3"]["key4"] == []
            assert deserialized_tags["namespace4"] == {}
            assert sorted(["key5"]) == sorted(deserialized_tags["null"].keys())
            assert sorted(["value4", "value5"]) == sorted(deserialized_tags["null"]["key5"])


def test_deserialize_structured_empty_list_serialization_deserialize_tags(subtests):
    for function in (_deserialize_tags, _deserialize_tags_list):
        with subtests.test(function=function):
            deserialized_tags = function([])
            assert deserialized_tags == {}


def test_deserialize_structured_no_key_error_serialization_deserialize_tags(subtests):
    for function in (_deserialize_tags, _deserialize_tags_list):
        for key in (None, ""):
            with subtests.test(function=function, key=key):
                with pytest.raises(ValueError):
                    structured_tags = [{"namespace": "namespace", "key": key, "value": "value"}]
                    function(structured_tags)


def test_deserialize_nested_empty_dict_serialization_deserialize_tags(subtests):
    for function in (_deserialize_tags, _deserialize_tags_dict):
        with subtests.test(function=function):
            deserialized_tags = function({})
            assert deserialized_tags == {}


def test_deserialize_nested_no_key_error_serialization_deserialize_tags(subtests):
    for function in (_deserialize_tags, _deserialize_tags_dict):
        for key in (None, ""):
            with subtests.test(function=function, key=key):
                with pytest.raises(ValueError):
                    nested_tags = {"namespace": {key: ["value"]}}
                    function(nested_tags)
