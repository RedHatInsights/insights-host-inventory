import json
from copy import deepcopy
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from threading import Event
from threading import Thread
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from dateutil.parser import isoparse

from app.auth.identity import from_auth_header
from app.models import db
from app.queue.event_producer import MessageDetails
from app.queue.event_producer import _encode_headers
from app.serialization import deserialize_canonical_facts
from app.serialization import serialize_canonical_facts
from tests.helpers.api_utils import HOST_WRITE_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import HOST_WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import RBACFilterOperation
from tests.helpers.api_utils import assert_error_response
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_facts_url
from tests.helpers.api_utils import build_host_checkin_url
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_id_list_for_url
from tests.helpers.api_utils import create_custom_rbac_response
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.api_utils import get_id_list_from_hosts
from tests.helpers.db_utils import DB_FACTS
from tests.helpers.db_utils import DB_FACTS_NAMESPACE
from tests.helpers.db_utils import DB_NEW_FACTS
from tests.helpers.db_utils import db_host
from tests.helpers.db_utils import get_expected_facts_after_update
from tests.helpers.mq_utils import HOST_EVENT_HEADER_CASES
from tests.helpers.mq_utils import assert_patch_event_is_valid
from tests.helpers.mq_utils import expected_headers
from tests.helpers.mq_utils import host_event_snapshot
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_staleness_timestamps


@pytest.mark.usefixtures("event_producer_mock")
@pytest.mark.parametrize(
    "patch_doc",
    [
        {"ansible_host": "NEW_ansible_host"},
        {"ansible_host": ""},
        {"display_name": "fred_flintstone"},
        {"display_name": "fred_flintstone", "ansible_host": "barney_rubble"},
    ],
)
def test_update_fields(patch_doc, db_create_host, db_get_host, api_patch):
    host = db_create_host()
    host2 = db_create_host()

    url = build_hosts_url(host_list_or_id=[host, host2])
    response_status, _ = api_patch(url, patch_doc)

    assert_response_status(response_status, expected_status=200)

    record = db_get_host(host.id)
    record2 = db_get_host(host2.id)

    for key in patch_doc:
        assert getattr(record, key) == patch_doc[key]
        assert getattr(record2, key) == patch_doc[key]


@pytest.mark.parametrize(
    "extra_data", [{"insights_id": generate_uuid()}, {"insights_id": generate_uuid(), "fqdn": generate_uuid()}]
)
def test_checkin_canonical_facts(
    event_datetime_mock,
    event_producer_mock,
    db_create_host,
    db_get_host,
    api_post,
    extra_data,
):
    created_host = db_create_host(extra_data=extra_data)

    post_doc = serialize_canonical_facts(created_host, include_none=False)
    updated_time = created_host.modified_on

    response_status, _ = api_post(
        build_host_checkin_url(), post_doc, extra_headers={"x-rh-insights-request-id": "123456"}
    )

    assert_response_status(response_status, expected_status=201)
    record = db_get_host(created_host.id)

    assert record.modified_on > updated_time
    assert record.reporter == created_host.reporter

    assert_patch_event_is_valid(
        created_host,
        event_producer_mock,
        "123456",
        event_datetime_mock,
        created_host.display_name,
    )


@pytest.mark.usefixtures("event_producer_mock")
@pytest.mark.parametrize("branch_id", ("", "54b80cb3-7fca-4444-9faf-aa43e8a560c3"))
def test_checkin_ignores_branch_id(db_create_host, api_post, branch_id):
    created_host = db_create_host()
    post_doc = serialize_canonical_facts(created_host, include_none=False)

    url = f"{build_host_checkin_url()}?branch_id={branch_id}"
    response_status, response_data = api_post(url, post_doc)

    assert_response_status(response_status, expected_status=201)
    assert response_data["id"] == str(created_host.id)


