#!/usr/bin/env python
import copy
from datetime import timedelta
from itertools import product

import pytest

from lib.host_repository import canonical_fact_host_query
from lib.host_repository import canonical_facts_host_query
from tests.test_utils import ACCOUNT
from tests.test_utils import assert_error_response
from tests.test_utils import assert_host_data
from tests.test_utils import assert_host_response_status
from tests.test_utils import assert_host_was_created
from tests.test_utils import assert_host_was_updated
from tests.test_utils import assert_response_status
from tests.test_utils import FACTS
from tests.test_utils import generate_uuid
from tests.test_utils import get_host_from_multi_response
from tests.test_utils import get_host_from_response
from tests.test_utils import HOST_URL
from tests.test_utils import minimal_host
from tests.test_utils import now
from tests.test_utils import SHARED_SECRET
from tests.test_utils import valid_system_profile


def test_create_and_update(api_create_or_update_host, api_get_host):
    host = minimal_host()

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)
    assert_host_data(actual_host=create_host_response["host"], expected_host=host)

    created_host_id = create_host_response["host"]["id"]

    host.facts = copy.deepcopy(FACTS)
    # Replace facts under the first namespace
    host.facts[0]["facts"] = {"newkey1": "newvalue1"}
    # Add a new set of facts under a new namespace
    host.facts.append({"namespace": "ns2", "facts": {"key2": "value2"}})

    # Add a new canonical fact
    host.rhel_machine_id = generate_uuid()
    host.ip_addresses = ["10.10.0.1", "10.0.0.2", "fe80::d46b:2807:f258:c319"]
    host.mac_addresses = ["c2:00:d0:c8:61:01"]
    host.external_id = "i-05d2313e6b9a42b16"
    host.insights_id = generate_uuid()

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    update_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_updated(create_host_response, update_host_response)
    assert_host_data(actual_host=update_host_response["host"], expected_host=host)

    response_status, response_data = api_get_host(f"{HOST_URL}/{created_host_id}")

    assert_response_status(response_status, 200)

    host_response = get_host_from_response(response_data)

    assert_host_data(actual_host=host_response, expected_host=host, expected_id=created_host_id)


def test_create_with_branch_id(api_create_or_update_host):
    host = minimal_host()

    multi_response_status, multi_response_data = api_create_or_update_host(
        [host], query_parameters={"branch_id": "1234"}
    )

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)


def test_create_host_update_with_same_insights_id_and_different_canonical_facts(
    api_create_or_update_host, api_get_host
):
    original_insights_id = generate_uuid()

    host = minimal_host(
        insights_id=original_insights_id,
        rhel_machine_id=generate_uuid(),
        subscription_manager_id=generate_uuid(),
        satellite_id=generate_uuid(),
        bios_uuid=generate_uuid(),
        fqdn="original_fqdn",
        mac_addresses=["aa:bb:cc:dd:ee:ff"],
        external_id="abcdef",
    )

    # Create the host
    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)

    created_host_id = create_host_response["host"]["id"]

    # Change the canonical facts except for the insights_id
    host.rhel_machine_id = generate_uuid()
    host.ip_addresses = ["192.168.1.44", "10.0.0.2"]
    host.subscription_manager_id = generate_uuid()
    host.satellite_id = generate_uuid()
    host.bios_uuid = generate_uuid()
    host.fqdn = "expected_fqdn"
    host.mac_addresses = ["ff:ee:dd:cc:bb:aa"]
    host.external_id = "fedcba"
    host.facts = [{"namespace": "ns1", "facts": {"newkey": "newvalue"}}]

    # Update the host
    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    update_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_updated(create_host_response, update_host_response)

    # Retrieve the host using the id that we first received
    response_status, response_data = api_get_host(f"{HOST_URL}/{created_host_id}")

    assert_response_status(response_status, 200)

    host_response = get_host_from_response(response_data)

    assert_host_data(actual_host=host_response, expected_host=host, expected_id=created_host_id)


def test_match_host_by_elevated_id_performance(api_create_or_update_host, mocker):
    canonical_fact_query = mocker.patch(
        "lib.host_repository.canonical_fact_host_query", wraps=canonical_fact_host_query
    )
    canonical_facts_query = mocker.patch(
        "lib.host_repository.canonical_facts_host_query", wraps=canonical_facts_host_query
    )

    subscription_manager_id = generate_uuid()
    host = minimal_host(subscription_manager_id=subscription_manager_id)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)

    # Create a host with Subscription Manager ID
    insights_id = generate_uuid()
    host = minimal_host(insights_id=insights_id, subscription_manager_id=subscription_manager_id)

    mocker.resetall()

    # Update a host with Insights ID and Subscription Manager ID
    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    update_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_updated(create_host_response, update_host_response)

    expected_calls = (
        mocker.call(ACCOUNT, "insights_id", insights_id),
        mocker.call(ACCOUNT, "subscription_manager_id", subscription_manager_id),
    )
    canonical_fact_query.assert_has_calls(expected_calls)

    assert canonical_fact_query.call_count == len(expected_calls)
    canonical_facts_query.assert_not_called()


