"""Host account is payload-owned, not derived from a user's identity account."""

import json
from copy import deepcopy

import pytest

from tests.helpers.api_utils import HOST_URL
from tests.helpers.api_utils import build_facts_url
from tests.helpers.db_utils import db_host
from tests.helpers.mq_utils import assert_delete_event_is_valid
from tests.helpers.mq_utils import assert_patch_event_is_valid
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host


@pytest.fixture(params=[None, "test", "identity"], ids=["missing", "same-as-org", "different-from-org"])
def user_account_identity(request):
    identity = deepcopy(USER_IDENTITY)
    if request.param is None:
        identity.pop("account_number")
    else:
        identity["account_number"] = request.param
    return identity


def _assert_account(host, host_id, account):
    assert host["id"] == str(host_id)
    assert host["org_id"] == USER_IDENTITY["org_id"]
    assert host["account"] == account


def _assert_host_reads(api_get, host_id, insights_id, account, identity=USER_IDENTITY):
    status, result = api_get(HOST_URL, identity=identity, query_parameters={"insights_id": str(insights_id)})
    assert status == 200
    assert result["total"] == 1
    assert len(result["results"]) == 1
    _assert_account(result["results"][0], host_id, account)
    status, result = api_get(f"{HOST_URL}/{host_id}", identity=identity)
    assert status == 200
    assert len(result["results"]) == 1
    host = result["results"][0]
    _assert_account(host, host_id, account)
    return host


@pytest.mark.parametrize("account", [None, "test", "payload"], ids=["omitted", "same-as-org", "different"])
def test_mq_creation_preserves_payload_account(user_account_identity, account, mq_create_or_update_host, api_get):
    payload = minimal_host(insights_id=generate_uuid())
    if account is not None:
        payload.account = account
    _, event, _ = mq_create_or_update_host(payload, identity=user_account_identity, return_all_data=True)
    assert event["type"] == "created"
    host_id = event["host"]["id"]
    _assert_account(event["host"], host_id, account)
    # Only MQ identity varies here; reads deliberately use the ordinary API user.
    _assert_host_reads(api_get, host_id, payload.insights_id, account)


@pytest.mark.parametrize("account", ["test", "payload"], ids=["same-as-org", "different"])
def test_mq_updates_preserve_original_account(
    user_account_identity, account, mq_create_or_update_host, api_get, db_get_host
):
    payload = minimal_host(insights_id=generate_uuid(), account=account, display_name="original")
    created = mq_create_or_update_host(payload)
    # Exercise resupply, omission, and an attempted conflicting account replacement.
    for update_account, name in [(account, "resupplied"), (None, "omitted"), ("replace", "conflicting")]:
        update = minimal_host(insights_id=payload.insights_id, reporter=payload.reporter, display_name=name)
        if update_account is not None:
            update.account = update_account
        _, event, _ = mq_create_or_update_host(update, identity=user_account_identity, return_all_data=True)
        assert event["type"] == "updated"
        _assert_account(event["host"], created.id, account)
        assert event["host"]["display_name"] == name
        stored = db_get_host(created.id)
        assert (stored.account, stored.org_id, stored.display_name) == (account, "test", name)
        read = _assert_host_reads(api_get, created.id, payload.insights_id, account)
        assert read["display_name"] == name