@pytest.mark.usefixtures("event_producer_mock")
def test_checkin_checkin_frequency_valid(db_create_host, api_post, api_get, mocker):
    extra_data = {"insights_id": generate_uuid()}
    created_host = db_create_host(extra_data=extra_data)
    created_host.last_check_in = datetime.now(UTC) - timedelta(days=1)
    db.session.commit()
    status, data = api_get(build_hosts_url(created_host.id))
    assert status == 200
    original = data["results"][0]

    deserialize_canonical_facts_mock = mocker.patch(
        "api.host.deserialize_canonical_facts", wraps=deserialize_canonical_facts
    )

    post_doc = {"insights_id": str(created_host.insights_id), "checkin_frequency": 60}
    response_status, response_data = api_post(
        build_host_checkin_url(), post_doc, extra_headers={"x-rh-insights-request-id": "123456"}
    )

    assert_response_status(response_status, expected_status=201)
    deserialize_canonical_facts_mock.assert_called_once_with(post_doc)
    assert response_data["id"] == str(created_host.id)
    assert response_data["insights_id"] == original["insights_id"]
    for field in ("last_check_in", "stale_timestamp", "stale_warning_timestamp", "culled_timestamp"):
        assert isoparse(response_data[field]) > isoparse(original[field])


@pytest.mark.usefixtures("event_producer_mock")
@pytest.mark.parametrize(("checkin_frequency",), ((-1,), (0,), (2881,), ("not a number",)))
def test_checkin_checkin_frequency_invalid(db_create_host, api_post, checkin_frequency):
    extra_data = {"insights_id": generate_uuid()}
    created_host = db_create_host(extra_data=extra_data)
    canonical_facts = serialize_canonical_facts(created_host, include_none=False)

    post_doc = {**canonical_facts, "checkin_frequency": checkin_frequency}
    response_status, _ = api_post(
        build_host_checkin_url(), post_doc, extra_headers={"x-rh-insights-request-id": "123456"}
    )

    assert_response_status(response_status, expected_status=400)


def test_checkin_no_matching_host(event_producer_mock, api_post):
    post_doc = {"insights_id": generate_uuid()}

    response_status, _ = api_post(
        build_host_checkin_url(), post_doc, extra_headers={"x-rh-insights-request-id": "123456"}
    )

    assert_response_status(response_status, expected_status=404)
    assert event_producer_mock.key is None
    assert event_producer_mock.event is None


@pytest.mark.parametrize(("post_doc",), (({},), ({"checkin_frequency": "720"},)))
def test_checkin_no_canonical_facts(event_producer_mock, api_post, post_doc):
    response_status, _ = api_post(
        build_host_checkin_url(), post_doc, extra_headers={"x-rh-insights-request-id": "123456"}
    )

    assert_response_status(response_status, expected_status=400)
    assert event_producer_mock.key is None
    assert event_producer_mock.event is None


@pytest.mark.usefixtures("event_producer_mock")
def test_patch_with_branch_id_parameter(db_create_multiple_hosts, api_patch):
    patch_doc = {"display_name": "branch_id_test"}

    hosts = db_create_multiple_hosts(how_many=5)

    url = build_hosts_url(host_list_or_id=hosts, query="?branch_id=123")
    response_status, _ = api_patch(url, patch_doc)

    assert_response_status(response_status, expected_status=200)


@pytest.mark.usefixtures("event_producer_mock")
def test_update_fields_on_multiple_hosts(db_create_multiple_hosts, db_get_hosts, api_patch):
    patch_doc = {"display_name": "fred_flintstone", "ansible_host": "barney_rubble"}

    hosts = db_create_multiple_hosts(how_many=5)

    url = build_hosts_url(host_list_or_id=hosts)
    response_status, _ = api_patch(url, patch_doc)

    assert_response_status(response_status, expected_status=200)

    host_id_list = [host.id for host in hosts]
    hosts = db_get_hosts(host_id_list)

    for host in hosts:
        for key in patch_doc:
            assert getattr(host, key) == patch_doc[key]