def test_create_host_with_empty_facts_display_name_then_update(api_create_or_update_host, api_get_host):
    # Create a host with empty facts, and display_name
    # then update those fields
    host = minimal_host()
    del host.display_name
    del host.facts

    # Create the host
    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)

    created_host_id = create_host_response["host"]["id"]

    # Update the facts and display name
    host.facts = copy.deepcopy(FACTS)
    host.display_name = "expected_display_name"

    # Update the hosts
    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    update_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_updated(create_host_response, update_host_response)

    response_status, response_data = api_get_host(f"{HOST_URL}/{created_host_id}")

    assert_response_status(response_status, 200)

    host_response = get_host_from_response(response_data)

    assert_host_data(actual_host=host_response, expected_host=host, expected_id=created_host_id)


def test_create_and_update_multiple_hosts_with_account_mismatch(api_create_or_update_host):
    """
    Attempt to create multiple hosts, one host has the wrong account number.
    Verify this causes an error response to be returned.
    """
    host1 = minimal_host(display_name="host1", ip_addresses=["10.0.0.1"], rhel_machine_id=generate_uuid())
    host2 = minimal_host(
        display_name="host2", account="222222", ip_addresses=["10.0.0.2"], rhel_machine_id=generate_uuid()
    )
    host_list = [host1, host2]

    # Create the host
    multi_response_status, multi_response_data = api_create_or_update_host(host_list)

    assert_response_status(multi_response_status, 207)

    assert len(host_list) == len(multi_response_data["data"])
    assert multi_response_status, multi_response_data["errors"] == 1

    assert_host_response_status(multi_response_data, 201, 0)
    assert_host_response_status(multi_response_data, 400, 1)


def test_create_host_without_canonical_facts(api_create_or_update_host):
    host = minimal_host()
    del host.insights_id
    del host.rhel_machine_id
    del host.subscription_manager_id
    del host.satellite_id
    del host.bios_uuid
    del host.ip_addresses
    del host.fqdn
    del host.mac_addresses
    del host.external_id

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    host_response = get_host_from_multi_response(multi_response_data)

    assert_error_response(host_response, expected_title="Invalid request", expected_status=400)


def test_create_host_without_account(api_create_or_update_host):
    host = minimal_host()
    del host.account

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_error_response(
        multi_response_data,
        expected_title="Bad Request",
        expected_detail="'account' is a required property - '0'",
        expected_status=400,
    )


@pytest.mark.parametrize("account", ["", "someaccount"])
def test_create_host_with_invalid_account(api_create_or_update_host, account):
    host = minimal_host(account=account)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    host_response = get_host_from_multi_response(multi_response_data)

    assert_error_response(
        host_response,
        expected_title="Bad Request",
        expected_detail="{'account': ['Length must be between 1 and 10.']}",
        expected_status=400,
    )


def test_create_host_with_mismatched_account_numbers(api_create_or_update_host):
    host = minimal_host(account=ACCOUNT[::-1])

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    host_response = get_host_from_multi_response(multi_response_data)

    assert_error_response(
        host_response,
        expected_title="Invalid request",
        expected_detail="The account number associated with the user does not match the account number associated "
        "with the host",
        expected_status=400,
    )


def _invalid_facts(key, value=None):
    invalid_facts = copy.deepcopy(FACTS)

    if value is None:
        del invalid_facts[0][key]
    else:
        invalid_facts[0][key] = value

    return invalid_facts


@pytest.mark.parametrize(
    "invalid_facts", [_invalid_facts("namespace"), _invalid_facts("facts"), _invalid_facts("namespace", "")]
)
def test_create_host_with_invalid_facts(api_create_or_update_host, invalid_facts):
    host = minimal_host(facts=invalid_facts)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_error_response(multi_response_data, expected_title="Bad Request", expected_status=400)


@pytest.mark.parametrize(
    "uuid_field", ["insights_id", "rhel_machine_id", "subscription_manager_id", "satellite_id", "bios_uuid"]
)
def test_create_host_with_invalid_uuid_field_values(api_create_or_update_host, uuid_field):
    host = minimal_host()
    setattr(host, uuid_field, "notauuid")

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    host_response = get_host_from_multi_response(multi_response_data)

    assert_error_response(host_response, expected_title="Bad Request", expected_status=400)


@pytest.mark.parametrize(
    "non_nullable_field",
    [
        "display_name",
        "account",
        "insights_id",
        "rhel_machine_id",
        "subscription_manager_id",
        "satellite_id",
        "fqdn",
        "bios_uuid",
        "ip_addresses",
        "mac_addresses",
        "external_id",
        "ansible_host",
        "stale_timestamp",
        "reporter",
    ],
)
def test_create_host_with_non_nullable_fields_as_none(api_create_or_update_host, non_nullable_field):
    # Have at least one good canonical fact set
    host = minimal_host(insights_id=generate_uuid(), rhel_machine_id=generate_uuid())
    # Set a null canonical fact
    setattr(host, non_nullable_field, None)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_error_response(multi_response_data, expected_title="Bad Request", expected_status=400)