@pytest.mark.parametrize("account", [None, "payload"], ids=["null", "different"])
def test_host_reads_ignore_identity_account(user_account_identity, account, db_create_host, api_get):
    host = db_create_host(
        host=db_host(
            account=account, tags={"account-test": {"role": ["web", "db"]}}, system_profile_facts={"arch": "x86_64"}
        )
    )
    host_id = str(host.id)
    _assert_host_reads(api_get, host_id, host.insights_id, account, user_account_identity)
    status, result = api_get(f"{HOST_URL}/{host_id}/system_profile", identity=user_account_identity)
    assert status == 200
    assert [row["id"] for row in result["results"]] == [host_id]
    assert result["results"][0]["system_profile"]["arch"] == "x86_64"
    status, result = api_get(f"{HOST_URL}/{host_id}/tags", identity=user_account_identity)
    assert status == 200
    assert result["total"] == 1
    assert sorted(result["results"][host_id], key=lambda tag: tag["value"]) == [
        {"namespace": "account-test", "key": "role", "value": "db"},
        {"namespace": "account-test", "key": "role", "value": "web"},
    ]
    status, result = api_get(f"{HOST_URL}/{host_id}/tags/count", identity=user_account_identity)
    assert status == 200
    assert result["total"] == 1
    assert result["results"] == {host_id: 2}


@pytest.mark.parametrize("account", [None, "payload"], ids=["null", "different"])
def test_host_mutations_preserve_account_in_api_and_events(
    user_account_identity,
    account,
    db_create_host,
    db_get_host,
    api_get,
    api_patch,
    api_put,
    event_producer_mock,
    event_datetime_mock,
):
    host = db_create_host(host=db_host(account=account, facts={"account-test": {"fact1": "keep", "fact2": "old"}}))
    host_id, insights_id = str(host.id), str(host.insights_id)
    status, _ = api_patch(f"{HOST_URL}/{host_id}", {"ansible_host": "new.example.com"}, identity=user_account_identity)
    assert status == 200
    read = _assert_host_reads(api_get, host_id, insights_id, account)
    assert read["ansible_host"] == "new.example.com"
    stored = db_get_host(host_id)
    assert_patch_event_is_valid(
        stored,
        event_producer_mock,
        None,
        event_datetime_mock,
        display_name="test-display-name",
        identity=user_account_identity,
    )
    _assert_account(json.loads(event_producer_mock.event)["host"], host_id, account)

    facts_url = build_facts_url(host_list_or_id=host_id, namespace="account-test")
    for method, replacement, expected in [
        (api_patch, "merged", {"fact1": "keep", "fact2": "merged"}),
        (api_put, "replaced", {"fact2": "replaced"}),
    ]:
        status, _ = method(facts_url, {"fact2": replacement}, identity=user_account_identity)
        assert status == 200
        read = _assert_host_reads(api_get, host_id, insights_id, account)
        assert read["facts"] == [{"namespace": "account-test", "facts": expected}]
        stored = db_get_host(host_id)
        assert stored.facts == {"account-test": expected}
        assert stored.account == account
        assert_patch_event_is_valid(
            stored,
            event_producer_mock,
            None,
            event_datetime_mock,
            display_name="test-display-name",
            identity=user_account_identity,
        )
        event_host = json.loads(event_producer_mock.event)["host"]
        _assert_account(event_host, host_id, account)
        assert event_host["facts"] == [{"namespace": "account-test", "facts": expected}]


@pytest.mark.parametrize("account", [None, "payload"], ids=["null", "different"])
@pytest.mark.usefixtures("notification_event_producer_mock")
def test_both_delete_routes_emit_stored_account(
    user_account_identity,
    account,
    db_create_host,
    db_get_host,
    api_delete_host,
    api_delete_filtered_hosts,
    event_producer_mock,
    event_datetime_mock,
):
    for route in ("by-id", "filtered"):
        host = db_create_host(host=db_host(account=account))
        host_id, insights_id = str(host.id), str(host.insights_id)
        if route == "by-id":
            status, _ = api_delete_host(host_id, identity=user_account_identity)
            assert status == 200
        else:
            status, result = api_delete_filtered_hosts({"insights_id": insights_id}, identity=user_account_identity)
            assert status == 202
            assert result["hosts_found"] == result["hosts_deleted"] == 1
        assert_delete_event_is_valid(event_producer_mock, host, event_datetime_mock, identity=user_account_identity)
        event = json.loads(event_producer_mock.event)
        _assert_account(event, host_id, account)
        assert db_get_host(host_id) is None