def test_patch_on_non_existent_host(api_patch):
    non_existent_id = generate_uuid()

    patch_doc = {"ansible_host": "NEW_ansible_host"}

    url = build_hosts_url(host_list_or_id=non_existent_id)
    response_status, _ = api_patch(url, patch_doc)

    assert_response_status(response_status, expected_status=404)


@pytest.mark.usefixtures("event_producer_mock")
def test_patch_on_multiple_hosts_with_some_non_existent(db_create_host, db_get_host, api_patch):
    non_existent_id = generate_uuid()
    host = db_create_host(extra_data={"ansible_host": "OLD_ansible_host"})

    patch_doc = {"ansible_host": "NEW_ansible_host"}

    url = build_hosts_url(host_list_or_id=f"{non_existent_id},{host.id}")
    response_status, _ = api_patch(url, patch_doc)

    assert_response_status(response_status, expected_status=404)

    # Make sure a partial update did not occur
    assert db_get_host(host.id).ansible_host == "OLD_ansible_host"


@pytest.mark.parametrize(
    "invalid_data",
    [
        {"ansible_host": "a" * 256},
        {"ansible_host": None},
        {},
        {"display_name": None},
        {"display_name": ""},
        {"display_name": "a" * 300},
    ],
)
def test_invalid_data(invalid_data, db_create_host, api_patch, event_producer_mock):
    host = db_create_host()

    url = build_hosts_url(host_list_or_id=host.id)
    response_status, _ = api_patch(url, invalid_data)

    assert_response_status(response_status, expected_status=400)
    assert event_producer_mock.events == []


def test_invalid_host_id(db_create_host, api_patch, subtests):
    host = db_create_host()

    patch_doc = {"display_name": "branch_id_test"}
    host_id_lists = ["notauuid", f"{host.id},notauuid"]

    for host_id_list in host_id_lists:
        with subtests.test(host_id_list=host_id_list):
            url = build_hosts_url(host_list_or_id=host_id_list)
            response_status, _ = api_patch(url, patch_doc)
            assert_response_status(response_status, expected_status=400)


def test_patch_produces_update_event_no_request_id(
    event_datetime_mock, event_producer_mock, db_create_host, api_patch
):
    host = db_host()
    created_host = db_create_host(host=host)

    patch_doc = {"display_name": "patch_event_test"}

    url = build_hosts_url(host_list_or_id=created_host.id)
    response_status, _ = api_patch(url, patch_doc)
    assert_response_status(response_status, expected_status=200)

    assert_patch_event_is_valid(
        host=created_host,
        event_producer=event_producer_mock,
        expected_request_id=None,
        expected_timestamp=event_datetime_mock,
    )


def test_patch_produces_update_event_with_request_id(
    event_datetime_mock, event_producer_mock, db_create_host, api_patch
):
    patch_doc = {"display_name": "patch_event_test"}
    request_id = generate_uuid()
    headers = {"x-rh-insights-request-id": request_id}

    host = db_host()
    created_host = db_create_host(host=host)

    url = build_hosts_url(host_list_or_id=created_host.id)
    response_status, _ = api_patch(url, patch_doc, extra_headers=headers)
    assert_response_status(response_status, expected_status=200)

    assert_patch_event_is_valid(
        host=created_host,
        event_producer=event_producer_mock,
        expected_request_id=request_id,
        expected_timestamp=event_datetime_mock,
    )


def test_patch_produces_update_event_no_insights_id(
    event_datetime_mock, event_producer_mock, db_create_host, api_patch
):
    host = db_host()
    del host.insights_id

    created_host = db_create_host(host=host)

    patch_doc = {"display_name": "patch_event_test"}

    url = build_hosts_url(host_list_or_id=created_host.id)
    response_status, _ = api_patch(url, patch_doc)
    assert_response_status(response_status, expected_status=200)

    assert_patch_event_is_valid(
        host=created_host,
        event_producer=event_producer_mock,
        expected_request_id=None,
        expected_timestamp=event_datetime_mock,
    )


