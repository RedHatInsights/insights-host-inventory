from __future__ import annotations

import json
from urllib.parse import quote
from urllib.parse import urlencode

import pytest

from app.exceptions import ValidationException
from app.utils import Tag
from tests.helpers.api_utils import build_host_tags_url
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host


def _flat_tag_set(tags):
    return {tuple(tag[part] for part in ("namespace", "key", "value")) for tag in tags}


def _expected_flat_tags(nested):
    # An independent expansion keeps event/persistence expectations out of the production serializer.
    return [
        {"namespace": None if namespace in (None, "", "null") else namespace, "key": key, "value": value}
        for namespace, keys in nested.items()
        for key, values in keys.items()
        for value in (values or [None])
    ]


def test_special_character_tags_event_readback_and_filter(mq_create_or_update_host, api_get, subtests):
    for tag in (
        {"key": "*()%$"},
        {"key": "^~&-=", "value": "}{?:><"},
        {"namespace": ";?:@", "key": "&+$-_,.", "value": "!~*'()#"},
        {"namespace": "Ns%21%40%23%24", "key": "k%2Fe%3Dy%5C", "value": "v%3A%7C%5C%7B%5C"},
        {"namespace": "location", "key": "city", "value": "Sacramento, CA"},
        {"namespace": "with-value", "key": "my/key", "value": "myvalue"},
        {"namespace": "without-value", "key": "my/key"},
    ):
        with subtests.test(tag=tag):
            expected = {"namespace": None, "value": None, **tag}
            host = mq_create_or_update_host(minimal_host(tags=[tag]))
            assert host.tags == [expected]
            status, response = api_get(build_host_tags_url(host.id))
            assert status == 200
            assert response["results"] == {host.id: [expected]}

            # Encode components independently from HTTP transport encoding. Percent text is literal input.
            encodings = (False, True) if tag["key"] in ("city", "my/key") else (True,)
            for encode_components in encodings:
                parts = {key: quote(value, safe="") if encode_components else value for key, value in tag.items()}
                query_tag = (f"{parts['namespace']}/" if parts.get("namespace") else "") + parts["key"]
                if parts.get("value"):
                    query_tag += "=" + parts["value"]
                status, response = api_get(build_hosts_url(query="?" + urlencode({"tags": query_tag})))
                assert status == 200
                assert response["count"] == 1
                assert [result["id"] for result in response["results"]] == [host.id]


def test_invalid_nested_tags_validation_notification(
    mq_create_or_update_host, notification_event_producer_mock, subtests
):
    for index, tags in enumerate(
        (
            {"namespace": {"k" * 256: ["v"]}},
            {"namespace": {"key": "scalar-value"}},
            {"n" * 256: {"key": ["v"]}},
            {"namespace": {"key": ["v" * 256]}},
            {"namespace": {"": ["v"]}},
            {"namespace": [{"key": "value"}]},
        )
    ):
        with subtests.test(tags=tags):
            host = minimal_host(display_name=f"invalid-nested-tags-{index}", tags=tags)
            with pytest.raises(ValidationException):
                mq_create_or_update_host(host)
            event = json.loads(notification_event_producer_mock.event)
            assert event["event_type"] == "validation-error"
            assert event["events"][0]["payload"]["display_name"] == host.display_name