@pytest.mark.parametrize("field", ["account", "stale_timestamp", "reporter"])
def test_create_host_without_required_fields(api_create_or_update_host, field):
    host = minimal_host()
    delattr(host, field)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_error_response(multi_response_data, expected_title="Bad Request", expected_status=400)


@pytest.mark.parametrize("valid_ip_array", [["blah"], ["1.1.1.1", "sigh"]])
def test_create_host_with_valid_ip_address(api_create_or_update_host, valid_ip_array):
    host = minimal_host(insights_id=generate_uuid(), ip_addresses=valid_ip_array)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)


@pytest.mark.parametrize("invalid_ip_array", [[], [""], ["a" * 256]])
def test_create_host_with_invalid_ip_address(api_create_or_update_host, invalid_ip_array):
    host = minimal_host(insights_id=generate_uuid(), ip_addresses=invalid_ip_array)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    host_response = get_host_from_multi_response(multi_response_data)

    assert_error_response(host_response, expected_title="Bad Request", expected_status=400)


@pytest.mark.parametrize("valid_mac_array", [["blah"], ["11:22:33:44:55:66", "blah"]])
def test_create_host_with_valid_mac_address(api_create_or_update_host, valid_mac_array):
    host = minimal_host(insights_id=generate_uuid(), mac_addresses=valid_mac_array)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)


@pytest.mark.parametrize("invalid_mac_array", [[], [""], ["11:22:33:44:55:66", "a" * 256]])
def test_create_host_with_invalid_mac_address(api_create_or_update_host, invalid_mac_array):
    host = minimal_host(insights_id=generate_uuid(), mac_addresses=invalid_mac_array)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    host_response = get_host_from_multi_response(multi_response_data)

    assert_error_response(host_response, expected_title="Bad Request", expected_status=400)


@pytest.mark.parametrize("invalid_display_name", ["", "a" * 201])
def test_create_host_with_invalid_display_name(api_create_or_update_host, invalid_display_name):
    host = minimal_host(display_name=invalid_display_name)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    host_response = get_host_from_multi_response(multi_response_data)

    assert_error_response(host_response, expected_title="Bad Request", expected_status=400)


@pytest.mark.parametrize("invalid_fqdn", ["", "a" * 256])
def test_create_host_with_invalid_fqdn(api_create_or_update_host, invalid_fqdn):
    host = minimal_host(fqdn=invalid_fqdn)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    host_response = get_host_from_multi_response(multi_response_data)

    assert_error_response(host_response, expected_title="Bad Request", expected_status=400)


@pytest.mark.parametrize("invalid_external_id", ["", "a" * 501])
def test_create_host_with_invalid_external_id(api_create_or_update_host, invalid_external_id):
    host = minimal_host(external_id=invalid_external_id)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    host_response = get_host_from_multi_response(multi_response_data)

    assert_error_response(host_response, expected_title="Bad Request", expected_status=400)


def test_create_host_with_ansible_host(api_create_or_update_host, api_get_host):
    # Create a host with ansible_host field
    host = minimal_host(ansible_host="ansible_host_" + generate_uuid())

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)

    created_host_id = create_host_response["host"]["id"]

    response_status, response_data = api_get_host(f"{HOST_URL}/{created_host_id}")

    assert_response_status(response_status, 200)

    host_response = get_host_from_response(response_data)

    assert_host_data(actual_host=host_response, expected_host=host, expected_id=created_host_id)


@pytest.mark.parametrize("ansible_host", ["ima_ansible_host_23c211af-c8eb-4575-9e54-3d86771af7f8", ""])
def test_create_host_without_ansible_host_then_update(api_create_or_update_host, api_get_host, ansible_host):
    # Create a host without ansible_host field
    # then update those fields
    host = minimal_host()
    del host.ansible_host

    # Create the host
    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    created_host_id = create_host_response["host"]["id"]

    host.ansible_host = ansible_host

    # Update the hosts
    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    update_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_updated(create_host_response, update_host_response)

    response_status, response_data = api_get_host(f"{HOST_URL}/{created_host_id}")

    assert_response_status(response_status, 200)

    host_response = get_host_from_response(response_data)

    assert_host_data(actual_host=host_response, expected_host=host, expected_id=created_host_id)


@pytest.mark.parametrize("invalid_ansible_host", ["a" * 256])
def test_create_host_with_invalid_ansible_host(api_create_or_update_host, invalid_ansible_host):
    host = minimal_host(ansible_host=invalid_ansible_host)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    host_response = get_host_from_multi_response(multi_response_data)

    assert_error_response(host_response, expected_title="Bad Request", expected_status=400)


def test_ignore_culled_host_on_update_by_canonical_facts(api_create_or_update_host):
    # Culled host
    host = minimal_host(fqdn="my awesome fqdn", facts=None, stale_timestamp=(now() - timedelta(weeks=3)).isoformat())

    # Create the host
    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)

    # Update the host
    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    update_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(update_host_response)

    assert create_host_response["host"]["id"] != update_host_response["host"]["id"]