def test_patch_by_namespace_produces_update_event(event_producer_mock, event_datetime_mock, db_create_host, api_patch):
    created_host = db_create_host(
        host=db_host(facts={"ns1": {"fact1": "keep", "fact2": "old"}, "other": {"keep": "me"}})
    )
    expected = host_event_snapshot(created_host)
    previous_updated = created_host.modified_on
    expected["facts"] = [
        {"namespace": "ns1", "facts": {"fact1": "keep", "fact2": "replaced", "fact3": "added"}},
        {"namespace": "other", "facts": {"keep": "me"}},
    ]

    facts_url = build_facts_url(host_list_or_id=created_host.id, namespace=DB_FACTS_NAMESPACE)
    response_status, _ = api_patch(facts_url, {"fact2": "replaced", "fact3": "added"})
    assert_response_status(response_status, expected_status=200)

    assert_patch_event_is_valid(
        host=created_host,
        event_producer=event_producer_mock,
        expected_request_id=None,
        expected_timestamp=event_datetime_mock,
        display_name="test-display-name",
        expected_host=expected,
        updated_after=previous_updated,
    )
    assert len(event_producer_mock.events) == 1


@pytest.mark.parametrize("how_many", (1, 3))
def test_patch_event_header_contracts(
    how_many,
    db_create_host,
    api_patch,
    event_producer_mock,
    event_datetime_mock,
    subtests,
    db_create_group,
    db_create_host_group_assoc,
):
    group_id = db_create_group("event-group").id
    request_ids = (None, "", "91a80cc0-309c-4cf5-b079-73fe588a9db4")
    for case_index, (profile, host_type, os_name, is_bootc) in enumerate(HOST_EVENT_HEADER_CASES):
        for with_insights_id in (False, True):
            with subtests.test(profile=profile, with_insights_id=with_insights_id):
                originals = []
                for _ in range(how_many):
                    host = db_create_host(host=db_host(insights_id=generate_uuid() if with_insights_id else None))
                    host.update_system_profile(deepcopy(profile))
                    db.session.commit()
                    db_create_host_group_assoc(host.id, group_id)
                    originals.append((host, host_event_snapshot(host), host.modified_on))
                request_id = request_ids[case_index % len(request_ids)]
                headers = {} if request_id is None else {"x-rh-insights-request-id": request_id}
                patch_doc = {"display_name": "patch_event_test", "ansible_host": "patched.example.com"}
                event_producer_mock.events.clear()
                status, _ = api_patch(
                    build_hosts_url([host for host, _, _ in originals]), patch_doc, extra_headers=headers
                )
                assert status == 200
                records = event_producer_mock.events
                assert len(records) == how_many
                assert {record.key for record in records} == {str(host.id) for host, _, _ in originals}
                by_id = {str(host.id): (host, expected, previous) for host, expected, previous in originals}
                for record in records:
                    host, expected, previous = by_id[record.key]
                    expected.update(patch_doc)
                    assert_patch_event_is_valid(
                        host, record, request_id, event_datetime_mock, expected_host=expected, updated_after=previous
                    )
                    assert record.headers == expected_headers(
                        "updated", request_id, expected["insights_id"], "test-reporter", host_type, os_name, is_bootc
                    )
                    assert dict(_encode_headers(record.headers))["request_id"] == (
                        request_id.encode() if request_id else b""
                    )


def test_patch_by_namespace_on_multiple_hosts_produces_multiple_update_events(
    event_producer, db_create_multiple_hosts, api_patch, mocker
):
    mocker.patch.object(event_producer, "write_event")

    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": DB_FACTS})

    facts_url = build_facts_url(host_list_or_id=created_hosts, namespace=DB_FACTS_NAMESPACE)
    response_status, _ = api_patch(facts_url, DB_NEW_FACTS)
    assert_response_status(response_status, expected_status=200)

    assert event_producer.write_event.call_count == 2