def test_replace_tags_of_host_by_list(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ([], {}),
        (
            [
                {"namespace": "namespace 1", "key": "key 1", "value": "value 1"},
                {"namespace": "namespace 2", "key": "key 2", "value": "value 2"},
                {"namespace": "null", "key": "key 3", "value": "value 3"},
            ],
            {
                "namespace 1": {"key 1": ["value 1"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 3": ["value 3"]},
            },
        ),
        (
            [{"namespace": "namespace 1", "key": "key 4", "value": "value 4"}],
            {
                "namespace 1": {"key 4": ["value 4"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 3": ["value 3"]},
            },
        ),
        (
            [{"key": "key 5", "value": "value 5"}],
            {
                "namespace 1": {"key 4": ["value 4"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 5": ["value 5"]},
            },
        ),
        (
            [{"namespace": None, "key": "key 6", "value": "value 6"}],
            {
                "namespace 1": {"key 4": ["value 4"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 6": ["value 6"]},
            },
        ),
        (
            [{"namespace": "", "key": "key 7", "value": "value 7"}],
            {
                "namespace 1": {"key 4": ["value 4"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 7": ["value 7"]},
            },
        ),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, tags=message_tags)
            mq_create_or_update_host(host)

            record = db_get_host_by_insights_id(insights_id)
            structured_tags = structured_tags = [
                Tag.from_nested({ns: ns_item}) for ns, ns_item in expected_tags.items()
            ]

            assert expected_tags == record.tags
            # The more concise way of replacing tags changes the list order
            assert sorted(
                Tag.create_flat_tags_from_structured(structured_tags), key=lambda t: t["namespace"]
            ) == sorted(record.tags_alt, key=lambda t: t["namespace"])


def test_replace_host_tags_by_dict(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ({}, {}),
        (
            {
                "namespace 1": {"key 1": ["value 1"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 3": ["value 3"]},
            },
            {
                "namespace 1": {"key 1": ["value 1"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 3": ["value 3"]},
            },
        ),
        (
            {"namespace 1": {"key 4": ["value 4"]}},
            {
                "namespace 1": {"key 4": ["value 4"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 3": ["value 3"]},
            },
        ),
        (
            {"": {"key 5": ["value 5"]}},
            {
                "namespace 1": {"key 4": ["value 4"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 5": ["value 5"]},
            },
        ),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, tags=message_tags)
            event_host = mq_create_or_update_host(host)

            record = db_get_host_by_insights_id(insights_id)
            structured_tags = [Tag.from_nested({ns: ns_item}) for ns, ns_item in expected_tags.items()]
            assert expected_tags == record.tags
            assert sorted(
                Tag.create_flat_tags_from_structured(structured_tags), key=lambda t: t["namespace"]
            ) == sorted(record.tags_alt, key=lambda t: t["namespace"])
            assert _flat_tag_set(_expected_flat_tags(expected_tags)) == _flat_tag_set(event_host.tags)


def test_keep_host_tags_by_empty(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ({"tags": {"namespace 1": {"key 1": ["value 1"]}}}, {"namespace 1": {"key 1": ["value 1"]}}),
        ({}, {"namespace 1": {"key 1": ["value 1"]}}),
        ({"tags": []}, {"namespace 1": {"key 1": ["value 1"]}}),
        ({"tags": {}}, {"namespace 1": {"key 1": ["value 1"]}}),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, **message_tags)
            mq_create_or_update_host(host)

            record = db_get_host_by_insights_id(insights_id)

            assert expected_tags == record.tags


def test_delete_host_tags(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ({}, {}),
        (
            {
                "namespace 1": {"key 1": ["value 1"]},
                "namespace 2": {"key 2": ["value 2"]},
                "namespace 3": {"key 3": ["value 3"]},
                "null": {"key 4": ["value 4"]},
            },
            {
                "namespace 1": {"key 1": ["value 1"]},
                "namespace 2": {"key 2": ["value 2"]},
                "namespace 3": {"key 3": ["value 3"]},
                "null": {"key 4": ["value 4"]},
            },
        ),
        (
            {"namespace 2": None, "namespace 3": {}},
            {"namespace 1": {"key 1": ["value 1"]}, "null": {"key 4": ["value 4"]}},
        ),
        ({"null": {}}, {"namespace 1": {"key 1": ["value 1"]}}),
        ({"null": {"key 5": ["value 5"]}}, {"namespace 1": {"key 1": ["value 1"]}, "null": {"key 5": ["value 5"]}}),
        ({"": {}}, {"namespace 1": {"key 1": ["value 1"]}}),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(account=SYSTEM_IDENTITY["account_number"], insights_id=insights_id, tags=message_tags)
            event_host = mq_create_or_update_host(host)

            record = db_get_host_by_insights_id(insights_id)
            structured_tags = [Tag.from_nested({ns: ns_item}) for ns, ns_item in expected_tags.items()]
            assert expected_tags == record.tags
            assert Tag.create_flat_tags_from_structured(structured_tags) == record.tags_alt
            assert _flat_tag_set(_expected_flat_tags(expected_tags)) == _flat_tag_set(event_host.tags)


def test_delete_only_tags_namespace(mq_create_or_update_host, db_get_host_by_insights_id):
    insights_id = generate_uuid()
    initial = {"only": {"first": ["v1"], "second": ["v2"]}}
    event_host = mq_create_or_update_host(minimal_host(insights_id=insights_id, tags=initial))
    assert _flat_tag_set(event_host.tags) == _flat_tag_set(_expected_flat_tags(initial))
    assert db_get_host_by_insights_id(insights_id).tags == initial

    event_host = mq_create_or_update_host(minimal_host(insights_id=insights_id, tags={"only": {}}))
    assert event_host.tags == []
    assert db_get_host_by_insights_id(insights_id).tags == {}


def test_delete_null_tags_namespace(mq_create_or_update_host, db_get_host_by_insights_id):
    insights_id = generate_uuid()
    initial = {None: {"key": ["v"]}, "retained": {"key": ["other"]}}
    event_host = mq_create_or_update_host(minimal_host(insights_id=insights_id, tags=initial))
    assert _flat_tag_set(event_host.tags) == _flat_tag_set(_expected_flat_tags(initial))
    event_host = mq_create_or_update_host(minimal_host(insights_id=insights_id, tags={None: {}}))
    assert event_host.tags == [{"namespace": "retained", "key": "key", "value": "other"}]
    assert db_get_host_by_insights_id(insights_id).tags == {"retained": {"key": ["other"]}}


@pytest.mark.parametrize(
    "initial,update,expected",
    (
        (
            {"satellite": {"multi": ["old", "retained"], "key": ["old"], "valueless": []}},
            {"satellite": {"multi": ["new", "retained"], "key": ["new"]}},
            {"satellite": {"multi": ["new", "retained"], "key": ["new"]}},
        ),
        (
            {"satellite": {"key": ["old"]}, "untouched": {"key": ["v"]}},
            {"satellite": {"key": ["new"]}, "added": {"key": ["added"]}},
            {"satellite": {"key": ["new"]}, "untouched": {"key": ["v"]}, "added": {"key": ["added"]}},
        ),
        (
            {"satellite": {"key": ["old"]}, "removed": {"key": ["v"]}},
            {"satellite": {"key": ["new"]}, "removed": {}},
            {"satellite": {"key": ["new"]}},
        ),
    ),
    ids=("multi-values-and-valueless-key", "replace-add-preserve", "replace-and-delete"),
)
def test_nested_tags_update_event(initial, update, expected, mq_create_or_update_host, db_get_host_by_insights_id):
    insights_id = generate_uuid()
    event_host = mq_create_or_update_host(minimal_host(insights_id=insights_id, tags=initial))
    assert _flat_tag_set(event_host.tags) == _flat_tag_set(_expected_flat_tags(initial))
    assert db_get_host_by_insights_id(insights_id).tags == initial

    event_host = mq_create_or_update_host(minimal_host(insights_id=insights_id, tags=update))
    assert _flat_tag_set(event_host.tags) == _flat_tag_set(_expected_flat_tags(expected))
    record = db_get_host_by_insights_id(insights_id)
    assert record.tags == expected
    assert _flat_tag_set(record.tags_alt) == _flat_tag_set(_expected_flat_tags(expected))
