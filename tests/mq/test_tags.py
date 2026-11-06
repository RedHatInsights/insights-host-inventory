from __future__ import annotations

from app.utils import Tag
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host


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
            mq_create_or_update_host(host)

            record = db_get_host_by_insights_id(insights_id)
            structured_tags = [Tag.from_nested({ns: ns_item}) for ns, ns_item in expected_tags.items()]

            assert expected_tags == record.tags
            # The more concise way of replacing tags changes the list order
            assert sorted(
                Tag.create_flat_tags_from_structured(structured_tags), key=lambda t: t["namespace"]
            ) == sorted(record.tags_alt, key=lambda t: t["namespace"])


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
            mq_create_or_update_host(host)

            record = db_get_host_by_insights_id(insights_id)
            structured_tags = [Tag.from_nested({ns: ns_item}) for ns, ns_item in expected_tags.items()]

            assert expected_tags == record.tags
            assert Tag.create_flat_tags_from_structured(structured_tags) == record.tags_alt