def test_ignore_culled_host_on_update_by_elevated_id(api_create_or_update_host):
    # Culled host
    host = minimal_host(
        insights_id=generate_uuid(), facts=None, stale_timestamp=(now() - timedelta(weeks=3)).isoformat()
    )

    # Create the host
    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)

    # Update the host
    host.ip_addresses = ["10.10.0.2"]

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    update_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(update_host_response)

    assert create_host_response["host"]["id"] != update_host_response["host"]["id"]


def test_create_host_with_20_byte_mac_address(api_create_or_update_host, api_get_host):
    system_profile = {
        "network_interfaces": [{"mac_address": "00:11:22:33:44:55:66:77:88:99:aa:bb:cc:dd:ee:ff:00:11:22:33"}]
    }

    host = minimal_host(system_profile=system_profile)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)

    created_host_id = create_host_response["host"]["id"]

    response_status, response_data = api_get_host(f"{HOST_URL}/{created_host_id}")

    assert_response_status(response_status, 200)

    host_response = get_host_from_response(response_data)

    assert_host_data(actual_host=host_response, expected_host=host, expected_id=created_host_id)


def test_create_host_with_too_long_mac_address(api_create_or_update_host):
    system_profile = {
        "network_interfaces": [{"mac_address": "00:11:22:33:44:55:66:77:88:99:aa:bb:cc:dd:ee:ff:00:11:22:33:44"}]
    }

    host = minimal_host(system_profile=system_profile)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    host_response = get_host_from_multi_response(multi_response_data)

    assert_error_response(host_response, expected_title="Bad Request", expected_status=400)


@pytest.mark.parametrize(
    "sample",
    [
        {"disk_devices": [{"options": {"": "invalid"}}]},
        {"disk_devices": [{"options": {"ro": True, "uuid": "0", "": "invalid"}}]},
        {"disk_devices": [{"options": {"nested": {"uuid": "0", "": "invalid"}}}]},
        {"disk_devices": [{"options": {"ro": True}}, {"options": {"": "invalid"}}]},
    ],
)
def test_create_host_with_empty_json_key_in_system_profile(api_create_or_update_host, sample):
    host = minimal_host(system_profile=sample)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    host_response = get_host_from_multi_response(multi_response_data)

    assert_error_response(host_response, expected_title="Bad Request", expected_status=400)


@pytest.mark.parametrize(
    "facts",
    [
        [{"facts": {"": "invalid"}, "namespace": "rhsm"}],
        [{"facts": {"metadata": {"": "invalid"}}, "namespace": "rhsm"}],
        [{"facts": {"foo": "bar", "": "invalid"}, "namespace": "rhsm"}],
        [{"facts": {"foo": "bar"}, "namespace": "valid"}, {"facts": {"": "invalid"}, "namespace": "rhsm"}],
    ],
)
def test_create_host_with_empty_json_key_in_facts(api_create_or_update_host, facts):
    host = minimal_host(facts=facts)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    host_response = get_host_from_multi_response(multi_response_data)

    assert_error_response(host_response, expected_title="Bad Request", expected_status=400)


def test_create_host_without_display_name_and_without_fqdn(api_create_or_update_host, api_get_host):
    """
    This test should verify that the display_name is set to the id
    when neither the display name or fqdn is set.
    """
    host = minimal_host()
    del host.display_name
    del host.fqdn

    # Create the host
    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)

    created_host_id = create_host_response["host"]["id"]

    response_status, response_data = api_get_host(f"{HOST_URL}/{created_host_id}")

    assert_response_status(response_status, 200)

    host_response = get_host_from_response(response_data)

    assert_host_data(actual_host=host_response, expected_host=host, expected_id=created_host_id)


def test_create_host_without_display_name_and_with_fqdn(api_create_or_update_host, api_get_host):
    """
    This test should verify that the display_name is set to the
    fqdn when a display_name is not passed in but the fqdn is passed in.
    """
    expected_display_name = "fred.flintstone.bedrock.com"

    host = minimal_host(fqdn=expected_display_name)
    del host.display_name

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)

    created_host_id = create_host_response["host"]["id"]

    response_status, response_data = api_get_host(f"{HOST_URL}/{created_host_id}")

    assert_response_status(response_status, 200)

    host_response = get_host_from_response(response_data)

    host.display_name = expected_display_name

    assert_host_data(actual_host=host_response, expected_host=host, expected_id=created_host_id)