@pytest.mark.parametrize(
    "patched_function,error",
    (
        ("message_produced", None),
        ("message_not_produced", MagicMock()),
    ),
)
def test_event_producer_instrumentation(mocker, event_producer, db_create_host, api_patch, patched_function, error):
    created_host = db_create_host()
    url = build_hosts_url(host_list_or_id=created_host.id)

    mocked_callback_function = mocker.patch(f"app.queue.event_producer.{patched_function}")
    headers = MagicMock()
    message = MagicMock()

    msgdet = MessageDetails(topic=None, event=message, headers=headers, key=created_host.id)
    event_producer._kafka_producer.produce.return_effects = msgdet.on_delivered(error, message)

    patch_doc = {"display_name": "patch_event_test"}

    response_status, _ = api_patch(url, patch_doc)

    assert_response_status(response_status, expected_status=200)
    mocked_callback_function.assert_called_once()


def test_add_facts_without_fact_dict(api_patch):
    facts_url = build_facts_url(host_list_or_id=generate_uuid(), namespace=DB_FACTS_NAMESPACE)
    _, response_data = api_patch(facts_url, None)

    assert_error_response(response_data, expected_status=400, expected_detail="Request body must not be empty")


@pytest.mark.usefixtures("event_producer_mock")
def test_add_facts_to_multiple_hosts(db_create_multiple_hosts, db_get_hosts, api_patch):
    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": DB_FACTS})

    host_id_list = get_id_list_from_hosts(created_hosts)
    facts_url = build_facts_url(host_list_or_id=created_hosts, namespace=DB_FACTS_NAMESPACE)

    response_status, _ = api_patch(facts_url, DB_NEW_FACTS)

    assert_response_status(response_status, expected_status=200)

    expected_facts = get_expected_facts_after_update("add", DB_FACTS_NAMESPACE, DB_FACTS, DB_NEW_FACTS)

    assert all(host.facts == expected_facts for host in db_get_hosts(host_id_list))


@pytest.mark.usefixtures("event_producer_mock")
def test_add_facts_to_multiple_hosts_with_branch_id(db_create_multiple_hosts, db_get_hosts, api_patch):
    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": DB_FACTS})

    host_id_list = get_id_list_from_hosts(created_hosts)
    facts_url = build_facts_url(host_list_or_id=created_hosts, namespace=DB_FACTS_NAMESPACE, query="?branch_id=1234")

    response_status, _ = api_patch(facts_url, DB_NEW_FACTS)
    assert_response_status(response_status, expected_status=200)

    expected_facts = get_expected_facts_after_update("add", DB_FACTS_NAMESPACE, DB_FACTS, DB_NEW_FACTS)

    assert all(host.facts == expected_facts for host in db_get_hosts(host_id_list))


def test_add_facts_to_multiple_hosts_including_nonexistent_host(db_create_multiple_hosts, api_patch):
    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": DB_FACTS})

    url_host_id_list = f"{build_id_list_for_url(created_hosts)},{generate_uuid()},{generate_uuid()}"
    facts_url = build_facts_url(host_list_or_id=url_host_id_list, namespace=DB_FACTS_NAMESPACE)

    response_status, _ = api_patch(facts_url, DB_NEW_FACTS)

    assert_response_status(response_status, expected_status=404)


@pytest.mark.usefixtures("event_producer_mock")
def test_add_facts_to_multiple_hosts_overwrite_empty_key_value_pair(db_create_multiple_hosts, db_get_hosts, api_patch):
    facts = {DB_FACTS_NAMESPACE: {}}

    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": facts})

    host_id_list = get_id_list_from_hosts(created_hosts)
    facts_url = build_facts_url(host_list_or_id=created_hosts, namespace=DB_FACTS_NAMESPACE)

    response_status, _ = api_patch(facts_url, DB_NEW_FACTS)
    assert_response_status(response_status, expected_status=200)

    expected_facts = get_expected_facts_after_update("add", DB_FACTS_NAMESPACE, facts, DB_NEW_FACTS)

    assert all(host.facts == expected_facts for host in db_get_hosts(host_id_list))