@pytest.mark.bulk_creation
def test_create_and_update_multiple_hosts_with_different_accounts(api_create_or_update_host, monkeypatch):
    monkeypatch.setenv("INVENTORY_SHARED_SECRET", SHARED_SECRET)

    host1 = minimal_host(
        display_name="host1", account="111111", ip_addresses=["10.0.0.1"], rhel_machine_id=generate_uuid()
    )
    host2 = minimal_host(
        display_name="host2", account="222222", ip_addresses=["10.0.0.2"], rhel_machine_id=generate_uuid()
    )
    host_list = [host1, host2]

    # Create the host
    multi_response_status, multi_response_data = api_create_or_update_host(host_list, auth_type="token")

    assert_response_status(multi_response_status, 207)

    assert len(host_list) == len(multi_response_data["data"])
    assert multi_response_data["total"] == len(multi_response_data["data"])
    assert multi_response_status, multi_response_data["errors"] == 0

    for i, host in enumerate(host_list):
        create_host_response = get_host_from_multi_response(multi_response_data, host_index=i)

        assert_host_was_created(create_host_response)

        host_list[i].id = create_host_response["host"]["id"]

    host_list[0].bios_uuid = generate_uuid()
    host_list[0].display_name = "fred"

    host_list[1].bios_uuid = generate_uuid()
    host_list[1].display_name = "barney"

    # Update the host
    multi_response_status, multi_response_data = api_create_or_update_host(host_list, auth_type="token")

    assert_response_status(multi_response_status, 207)

    for i, host in enumerate(host_list):
        update_host_response = get_host_from_multi_response(multi_response_data, host_index=i)

        assert_host_response_status(update_host_response, expected_status=200)
        assert_host_data(
            actual_host=update_host_response["host"], expected_host=host_list[i], expected_id=host_list[i].id
        )


@pytest.mark.system_profile
def test_create_host_with_system_profile(api_create_or_update_host, api_get_host):
    host = minimal_host(system_profile=valid_system_profile())

    # Create the host
    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)

    created_host = create_host_response["host"]

    # verify system_profile is not included
    assert "system_profile" not in created_host

    response_status, response_data = api_get_host(f"{HOST_URL}/{created_host['id']}/system_profile")

    assert_response_status(response_status, 200)

    host_response = get_host_from_response(response_data)

    assert host_response["id"] == created_host["id"]
    assert host_response["system_profile"] == host.system_profile


@pytest.mark.system_profile
def test_create_host_with_system_profile_and_query_with_branch_id(api_create_or_update_host, api_get_host):
    host = minimal_host(system_profile=valid_system_profile())

    # Create the host
    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)

    created_host = create_host_response["host"]

    # verify system_profile is not included
    assert "system_profile" not in created_host

    response_status, response_data = api_get_host(
        f"{HOST_URL}/{created_host['id']}/system_profile", query_parameters={"branch_id": 1234}
    )

    assert_response_status(response_status, 200)

    host_response = get_host_from_response(response_data)

    assert host_response["id"] == created_host["id"]
    assert host_response["system_profile"] == host.system_profile


@pytest.mark.system_profile
def test_create_host_with_null_system_profile(api_create_or_update_host):
    host = minimal_host(system_profile=None)

    # Create the host without a system profile
    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_error_response(multi_response_data, expected_title="Bad Request", expected_status=400)


@pytest.mark.system_profile
@pytest.mark.parametrize(
    "system_profile",
    [{"infrastructure_type": "i" * 101, "infrastructure_vendor": "i" * 101, "cloud_provider": "i" * 101}],
)
def test_create_host_with_system_profile_with_invalid_data(api_create_or_update_host, api_get_host, system_profile):
    host = minimal_host(system_profile=system_profile)

    # Create the host
    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    host_response = get_host_from_multi_response(multi_response_data)

    assert_error_response(host_response, expected_title="Bad Request", expected_status=400)


@pytest.mark.system_profile
@pytest.mark.parametrize(
    "yum_url",
    [
        "file:///cdrom/",
        "http://foo.com http://foo.com",
        "file:///etc/pki/rpm-gpg/RPM-GPG-KEY-fedora-$releasever-$basearch",
        "https://codecs.fedoraproject.org/openh264/$releasever/$basearch/debug/",
    ],
)
def test_create_host_with_system_profile_with_different_yum_urls(api_create_or_update_host, api_get_host, yum_url):
    system_profile = {"yum_repos": [{"name": "repo1", "gpgcheck": True, "enabled": True, "base_url": yum_url}]}
    host = minimal_host(system_profile=system_profile)

    # Create the host
    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)

    created_host = create_host_response["host"]

    # verify system_profile is not included
    assert "system_profile" not in created_host

    response_status, response_data = api_get_host(f"{HOST_URL}/{created_host['id']}/system_profile")

    assert_response_status(response_status, 200)

    host_response = get_host_from_response(response_data)

    assert host_response["id"] == created_host["id"]
    assert host_response["system_profile"] == host.system_profile


@pytest.mark.system_profile
@pytest.mark.parametrize("cloud_provider", ["cumulonimbus", "cumulus", "c" * 100])
def test_create_host_with_system_profile_with_different_cloud_providers(
    api_create_or_update_host, api_get_host, cloud_provider
):
    host = minimal_host(system_profile={"cloud_provider": cloud_provider})

    # Create the host
    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)

    created_host = create_host_response["host"]

    # verify system_profile is not included
    assert "system_profile" not in created_host

    response_status, response_data = api_get_host(f"{HOST_URL}/{created_host['id']}/system_profile")

    assert_response_status(response_status, 200)

    host_response = get_host_from_response(response_data)

    assert host_response["id"] == created_host["id"]
    assert host_response["system_profile"] == host.system_profile


@pytest.mark.system_profile
def test_get_system_profile_of_host_that_does_not_have_system_profile(api_create_or_update_host, api_get_host):
    host = minimal_host()

    # Create the host
    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)

    created_host = create_host_response["host"]

    # verify system_profile is not included
    assert "system_profile" not in created_host

    response_status, response_data = api_get_host(f"{HOST_URL}/{created_host['id']}/system_profile")

    assert_response_status(response_status, 200)

    host_response = get_host_from_response(response_data)

    assert host_response["id"] == created_host["id"]
    assert host_response["system_profile"] == {}


@pytest.mark.system_profile
def test_get_system_profile_of_multiple_hosts(api_create_or_update_host, api_get_host):
    host_id_list = []
    expected_system_profiles = []

    for i in range(2):
        system_profile = valid_system_profile()
        system_profile["number_of_cpus"] = i

        host = minimal_host(ip_addresses=[f"10.0.0.{i}"], system_profile=system_profile)

        multi_response_status, multi_response_data = api_create_or_update_host([host])

        assert_response_status(multi_response_status, 207)

        create_host_response = get_host_from_multi_response(multi_response_data)

        assert_host_was_created(create_host_response)

        created_host_id = create_host_response["host"]["id"]

        host_id_list.append(created_host_id)
        expected_system_profiles.append({"id": created_host_id, "system_profile": host.system_profile})

    url_host_id_list = ",".join(host_id_list)
    test_url = f"{HOST_URL}/{url_host_id_list}/system_profile"

    response_status, response_data = api_get_host(test_url)

    assert_response_status(response_status, 200)

    assert len(expected_system_profiles) == len(response_data["results"])
    for expected_system_profile in expected_system_profiles:
        assert expected_system_profile in response_data["results"]

    # TODO: Move to a separate pagination test
    # paging_test(test_url, len(expected_system_profiles))
    # invalid_paging_parameters_test(test_url)


@pytest.mark.system_profile
def test_get_system_profile_of_host_that_does_not_exist(api_get_host):
    expected_count = 0
    expected_total = 0
    host_id = generate_uuid()

    response_status, response_data = api_get_host(f"{HOST_URL}/{host_id}/system_profile")

    assert_response_status(response_status, 200)

    assert response_data["count"] == expected_count
    assert response_data["total"] == expected_total


@pytest.mark.system_profile
@pytest.mark.parametrize("invalid_host_id", ["notauuid", "922680d3-4aa2-4f0e-9f39-38ab8ea318bb,notuuid"])
def test_get_system_profile_with_invalid_host_id(api_get_host, invalid_host_id):
    response_status, response_data = api_get_host(f"{HOST_URL}/{invalid_host_id}/system_profile")

    assert_error_response(response_data, expected_title="Bad Request", expected_status=400)


@pytest.mark.tagging
def test_create_host_with_null_tags(api_create_or_update_host):
    host = minimal_host(tags=None)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_error_response(multi_response_data, expected_title="Bad Request", expected_status=400)


@pytest.mark.tagging
def test_create_host_with_null_tag_key(api_create_or_update_host):
    host = minimal_host(tags=[({"namespace": "ns", "key": None, "value": "val"},)])

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_error_response(multi_response_data, expected_title="Bad Request", expected_status=400)


@pytest.mark.tagging
@pytest.mark.parametrize(
    "tag",
    [
        {"namespace": "a" * 256, "key": "key", "value": "val"},
        {"namespace": "ns", "key": "a" * 256, "value": "val"},
        {"namespace": "ns", "key": "key", "value": "a" * 256},
        {"namespace": "ns", "key": "", "value": "val"},
        {"namespace": "ns", "value": "val"},
    ],
)
def test_create_host_with_invalid_tags(api_create_or_update_host, tag):
    host = minimal_host(tags=[tag])

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    host_response = get_host_from_multi_response(multi_response_data)

    assert_error_response(host_response, expected_title="Bad Request", expected_status=400)


@pytest.mark.tagging
def test_create_host_with_keyless_tag(api_create_or_update_host):
    host = minimal_host(tags=[{"namespace": "ns", "key": None, "value": "val"}])

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_error_response(multi_response_data, expected_title="Bad Request", expected_status=400)


@pytest.mark.tagging
def test_create_host_with_invalid_string_tag_format(api_create_or_update_host):
    host = minimal_host(tags=["string/tag=format"])

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_error_response(multi_response_data, expected_title="Bad Request", expected_status=400)


@pytest.mark.tagging
def test_create_host_with_invalid_tag_format(api_create_or_update_host):
    host = minimal_host(tags=[{"namespace": "spam", "key": {"foo": "bar"}, "value": "eggs"}])

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_error_response(multi_response_data, expected_title="Bad Request", expected_status=400)