def test_add_facts_to_multiple_hosts_add_empty_fact_set(db_create_multiple_hosts, api_patch):
    new_facts = {}

    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": DB_FACTS})

    facts_url = build_facts_url(created_hosts, DB_FACTS_NAMESPACE)

    response_status, _ = api_patch(facts_url, new_facts)
    assert_response_status(response_status, expected_status=400)


@pytest.mark.parametrize("facts_to_update,expected_status", (({}, 400), ({"new": "fact"}, 404)))
def test_add_facts_to_namespace_that_does_not_exist(
    db_create_multiple_hosts, api_patch, event_producer_mock, facts_to_update, expected_status
):
    facts_namespace = "ns1"
    facts = {facts_namespace: {"key1": "value1"}}

    created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": facts})

    facts_url = build_facts_url(host_list_or_id=created_hosts, namespace="imanonexistentnamespace")

    response_status, data = api_patch(facts_url, facts_to_update)
    assert_response_status(response_status, expected_status=expected_status)
    if expected_status == 404:
        assert "number of hosts" in data.lower()
    assert event_producer_mock.events == []


@pytest.mark.usefixtures("event_producer_mock")
@pytest.mark.system_culling
def test_add_facts_to_multiple_culled_hosts(db_create_multiple_hosts, api_patch, db_create_staleness_culling):
    with patch("app.models.utils.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(2023, 4, 2)
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        db_create_staleness_culling(
            conventional_time_to_stale=1,
            conventional_time_to_stale_warning=1,
            conventional_time_to_delete=1,
        )

        created_hosts = db_create_multiple_hosts(how_many=2, extra_data={"facts": DB_FACTS})

        culled_last_check_in = get_staleness_timestamps()["culled"]
        for host in created_hosts:
            host.last_check_in = culled_last_check_in
        db.session.commit()

        facts_url = build_facts_url(host_list_or_id=created_hosts, namespace=DB_FACTS_NAMESPACE)

        # Try to replace the facts on a host that has been marked as culled
        response_status, _ = api_patch(facts_url, DB_NEW_FACTS)
        assert_response_status(response_status, expected_status=404)


@pytest.mark.usefixtures("enable_rbac", "event_producer_mock")
def test_patch_host_with_RBAC_allowed(subtests, mocker, api_patch, db_create_host):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in HOST_WRITE_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            host = db_create_host()

            url = build_hosts_url(host_list_or_id=host.id)
            response_status, _ = api_patch(url, {"display_name": "fred_flintstone"})

            assert_response_status(response_status, 200)


@pytest.mark.usefixtures("enable_rbac", "event_producer_mock")
def test_patch_host_with_RBAC_denied(subtests, mocker, api_patch, db_create_host, db_get_host):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in HOST_WRITE_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            host = db_create_host()

            url = build_hosts_url(host_list_or_id=host.id)

            new_display_name = "fred_flintstone"
            response_status, _ = api_patch(url, {"display_name": new_display_name})

            assert_response_status(response_status, 403)

            assert db_get_host(host.id).display_name != new_display_name


@pytest.mark.usefixtures("enable_rbac")
def test_patch_host_with_RBAC_denied_specific_groups(mocker, api_patch, db_create_host):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    # Grant write access to the hosts in irrelevant groups
    get_rbac_permissions_mock.return_value = create_custom_rbac_response(
        [generate_uuid(), generate_uuid()], RBACFilterOperation.IN, "write"
    )

    # Create host that user doesn't have access to
    host = db_create_host()
    url = build_hosts_url(host_list_or_id=host.id)

    new_display_name = "fred_flintstone"
    response_status, response_data = api_patch(url, {"display_name": new_display_name})

    assert_response_status(response_status, 404)
    assert "not found" in response_data["detail"]


@pytest.mark.usefixtures("enable_rbac", "event_producer_mock")
def test_patch_host_with_RBAC_allowed_ungrouped(mocker, api_patch, db_create_host):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    # Grant write access specifically to ungrouped hosts
    get_rbac_permissions_mock.return_value = create_custom_rbac_response([None], RBACFilterOperation.IN, "write")

    # Create an ungrouped host
    host = db_create_host()
    url = build_hosts_url(host_list_or_id=host.id)

    new_display_name = "fred_flintstone"
    response_status, _ = api_patch(url, {"display_name": new_display_name})

    assert_response_status(response_status, 200)


@pytest.mark.usefixtures("enable_rbac", "event_producer_mock")
def test_patch_host_with_RBAC_bypassed_as_system(api_patch, db_create_host):
    host = db_create_host(
        SYSTEM_IDENTITY, extra_data={"system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]}}
    )

    url = build_hosts_url(host_list_or_id=host.id)
    response_status, _ = api_patch(url, {"display_name": "fred_flintstone"}, SYSTEM_IDENTITY)

    assert_response_status(response_status, 200)


@pytest.mark.usefixtures("notification_event_producer")
def test_update_delete_race(event_producer, db_create_host, db_get_host, api_patch, api_delete_host, mocker):
    mocker.patch.object(event_producer, "write_event")
    mocker.patch("lib.host_delete.kafka_available")

    patch_started = Event()
    delete_finished = Event()

    def wait_for_delete(_display_name, _reporter):
        patch_started.set()
        assert delete_finished.wait(timeout=10)

    mocker.patch("app.models.Host.update_display_name", wraps=wait_for_delete)

    host_id = db_create_host().id

    def patch_host():
        url = build_hosts_url(host_list_or_id=host_id)
        api_patch(url, {"ansible_host": "localhost.localdomain"})

    # run PATCH asynchronously
    patchThread = Thread(target=patch_host, daemon=True)
    patchThread.start()
    assert patch_started.wait(timeout=10)

    # as PATCH is running, concurrently delete the host
    response_status, _ = api_delete_host(host_id)
    delete_finished.set()
    assert_response_status(response_status, expected_status=200)

    # wait for PATCH to finish
    patchThread.join()

    # the host should be deleted and the last message to be produced should be the delete message
    assert not db_get_host(host_id)
    assert event_producer.write_event.call_args_list[-1][0][2]["event_type"] == "delete"


def test_no_event_on_noop(event_producer, db_create_host, api_patch, mocker):
    mocker.patch.object(event_producer, "write_event")

    host = db_create_host()

    url = build_hosts_url(host_list_or_id=host.id)
    api_patch(url, {})

    assert event_producer.write_event.call_count == 0


def test_patch_updated_timestamp(event_producer, db_create_host, db_get_host, api_patch, mocker):
    mocker.patch.object(event_producer, "write_event")
    host = db_create_host()
    patch_doc = {"display_name": "update_test"}
    url = build_hosts_url(host_list_or_id=host.id)
    patch_response_status, _ = api_patch(url, patch_doc)

    assert_response_status(patch_response_status, expected_status=200)

    record = db_get_host(host.id)

    updated_timestamp_from_event = json.loads(event_producer.write_event.call_args_list[0][0][0])["host"]["updated"]
    b64_identity = json.loads(event_producer.write_event.call_args_list[0][0][0])["platform_metadata"]["b64_identity"]
    identity = from_auth_header(b64_identity)

    assert updated_timestamp_from_event == record.modified_on.astimezone(UTC).isoformat()
    assert identity._asdict() == USER_IDENTITY