@pytest.mark.tagging
def test_create_host_with_tags(api_create_or_update_host, api_get_host):
    host = minimal_host(
        tags=[
            {"namespace": "NS3", "key": "key2", "value": "val2"},
            {"namespace": "NS1", "key": "key3", "value": "val3"},
            {"namespace": "Sat", "key": "prod", "value": None},
            {"namespace": "NS2", "key": "key1", "value": ""},
        ]
    )

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)

    created_host_id = create_host_response["host"]["id"]

    response_status, response_data = api_get_host(f"{HOST_URL}/{created_host_id}")

    assert_response_status(response_status, 200)

    host_response = get_host_from_response(response_data)

    assert_host_data(actual_host=host_response, expected_host=host, expected_id=created_host_id)

    host_tags_response_status, host_tags_response_data = api_get_host(f"{HOST_URL}/{created_host_id}/tags")

    assert_response_status(host_tags_response_status, 200)

    host_tags = host_tags_response_data["results"][created_host_id]

    expected_tags = [
        {"namespace": "NS1", "key": "key3", "value": "val3"},
        {"namespace": "NS3", "key": "key2", "value": "val2"},
        {"namespace": "Sat", "key": "prod", "value": None},
        {"namespace": "NS2", "key": "key1", "value": None},
    ]

    assert len(host_tags) == len(expected_tags)


@pytest.mark.tagging
def test_create_host_with_tags_special_characters(api_create_or_update_host, api_get_host):
    tags = [
        {"namespace": "NS1;,/?:@&=+$-_.!~*'()#", "key": "ŠtěpánΔ12!@#$%^&*()_+-=", "value": "ŠtěpánΔ:;'|,./?~`"},
        {"namespace": " \t\n\r\f\v", "key": " \t\n\r\f\v", "value": " \t\n\r\f\v"},
    ]
    host = minimal_host(tags=tags)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)

    created_host_id = create_host_response["host"]["id"]

    response_status, response_data = api_get_host(f"{HOST_URL}/{created_host_id}")

    assert_response_status(response_status, 200)

    host_response = get_host_from_response(response_data)

    assert_host_data(actual_host=host_response, expected_host=host, expected_id=created_host_id)

    host_tags_response_status, host_tags_response_data = api_get_host(f"{HOST_URL}/{created_host_id}/tags")

    assert_response_status(host_tags_response_status, 200)

    host_tags = host_tags_response_data["results"][created_host_id]

    assert len(host_tags) == len(tags)


@pytest.mark.tagging
def test_create_host_with_tag_without_some_fields(api_create_or_update_host, api_get_host):
    tags = [
        {"namespace": None, "key": "key3", "value": "val3"},
        {"namespace": "", "key": "key1", "value": "val1"},
        {"namespace": "null", "key": "key4", "value": "val4"},
        {"key": "key2", "value": "val2"},
        {"namespace": "Sat", "key": "prod", "value": None},
        {"namespace": "Sat", "key": "dev", "value": ""},
        {"key": "some_key"},
    ]

    host = minimal_host(tags=tags)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)

    created_host_id = create_host_response["host"]["id"]

    response_status, response_data = api_get_host(f"{HOST_URL}/{created_host_id}")

    assert_response_status(response_status, 200)

    host_response = get_host_from_response(response_data)

    assert_host_data(actual_host=host_response, expected_host=host, expected_id=created_host_id)

    host_tags_response_status, host_tags_response_data = api_get_host(f"{HOST_URL}/{created_host_id}/tags")

    assert_response_status(host_tags_response_status, 200)

    host_tags = host_tags_response_data["results"][created_host_id]

    expected_tags = [
        {"namespace": "Sat", "key": "prod", "value": None},
        {"namespace": "Sat", "key": "dev", "value": None},
        {"namespace": None, "key": "key1", "value": "val1"},
        {"namespace": None, "key": "key2", "value": "val2"},
        {"namespace": None, "key": "key3", "value": "val3"},
        {"namespace": None, "key": "key4", "value": "val4"},
        {"namespace": None, "key": "some_key", "value": None},
    ]

    assert len(host_tags) == len(expected_tags)


@pytest.mark.tagging
def test_update_host_replaces_tags(api_create_or_update_host, api_get_host):
    insights_id = generate_uuid()

    create_tags = [
        {"namespace": "namespace1", "key": "key1", "value": "value1"},
        {"namespace": "namespace1", "key": "key2", "value": "value2"},
    ]

    host = minimal_host(insights_id=insights_id, tags=create_tags)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)

    created_host_id = create_host_response["host"]["id"]

    host_tags_response_status, host_tags_response_data = api_get_host(f"{HOST_URL}/{created_host_id}/tags")

    assert_response_status(host_tags_response_status, 200)

    created_host_tags = host_tags_response_data["results"][created_host_id]

    assert len(created_host_tags) == len(create_tags)

    update_tags = [
        {"namespace": "namespace1", "key": "key2", "value": "value3"},
        {"namespace": "namespace1", "key": "key3", "value": "value4"},
    ]

    host = minimal_host(insights_id=insights_id, tags=update_tags)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    update_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_updated(create_host_response, update_host_response)

    host_tags_response_status, host_tags_response_data = api_get_host(f"{HOST_URL}/{created_host_id}/tags")

    assert_response_status(host_tags_response_status, 200)

    updated_host_tags = host_tags_response_data["results"][created_host_id]

    assert len(updated_host_tags) == len(update_tags)


@pytest.mark.tagging
def test_update_host_does_not_remove_namespace(api_create_or_update_host, api_get_host):
    insights_id = generate_uuid()
    create_tags = [{"namespace": "namespace1", "key": "key1", "value": "value1"}]

    host = minimal_host(insights_id=insights_id, tags=create_tags)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)

    created_host_id = create_host_response["host"]["id"]

    host_tags_response_status, host_tags_response_data = api_get_host(f"{HOST_URL}/{created_host_id}/tags")

    assert_response_status(host_tags_response_status, 200)

    created_host_tags = host_tags_response_data["results"][created_host_id]

    assert len(created_host_tags) == len(create_tags)

    update_tags = [{"namespace": "namespace2", "key": "key2", "value": "value3"}]

    host = minimal_host(insights_id=insights_id, tags=update_tags)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    update_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_updated(create_host_response, update_host_response)

    host_tags_response_status, host_tags_response_data = api_get_host(f"{HOST_URL}/{created_host_id}/tags")

    assert_response_status(host_tags_response_status, 200)

    updated_host_tags = host_tags_response_data["results"][created_host_id]

    assert len(updated_host_tags) == len(create_tags) + len(update_tags)


@pytest.mark.tagging
def test_create_host_with_nested_tags(api_create_or_update_host):
    host = minimal_host(tags={"namespace": {"key": ["value"]}})

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_error_response(multi_response_data, expected_title="Bad Request", expected_status=400)


@pytest.mark.system_culling
@pytest.mark.parametrize("fields_to_delete", [("stale_timestamp", "reporter"), ("stale_timestamp",), ("reporter",)])
def test_create_host_without_culling_fields(api_create_or_update_host, fields_to_delete):
    host = minimal_host(fqdn="match this host")
    for field in fields_to_delete:
        delattr(host, field)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_error_response(multi_response_data, expected_title="Bad Request", expected_status=400)


@pytest.mark.system_culling
@pytest.mark.parametrize("culling_fields", [("stale_timestamp",), ("reporter",), ("stale_timestamp", "reporter")])
def test_create_host_with_null_culling_fields(api_create_or_update_host, culling_fields):
    host = minimal_host(fqdn="match this host", **{field: None for field in culling_fields})

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_error_response(multi_response_data, expected_title="Bad Request", expected_status=400)


@pytest.mark.system_culling
@pytest.mark.parametrize("culling_fields", [("stale_timestamp",), ("reporter",), ("stale_timestamp", "reporter")])
def test_create_host_with_empty_culling_fields(api_create_or_update_host, culling_fields):
    host = minimal_host(**{field: "" for field in culling_fields})

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    host_response = get_host_from_multi_response(multi_response_data)

    assert_error_response(host_response, expected_title="Bad Request", expected_status=400)


@pytest.mark.system_culling
def test_create_host_with_invalid_stale_timestamp(api_create_or_update_host):
    host = minimal_host(stale_timestamp="not a timestamp")

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    host_response = get_host_from_multi_response(multi_response_data)

    assert_error_response(host_response, expected_title="Bad Request", expected_status=400)


@pytest.mark.system_culling
def test_create_host_with_stale_timestamp_and_reporter(api_create_or_update_host, get_host_from_db):
    stale_timestamp = now()
    reporter = "some reporter"

    host = minimal_host(stale_timestamp=stale_timestamp.isoformat(), reporter=reporter)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)

    created_host_id = create_host_response["host"]["id"]

    retrieved_host = get_host_from_db(created_host_id)

    assert stale_timestamp == retrieved_host.stale_timestamp
    assert reporter == retrieved_host.reporter


@pytest.mark.system_culling
@pytest.mark.parametrize("new_stale_timestamp,new_reporter", [
    (now() + timedelta(days=3), "old reporter"),
    (now() + timedelta(days=3), "new reporter"),
    (now() + timedelta(days=1), "old reporter"),
    (now() + timedelta(days=1), "new reporter"),
])
def test_always_update_stale_timestamp_from_next_reporter(api_create_or_update_host, get_host_from_db, new_stale_timestamp, new_reporter):
    old_stale_timestamp = now() + timedelta(days=2)
    old_reporter = "old reporter"

    host = minimal_host(stale_timestamp=old_stale_timestamp.isoformat(), reporter=old_reporter)

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    create_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_created(create_host_response)

    created_host_id = create_host_response["host"]["id"]

    retrieved_host = get_host_from_db(created_host_id)

    assert old_stale_timestamp == retrieved_host.stale_timestamp
    assert old_reporter == retrieved_host.reporter

    host.stale_timestamp = new_stale_timestamp.isoformat()
    host.reporter = new_reporter

    multi_response_status, multi_response_data = api_create_or_update_host([host])

    assert_response_status(multi_response_status, 207)

    update_host_response = get_host_from_multi_response(multi_response_data)

    assert_host_was_updated(create_host_response, update_host_response)

    retrieved_host = get_host_from_db(created_host_id)

    assert new_stale_timestamp == retrieved_host.stale_timestamp
    assert new_reporter == retrieved_host.reporter
