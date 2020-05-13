#!/usr/bin/env python
import copy
from datetime import datetime
from datetime import timedelta
from datetime import timezone

import dateutil.parser
import pytest

from app.utils import HostWrapper
from lib.host_repository import canonical_fact_host_query
from lib.host_repository import canonical_facts_host_query
from tests.test_utils import ACCOUNT
from tests.test_utils import FACTS
from tests.test_utils import generate_uuid
from tests.test_utils import HOST_URL
from tests.test_utils import now
from tests.test_utils import test_data
from tests.test_utils import valid_system_profile
from tests.test_utils import validate_host
from tests.test_utils import verify_error_response


def test_create_and_update(create_or_update_host, get_host):
    facts = None
    host_data = HostWrapper(test_data(facts=facts))
    created_host = create_or_update_host(host_data)

    original_id = created_host["id"]

    created_time = dateutil.parser.parse(created_host["created"])
    current_timestamp = datetime.now(timezone.utc)
    assert current_timestamp > created_time
    assert (current_timestamp - timedelta(minutes=15)) < created_time

    host_data.facts = copy.deepcopy(FACTS)

    # Replace facts under the first namespace
    host_data.facts[0]["facts"] = {"newkey1": "newvalue1"}

    # Add a new set of facts under a new namespace
    host_data.facts.append({"namespace": "ns2", "facts": {"key2": "value2"}})

    # Add a new canonical fact
    host_data.rhel_machine_id = generate_uuid()
    host_data.ip_addresses = ["10.10.0.1", "10.0.0.2", "fe80::d46b:2807:f258:c319"]
    host_data.mac_addresses = ["c2:00:d0:c8:61:01"]
    host_data.external_id = "i-05d2313e6b9a42b16"
    host_data.insights_id = generate_uuid()

    updated_host = create_or_update_host(host_data, host_status=200)

    assert updated_host["id"] == original_id
    assert updated_host["updated"] is not None
    modified_time = dateutil.parser.parse(updated_host["updated"])
    assert modified_time > created_time

    host_lookup_results = get_host(f"{HOST_URL}/{original_id}")

    validate_host(host_lookup_results["results"][0], host_data, original_id)


def test_create_with_branch_id(create_or_update_host):
    facts = None
    host_data = HostWrapper(test_data(facts=facts))

    post_url = f"{HOST_URL}?branch_id=1234"
    create_or_update_host(host_data, url=post_url)


def test_create_host_update_with_same_insights_id_and_different_canonical_facts(create_or_update_host, get_host):
    original_insights_id = generate_uuid()

    host_data = HostWrapper(test_data(facts=None))
    host_data.insights_id = original_insights_id
    host_data.rhel_machine_id = generate_uuid()
    host_data.subscription_manager_id = generate_uuid()
    host_data.satellite_id = generate_uuid()
    host_data.bios_uuid = generate_uuid()
    host_data.fqdn = "original_fqdn"
    host_data.mac_addresses = ["aa:bb:cc:dd:ee:ff"]
    host_data.external_id = "abcdef"

    # Create the host
    created_host = create_or_update_host(host_data)
    original_id = created_host["id"]

    # Change the canonical facts except for the insights_id
    host_data.rhel_machine_id = generate_uuid()
    host_data.ip_addresses = ["192.168.1.44", "10.0.0.2"]
    host_data.subscription_manager_id = generate_uuid()
    host_data.satellite_id = generate_uuid()
    host_data.bios_uuid = generate_uuid()
    host_data.fqdn = "expected_fqdn"
    host_data.mac_addresses = ["ff:ee:dd:cc:bb:aa"]
    host_data.external_id = "fedcba"
    host_data.facts = [{"namespace": "ns1", "facts": {"newkey": "newvalue"}}]

    # Update the host
    updated_host = create_or_update_host(host_data, host_status=200)

    # Verify that the id did not change on the update
    assert updated_host["id"] == original_id

    # Retrieve the host using the id that we first received
    data = get_host(f"{HOST_URL}/{original_id}")

    validate_host(data["results"][0], host_data, original_id)


def test_match_host_by_elevated_id_performance(create_or_update_host, mocker):
    canonical_fact_query = mocker.patch(
        "lib.host_repository.canonical_fact_host_query", wraps=canonical_fact_host_query
    )
    canonical_facts_query = mocker.patch(
        "lib.host_repository.canonical_facts_host_query", wraps=canonical_facts_host_query
    )

    subscription_manager_id = generate_uuid()
    host_data = HostWrapper(test_data(subscription_manager_id=subscription_manager_id))

    create_or_update_host(host_data)

    # Create a host with Subscription Manager ID
    insights_id = generate_uuid()
    host_data = HostWrapper(test_data(insights_id=insights_id, subscription_manager_id=subscription_manager_id))

    mocker.resetall()

    # Update a host with Insights ID and Subscription Manager ID
    create_or_update_host(host_data, host_status=200)

    expected_calls = (
        mocker.call(ACCOUNT, "insights_id", insights_id),
        mocker.call(ACCOUNT, "subscription_manager_id", subscription_manager_id),
    )
    canonical_fact_query.assert_has_calls(expected_calls)

    assert canonical_fact_query.call_count == len(expected_calls)
    canonical_facts_query.assert_not_called()


def test_create_host_with_empty_facts_display_name_then_update(create_or_update_host, get_host):
    # Create a host with empty facts, and display_name
    # then update those fields
    host_data = HostWrapper(test_data(facts=None))
    del host_data.display_name
    del host_data.facts

    # Create the host
    created_host = create_or_update_host(host_data)
    original_id = created_host["id"]

    # Update the facts and display name
    host_data.facts = copy.deepcopy(FACTS)
    host_data.display_name = "expected_display_name"

    # Update the hosts
    create_or_update_host(host_data, host_status=200)

    host_lookup_results = get_host(f"{HOST_URL}/{original_id}")
    validate_host(host_lookup_results["results"][0], host_data, expected_id=original_id)


def test_create_and_update_multiple_hosts_with_account_mismatch(create_or_update_host):
    """
    Attempt to create multiple hosts, one host has the wrong account number.
    Verify this causes an error response to be returned.
    """
    facts = None

    host1 = HostWrapper(test_data(display_name="host1", facts=facts))
    host1.ip_addresses = ["10.0.0.1"]
    host1.rhel_machine_id = generate_uuid()

    host2 = HostWrapper(test_data(display_name="host2", facts=facts))
    # Set the account number to the wrong account for this request
    host2.account = "222222"
    host2.ip_addresses = ["10.0.0.2"]
    host2.rhel_machine_id = generate_uuid()

    host_list = [host1, host2]

    # Create the host
    response = create_or_update_host(host_list, skip_host_validation=True)

    assert len(host_list) == len(response["data"])

    assert response["errors"] == 1

    assert response["data"][0]["status"] == 201
    assert response["data"][1]["status"] == 400


def test_create_host_without_canonical_facts(create_or_update_host):
    host_data = HostWrapper(test_data(facts=None))
    del host_data.insights_id
    del host_data.rhel_machine_id
    del host_data.subscription_manager_id
    del host_data.satellite_id
    del host_data.bios_uuid
    del host_data.ip_addresses
    del host_data.fqdn
    del host_data.mac_addresses
    del host_data.external_id

    response = create_or_update_host(host_data, skip_host_validation=True)

    verify_error_response(response["data"][0], expected_title="Invalid request", expected_status=400)


def test_create_host_without_account(create_or_update_host):
    host_data = HostWrapper(test_data(facts=None))
    del host_data.account

    response = create_or_update_host(host_data, status=400)

    verify_error_response(
        response, expected_title="Bad Request", expected_detail="'account' is a required property - '0'"
    )


@pytest.mark.parametrize("account", ["", "someaccount"])
def test_create_host_with_invalid_account(create_or_update_host, account):
    host_data = HostWrapper(test_data(account=account, facts=None))

    response = create_or_update_host(host_data, status=207, skip_host_validation=True)

    verify_error_response(
        response["data"][0],
        expected_title="Bad Request",
        expected_detail="{'account': ['Length must be between 1 and 10.']}",
        expected_status=400,
    )


def test_create_host_with_mismatched_account_numbers(create_or_update_host):
    host_data = HostWrapper(test_data(facts=None))
    host_data.account = ACCOUNT[::-1]

    response = create_or_update_host(host_data, status=207, skip_host_validation=True)

    verify_error_response(
        response["data"][0],
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
def test_create_host_with_invalid_facts(create_or_update_host, invalid_facts):
    host_data = HostWrapper(test_data(facts=invalid_facts))

    response = create_or_update_host(host_data, status=400)

    verify_error_response(response, expected_title="Bad Request")


@pytest.mark.parametrize(
    "uuid_field", ["insights_id", "rhel_machine_id", "subscription_manager_id", "satellite_id", "bios_uuid"]
)
def test_create_host_with_invalid_uuid_field_values(create_or_update_host, uuid_field):
    host_data = HostWrapper(test_data(facts=None))
    setattr(host_data, uuid_field, "notauuid")

    response = create_or_update_host(host_data, skip_host_validation=True)

    verify_error_response(response["data"][0], expected_title="Bad Request", expected_status=400)


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
def test_create_host_with_non_nullable_fields_as_none(create_or_update_host, non_nullable_field):
    host_data = HostWrapper(test_data(facts=None))

    # Have at least one good canonical fact set
    host_data.insights_id = generate_uuid()
    host_data.rhel_machine_id = generate_uuid()

    setattr(host_data, non_nullable_field, None)

    response = create_or_update_host(host_data, status=400)

    verify_error_response(response, expected_title="Bad Request", expected_status=400)


@pytest.mark.parametrize("field", ["account", "stale_timestamp", "reporter"])
def test_create_host_without_required_fields(create_or_update_host, field):
    data = test_data()
    del data[field]

    host_data = HostWrapper(data)

    response = create_or_update_host(host_data, status=400)
    verify_error_response(response, expected_title="Bad Request", expected_status=400)


@pytest.mark.parametrize("valid_ip_array", [["blah"], ["1.1.1.1", "sigh"]])
def test_create_host_with_valid_ip_address(create_or_update_host, valid_ip_array):
    host_data = HostWrapper(test_data(facts=None))
    host_data.insights_id = generate_uuid()
    host_data.ip_addresses = valid_ip_array

    create_or_update_host(host_data, status=207, host_status=201)


@pytest.mark.parametrize("invalid_ip_array", [[], [""], ["a" * 256]])
def test_create_host_with_invalid_ip_address(create_or_update_host, invalid_ip_array):
    host_data = HostWrapper(test_data(facts=None))
    host_data.insights_id = generate_uuid()
    host_data.ip_addresses = invalid_ip_array

    response = create_or_update_host(host_data, status=207, skip_host_validation=True)

    verify_error_response(response["data"][0], expected_title="Bad Request", expected_status=400)


@pytest.mark.parametrize("valid_mac_array", [["blah"], ["11:22:33:44:55:66", "blah"]])
def test_create_host_with_valid_mac_address(create_or_update_host, valid_mac_array):
    host_data = HostWrapper(test_data(facts=None))
    host_data.insights_id = generate_uuid()
    host_data.mac_addresses = valid_mac_array

    create_or_update_host(host_data, status=207, host_status=201)


@pytest.mark.parametrize("invalid_mac_array", [[], [""], ["11:22:33:44:55:66", "a" * 256]])
def test_create_host_with_invalid_mac_address(create_or_update_host, invalid_mac_array):
    host_data = HostWrapper(test_data(facts=None))
    host_data.insights_id = generate_uuid()
    host_data.mac_addresses = invalid_mac_array

    response = create_or_update_host(host_data, status=207, skip_host_validation=True)

    verify_error_response(response["data"][0], expected_title="Bad Request", expected_status=400)


@pytest.mark.parametrize("invalid_display_name", ["", "a" * 201])
def test_create_host_with_invalid_display_name(create_or_update_host, invalid_display_name):
    host_data = HostWrapper(test_data(facts=None))
    host_data.display_name = invalid_display_name

    response = create_or_update_host(host_data, status=207, skip_host_validation=True)

    verify_error_response(response["data"][0], expected_title="Bad Request", expected_status=400)


@pytest.mark.parametrize("invalid_fqdn", ["", "a" * 256])
def test_create_host_with_invalid_fqdn(create_or_update_host, invalid_fqdn):
    host_data = HostWrapper(test_data(facts=None))
    host_data.fqdn = invalid_fqdn

    response = create_or_update_host(host_data, status=207, skip_host_validation=True)

    verify_error_response(response["data"][0], expected_title="Bad Request", expected_status=400)


@pytest.mark.parametrize("invalid_external_id", ["", "a" * 501])
def test_create_host_with_invalid_external_id(create_or_update_host, invalid_external_id):
    host_data = HostWrapper(test_data(facts=None))
    host_data.external_id = invalid_external_id

    response = create_or_update_host(host_data, status=207, skip_host_validation=True)

    verify_error_response(response["data"][0], expected_title="Bad Request", expected_status=400)


def test_create_host_with_ansible_host(create_or_update_host, get_host):
    # Create a host with ansible_host field
    host_data = HostWrapper(test_data(facts=None))
    host_data.ansible_host = "ansible_host_" + generate_uuid()

    # Create the host
    created_host = create_or_update_host(host_data, status=207, host_status=201)

    original_id = created_host["id"]

    host_lookup_results = get_host(f"{HOST_URL}/{original_id}", 200)

    validate_host(host_lookup_results["results"][0], host_data, expected_id=original_id)


@pytest.mark.parametrize("ansible_host", ["ima_ansible_host_" + generate_uuid(), ""])
def test_create_host_without_ansible_host_then_update(create_or_update_host, get_host, ansible_host):
    # Create a host without ansible_host field
    # then update those fields
    host_data = HostWrapper(test_data(facts=None))
    del host_data.ansible_host

    # Create the host
    created_host = create_or_update_host(host_data, status=207, host_status=201)

    original_id = created_host["id"]

    host_data.ansible_host = ansible_host

    # Update the hosts
    create_or_update_host(host_data, status=207, host_status=200)

    host_lookup_results = get_host(f"{HOST_URL}/{original_id}", 200)

    validate_host(host_lookup_results["results"][0], host_data, expected_id=original_id)


@pytest.mark.parametrize("invalid_ansible_host", ["a" * 256])
def test_create_host_with_invalid_ansible_host(create_or_update_host, invalid_ansible_host):
    host_data = HostWrapper(test_data(facts=None))
    host_data.ansible_host = invalid_ansible_host

    response = create_or_update_host(host_data, status=207, skip_host_validation=True)

    verify_error_response(response["data"][0], expected_title="Bad Request", expected_status=400)


def test_ignore_culled_host_on_update_by_canonical_facts(create_or_update_host):
    # Culled host
    host_data = HostWrapper(
        test_data(fqdn="my awesome fqdn", facts=None, stale_timestamp=(now() - timedelta(weeks=3)).isoformat())
    )

    # Create the host
    created_host = create_or_update_host(host_data, status=207, host_status=201)

    # Update the host
    updated_host = create_or_update_host(host_data, status=207, host_status=201)

    assert created_host["id"] != updated_host["id"]


def test_ignore_culled_host_on_update_by_elevated_id(create_or_update_host):
    # Culled host
    host_to_create_data = HostWrapper(
        test_data(insights_id=generate_uuid(), facts=None, stale_timestamp=(now() - timedelta(weeks=3)).isoformat())
    )

    # Create the host
    created_host = create_or_update_host(host_to_create_data, status=207, host_status=201)

    # Update the host
    host_to_update_data = host_to_create_data
    host_to_update_data.ip_addresses = ["10.10.0.2"]
    updated_host = create_or_update_host(host_to_update_data, status=207, host_status=201)

    assert created_host["id"] != updated_host["id"]


def test_create_host_with_20_byte_mac_address(create_or_update_host, get_host):
    system_profile = {
        "network_interfaces": [{"mac_address": "00:11:22:33:44:55:66:77:88:99:aa:bb:cc:dd:ee:ff:00:11:22:33"}]
    }

    host_data = HostWrapper(test_data(system_profile=system_profile))

    created_host = create_or_update_host(host_data, status=207, host_status=201)
    original_id = created_host["id"]

    host_lookup_results = get_host(f"{HOST_URL}/{original_id}", 200)

    validate_host(host_lookup_results["results"][0], host_data, expected_id=original_id)


def test_create_host_with_too_long_mac_address(create_or_update_host):
    system_profile = {
        "network_interfaces": [{"mac_address": "00:11:22:33:44:55:66:77:88:99:aa:bb:cc:dd:ee:ff:00:11:22:33:44"}]
    }

    host_data = HostWrapper(test_data(system_profile=system_profile))

    create_or_update_host(host_data, status=207, host_status=400)


@pytest.mark.parametrize(
    "sample",
    [
        {"disk_devices": [{"options": {"": "invalid"}}]},
        {"disk_devices": [{"options": {"ro": True, "uuid": "0", "": "invalid"}}]},
        {"disk_devices": [{"options": {"nested": {"uuid": "0", "": "invalid"}}}]},
        {"disk_devices": [{"options": {"ro": True}}, {"options": {"": "invalid"}}]},
    ],
)
def test_create_host_with_empty_json_key_in_system_profile(create_or_update_host, sample):
    host_data = HostWrapper(test_data(system_profile=sample))
    create_or_update_host(host_data, status=207, host_status=400)


@pytest.mark.parametrize(
    "facts",
    [
        [{"facts": {"": "invalid"}, "namespace": "rhsm"}],
        [{"facts": {"metadata": {"": "invalid"}}, "namespace": "rhsm"}],
        [{"facts": {"foo": "bar", "": "invalid"}, "namespace": "rhsm"}],
        [{"facts": {"foo": "bar"}, "namespace": "valid"}, {"facts": {"": "invalid"}, "namespace": "rhsm"}],
    ],
)
def test_create_host_with_empty_json_key_in_facts(create_or_update_host, facts):
    host_data = HostWrapper(test_data(facts=facts))
    create_or_update_host(host_data, status=207, host_status=400)


def test_create_host_without_display_name_and_without_fqdn(create_or_update_host, get_host):
    """
    This test should verify that the display_name is set to the id
    when neither the display name or fqdn is set.
    """
    host_data = HostWrapper(test_data(facts=None))
    del host_data.display_name
    del host_data.fqdn

    # Create the host
    created_host = create_or_update_host(host_data, status=207, host_status=201)
    original_id = created_host["id"]

    host_lookup_results = get_host(f"{HOST_URL}/{original_id}", 200)

    # Explicitly set the display_name to the be id...this is expected here
    host_data.display_name = created_host["id"]

    validate_host(host_lookup_results["results"][0], host_data, expected_id=original_id)


def test_create_host_without_display_name_and_with_fqdn(create_or_update_host, get_host):
    """
    This test should verify that the display_name is set to the
    fqdn when a display_name is not passed in but the fqdn is passed in.
    """
    expected_display_name = "fred.flintstone.bedrock.com"

    host_data = HostWrapper(test_data(facts=None))
    del host_data.display_name
    host_data.fqdn = expected_display_name

    # Create the host
    created_host = create_or_update_host(host_data, status=207, host_status=201)
    original_id = created_host["id"]

    host_lookup_results = get_host(f"{HOST_URL}/{original_id}", 200)

    # Explicitly set the display_name ...this is expected here
    host_data.display_name = expected_display_name

    validate_host(host_lookup_results["results"][0], host_data, expected_id=original_id)


@pytest.mark.bulk_creation
def test_create_and_update_multiple_hosts_with_different_accounts(create_or_update_host, mock_env_token):
    facts = None

    host1 = HostWrapper(test_data(display_name="host1", facts=facts))
    host1.account = "111111"
    host1.ip_addresses = ["10.0.0.1"]
    host1.rhel_machine_id = generate_uuid()

    host2 = HostWrapper(test_data(display_name="host2", facts=facts))
    host2.account = "222222"
    host2.ip_addresses = ["10.0.0.2"]
    host2.rhel_machine_id = generate_uuid()

    host_list = [host1, host2]

    # Create the host
    create_response = create_or_update_host(host_list, status=207, host_status=[201, 201], auth_type="token")

    assert len(host_list) == len(create_response)

    host_list[0].id = create_response[0]["id"]
    host_list[0].bios_uuid = generate_uuid()
    host_list[0].display_name = "fred"

    host_list[1].id = create_response[1]["id"]
    host_list[1].bios_uuid = generate_uuid()
    host_list[1].display_name = "barney"

    # Update the host
    update_response = create_or_update_host(host_list, status=207, host_status=[200, 200], auth_type="token")

    for i, host in enumerate(update_response):
        validate_host(host, host_list[i], expected_id=host_list[i].id)


@pytest.mark.system_profile
def test_create_host_with_system_profile(create_or_update_host, get_host):
    host_data = test_data(display_name="host1", facts=None)
    host_data["ip_addresses"] = ["10.0.0.1"]
    host_data["rhel_machine_id"] = generate_uuid()
    host_data["system_profile"] = valid_system_profile()

    # Create the host
    created_host = create_or_update_host(host_data, status=207, host_status=201)
    original_id = created_host["id"]

    # verify system_profile is not included
    assert "system_profile" not in created_host

    host_lookup_results = get_host(f"{HOST_URL}/{original_id}/system_profile", 200)
    actual_host = host_lookup_results["results"][0]

    assert actual_host["id"] == original_id
    assert actual_host["system_profile"] == host_data["system_profile"]


@pytest.mark.system_profile
def test_create_host_with_system_profile_and_query_with_branch_id(create_or_update_host, get_host):
    host_data = test_data(display_name="host1", facts=None)
    host_data["ip_addresses"] = ["10.0.0.1"]
    host_data["rhel_machine_id"] = generate_uuid()
    host_data["system_profile"] = valid_system_profile()

    # Create the host
    created_host = create_or_update_host(host_data, status=207, host_status=201)
    original_id = created_host["id"]

    # verify system_profile is not included
    assert "system_profile" not in created_host

    host_lookup_results = get_host(f"{HOST_URL}/{original_id}/system_profile?branch_id=1234", 200)
    actual_host = host_lookup_results["results"][0]

    assert actual_host["id"] == original_id
    assert actual_host["system_profile"] == host_data["system_profile"]


@pytest.mark.system_profile
def test_create_host_with_null_system_profile(create_or_update_host, get_host):
    host_data = test_data(display_name="host1", facts=None)
    host_data["ip_addresses"] = ["10.0.0.1"]
    host_data["rhel_machine_id"] = generate_uuid()
    host_data["system_profile"] = None

    # Create the host without a system profile
    response = create_or_update_host(host_data, status=400)

    verify_error_response(response, expected_title="Bad Request", expected_status=400)


@pytest.mark.system_profile
@pytest.mark.parametrize(
    "system_profile",
    [{"infrastructure_type": "i" * 101, "infrastructure_vendor": "i" * 101, "cloud_provider": "i" * 101}],
)
def test_create_host_with_system_profile_with_invalid_data(create_or_update_host, get_host, system_profile):
    host_data = test_data(display_name="host1", facts=None)
    host_data["ip_addresses"] = ["10.0.0.1"]
    host_data["rhel_machine_id"] = generate_uuid()
    host_data["system_profile"] = system_profile

    # Create the host
    create_or_update_host(host_data, status=207, host_status=400)


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
def test_create_host_with_system_profile_with_different_yum_urls(create_or_update_host, get_host, yum_url):
    host_data = test_data(display_name="host1", facts=None)
    host_data["rhel_machine_id"] = generate_uuid()
    host_data["system_profile"] = {
        "yum_repos": [{"name": "repo1", "gpgcheck": True, "enabled": True, "base_url": yum_url}]
    }

    # Create the host
    created_host = create_or_update_host(host_data, status=207, host_status=201)
    original_id = created_host["id"]

    # Verify that the system profile data is saved
    host_lookup_results = get_host(f"{HOST_URL}/{original_id}/system_profile", 200)
    actual_host = host_lookup_results["results"][0]

    assert actual_host["id"] == original_id
    assert actual_host["system_profile"] == host_data["system_profile"]


@pytest.mark.system_profile
@pytest.mark.parametrize("cloud_provider", ["cumulonimbus", "cumulus", "c" * 100])
def test_create_host_with_system_profile_with_different_cloud_providers(
    create_or_update_host, get_host, cloud_provider
):
    host_data = test_data(display_name="host1", facts=None)
    host_data["rhel_machine_id"] = generate_uuid()
    host_data["system_profile"] = {"cloud_provider": cloud_provider}

    # Create the host
    created_host = create_or_update_host(host_data, status=207, host_status=201)
    original_id = created_host["id"]

    # Verify that the system profile data is saved
    host_lookup_results = get_host(f"{HOST_URL}/{original_id}/system_profile", 200)
    actual_host = host_lookup_results["results"][0]

    assert actual_host["id"] == original_id
    assert actual_host["system_profile"] == host_data["system_profile"]


@pytest.mark.system_profile
def test_get_system_profile_of_host_that_does_not_have_system_profile(create_or_update_host, get_host):
    host_data = test_data(display_name="host1", facts=None)
    host_data["ip_addresses"] = ["10.0.0.1"]
    host_data["rhel_machine_id"] = generate_uuid()

    # Create the host
    created_host = create_or_update_host(host_data, status=207, host_status=201)
    original_id = created_host["id"]

    # Verify that the system profile data is saved
    host_lookup_results = get_host(f"{HOST_URL}/{original_id}/system_profile", 200)
    actual_host = host_lookup_results["results"][0]

    assert actual_host["id"] == original_id
    assert actual_host["system_profile"] == {}


@pytest.mark.system_profile
def test_get_system_profile_of_multiple_hosts(
    create_or_update_host, get_host, paging_test, invalid_paging_parameters_test
):
    host_id_list = []
    expected_system_profiles = []

    for i in range(2):
        host_data = test_data(display_name="host1", facts=None)
        host_data["ip_addresses"] = [f"10.0.0.{i}"]
        host_data["rhel_machine_id"] = generate_uuid()
        host_data["system_profile"] = valid_system_profile()
        host_data["system_profile"]["number_of_cpus"] = i

        created_host = create_or_update_host(host_data, status=207, host_status=201)
        original_id = created_host["id"]

        host_id_list.append(original_id)
        expected_system_profiles.append({"id": original_id, "system_profile": host_data["system_profile"]})

    url_host_id_list = ",".join(host_id_list)
    test_url = f"{HOST_URL}/{url_host_id_list}/system_profile"
    host_lookup_results = get_host(test_url, 200)

    assert len(expected_system_profiles) == len(host_lookup_results["results"])
    for expected_system_profile in expected_system_profiles:
        assert expected_system_profile in host_lookup_results["results"]

    paging_test(test_url, len(expected_system_profiles))
    invalid_paging_parameters_test(test_url)


@pytest.mark.system_profile
def test_get_system_profile_of_host_that_does_not_exist(get_host):
    expected_count = 0
    expected_total = 0
    host_id = generate_uuid()

    results = get_host(f"{HOST_URL}/{host_id}/system_profile", 200)

    assert results["count"] == expected_count
    assert results["total"] == expected_total


@pytest.mark.system_profile
@pytest.mark.parametrize("invalid_host_id", ["notauuid", f"{generate_uuid()},notuuid"])
def test_get_system_profile_with_invalid_host_id(get_host, invalid_host_id):
    response = get_host(f"{HOST_URL}/{invalid_host_id}/system_profile", 400)
    verify_error_response(response, expected_title="Bad Request", expected_status=400)


@pytest.mark.tagging
def test_create_host_with_null_tags(create_or_update_host):
    host_data = HostWrapper(test_data(tags=None))
    create_or_update_host(host_data, status=400)


@pytest.mark.tagging
def test_create_host_with_null_tag_key(create_or_update_host):
    tag = ({"namespace": "ns", "key": None, "value": "val"},)
    host_data = HostWrapper(test_data(tags=[tag]))
    create_or_update_host(host_data, status=400)


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
def test_create_host_with_invalid_tags(create_or_update_host, tag):
    host_data = HostWrapper(test_data(tags=[tag]))
    create_or_update_host(host_data, status=207, host_status=400)


@pytest.mark.tagging
def test_create_host_with_keyless_tag(create_or_update_host):
    tag = {"namespace": "ns", "key": None, "value": "val"}
    host_data = HostWrapper(test_data(tags=[tag]))
    create_or_update_host(host_data, status=400)


@pytest.mark.tagging
def test_create_host_with_invalid_string_tag_format(create_or_update_host):
    tag = "string/tag=format"
    host_data = HostWrapper(test_data(tags=[tag]))
    create_or_update_host(host_data, status=400)


@pytest.mark.tagging
def test_create_host_with_invalid_tag_format(create_or_update_host):
    tag = {"namespace": "spam", "key": {"foo": "bar"}, "value": "eggs"}
    host_data = HostWrapper(test_data(tags=[tag]))
    create_or_update_host(host_data, status=400)


@pytest.mark.tagging
def test_create_host_with_tags(create_or_update_host, get_host):
    host_data = HostWrapper(
        test_data(
            tags=[
                {"namespace": "NS3", "key": "key2", "value": "val2"},
                {"namespace": "NS1", "key": "key3", "value": "val3"},
                {"namespace": "Sat", "key": "prod", "value": None},
                {"namespace": "NS2", "key": "key1", "value": ""},
            ]
        )
    )

    created_host = create_or_update_host(host_data, status=207, host_status=201)
    original_id = created_host["id"]

    host_lookup_results = get_host(f"{HOST_URL}/{original_id}", 200)
    assert host_lookup_results["results"][0]["id"] == original_id

    host_tags = get_host(f"{HOST_URL}/{original_id}/tags", 200)["results"][original_id]

    expected_tags = [
        {"namespace": "NS1", "key": "key3", "value": "val3"},
        {"namespace": "NS3", "key": "key2", "value": "val2"},
        {"namespace": "Sat", "key": "prod", "value": None},
        {"namespace": "NS2", "key": "key1", "value": None},
    ]

    assert len(host_tags) == len(expected_tags)


@pytest.mark.tagging
def test_create_host_with_tags_special_characters(create_or_update_host, get_host):
    tags = [
        {"namespace": "NS1;,/?:@&=+$-_.!~*'()#", "key": "ŠtěpánΔ12!@#$%^&*()_+-=", "value": "ŠtěpánΔ:;'|,./?~`"},
        {"namespace": " \t\n\r\f\v", "key": " \t\n\r\f\v", "value": " \t\n\r\f\v"},
    ]
    host_data = HostWrapper(test_data(tags=tags))

    created_host = create_or_update_host(host_data, status=207, host_status=201)
    original_id = created_host["id"]

    host_lookup_results = get_host(f"{HOST_URL}/{original_id}", 200)
    assert host_lookup_results["results"][0]["id"] == original_id

    host_tags = get_host(f"{HOST_URL}/{original_id}/tags", 200)["results"][original_id]
    assert len(host_tags) == len(tags)


@pytest.mark.tagging
def test_create_host_with_tag_without_some_fields(create_or_update_host, get_host):
    tags = [
        {"namespace": None, "key": "key3", "value": "val3"},
        {"namespace": "", "key": "key1", "value": "val1"},
        {"namespace": "null", "key": "key4", "value": "val4"},
        {"key": "key2", "value": "val2"},
        {"namespace": "Sat", "key": "prod", "value": None},
        {"namespace": "Sat", "key": "dev", "value": ""},
        {"key": "some_key"},
    ]

    host_data = HostWrapper(test_data(tags=tags))

    created_host = create_or_update_host(host_data, status=207, host_status=201)
    original_id = created_host["id"]

    host_lookup_results = get_host(f"{HOST_URL}/{original_id}", 200)
    assert host_lookup_results["results"][0]["id"] == original_id

    host_tags = get_host(f"{HOST_URL}/{original_id}/tags", 200)["results"][original_id]

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
def test_update_host_replaces_tags(create_or_update_host, get_host):
    insights_id = generate_uuid()

    create_tags = [
        {"namespace": "namespace1", "key": "key1", "value": "value1"},
        {"namespace": "namespace1", "key": "key2", "value": "value2"},
    ]
    create_host_data = test_data(insights_id=insights_id, tags=create_tags)
    created_host = create_or_update_host(create_host_data, status=207, host_status=201)
    host_id = created_host["id"]

    created_tags = get_host(f"{HOST_URL}/{host_id}/tags", 200)["results"][host_id]
    assert len(created_tags) == len(create_tags)

    update_tags = [
        {"namespace": "namespace1", "key": "key2", "value": "value3"},
        {"namespace": "namespace1", "key": "key3", "value": "value4"},
    ]
    update_host_data = test_data(insights_id=insights_id, tags=update_tags)
    create_or_update_host(update_host_data, status=207, host_status=200)

    updated_tags = get_host(f"{HOST_URL}/{host_id}/tags", 200)["results"][host_id]
    assert len(updated_tags) == len(update_tags)


@pytest.mark.tagging
def test_update_host_does_not_remove_namespace(create_or_update_host, get_host):
    insights_id = generate_uuid()

    create_tags = [{"namespace": "namespace1", "key": "key1", "value": "value1"}]
    create_host_data = test_data(insights_id=insights_id, tags=create_tags)
    created_host = create_or_update_host(create_host_data, status=207, host_status=201)
    host_id = created_host["id"]

    created_tags = get_host(f"{HOST_URL}/{host_id}/tags", 200)["results"][host_id]
    assert len(created_tags) == len(create_tags)

    update_tags = [{"namespace": "namespace2", "key": "key2", "value": "value3"}]
    update_host_data = test_data(insights_id=insights_id, tags=update_tags)
    create_or_update_host(update_host_data, status=207, host_status=200)

    updated_tags = get_host(f"{HOST_URL}/{host_id}/tags", 200)["results"][host_id]
    assert len(updated_tags) == len(create_tags) + len(update_tags)


@pytest.mark.tagging
def test_create_host_with_nested_tags(create_or_update_host):
    create_tags = {"namespace": {"key": ["value"]}}
    create_host_data = test_data(tags=create_tags)
    create_or_update_host(create_host_data, status=400)


@pytest.mark.system_culling
@pytest.mark.parametrize("fields_to_delete", [("stale_timestamp", "reporter"), ("stale_timestamp",), ("reporter",)])
def test_create_host_without_culling_fields(create_or_update_host, fields_to_delete):
    host_data = test_data(fqdn="match this host")
    for field in fields_to_delete:
        del host_data[field]
    create_or_update_host(host_data, status=400)


@pytest.mark.system_culling
@pytest.mark.parametrize("culling_fields", [("stale_timestamp",), ("reporter",), ("stale_timestamp", "reporter")])
def test_create_host_with_null_culling_fields(create_or_update_host, culling_fields):
    host_data = test_data(fqdn="match this host", **{field: None for field in culling_fields})
    create_or_update_host(host_data, status=400)


@pytest.mark.system_culling
@pytest.mark.parametrize("culling_fields", [("stale_timestamp",), ("reporter",), ("stale_timestamp", "reporter")])
def test_create_host_with_empty_culling_fields(create_or_update_host, culling_fields):
    host_data = HostWrapper(test_data(**{field: "" for field in culling_fields}))
    create_or_update_host(host_data, status=207, host_status=400)


@pytest.mark.system_culling
def test_create_host_with_invalid_stale_timestamp(create_or_update_host):
    host_data = HostWrapper(test_data(stale_timestamp="not a timestamp"))
    create_or_update_host(host_data, status=207, host_status=400)


@pytest.mark.system_culling
def test_create_host_with_stale_timestamp_and_reporter(create_or_update_host, get_host_from_db):
    stale_timestamp = now()
    reporter = "some reporter"
    host_data = HostWrapper(test_data(stale_timestamp=stale_timestamp.isoformat(), reporter=reporter))

    created_host = create_or_update_host(host_data, status=207, host_status=201)

    retrieved_host = get_host_from_db(created_host["id"])

    assert stale_timestamp == retrieved_host.stale_timestamp
    assert reporter == retrieved_host.reporter


@pytest.mark.system_culling
def test_update_stale_timestamp_from_same_reporter(create_or_update_host, get_host_from_db):
    current_timestamp = now()

    old_stale_timestamp = current_timestamp + timedelta(days=1)
    reporter = "some reporter"
    host_data = HostWrapper(test_data(stale_timestamp=old_stale_timestamp.isoformat(), reporter=reporter))

    created_host = create_or_update_host(host_data, status=207, host_status=201)
    old_retrieved_host = get_host_from_db(created_host["id"])

    assert old_stale_timestamp == old_retrieved_host.stale_timestamp
    assert reporter == old_retrieved_host.reporter

    new_stale_timestamp = current_timestamp + timedelta(days=2)
    host_data = HostWrapper(test_data(stale_timestamp=new_stale_timestamp.isoformat(), reporter=reporter))

    create_or_update_host(host_data, status=207, host_status=200)
    new_retrieved_host = get_host_from_db(created_host["id"])

    assert new_stale_timestamp == new_retrieved_host.stale_timestamp
    assert reporter == new_retrieved_host.reporter


@pytest.mark.system_culling
def test_dont_update_stale_timestamp_from_same_reporter(create_or_update_host, get_host_from_db):
    current_timestamp = now()

    old_stale_timestamp = current_timestamp + timedelta(days=2)
    reporter = "some reporter"
    host_data = HostWrapper(test_data(stale_timestamp=old_stale_timestamp.isoformat(), reporter=reporter))

    created_host = create_or_update_host(host_data, status=207, host_status=201)
    old_retrieved_host = get_host_from_db(created_host["id"])

    assert old_stale_timestamp == old_retrieved_host.stale_timestamp

    new_stale_timestamp = current_timestamp + timedelta(days=1)
    host_data = HostWrapper(test_data(stale_timestamp=new_stale_timestamp.isoformat(), reporter=reporter))

    create_or_update_host(host_data, status=207, host_status=200)
    new_retrieved_host = get_host_from_db(created_host["id"])

    assert old_stale_timestamp == new_retrieved_host.stale_timestamp


@pytest.mark.system_culling
def test_update_stale_timestamp_from_different_reporter(create_or_update_host, get_host_from_db):
    current_timestamp = now()

    old_stale_timestamp = current_timestamp + timedelta(days=2)
    old_reporter = "old reporter"
    host_data = HostWrapper(test_data(stale_timestamp=old_stale_timestamp.isoformat(), reporter=old_reporter))

    created_host = create_or_update_host(host_data, status=207, host_status=201)
    old_retrieved_host = get_host_from_db(created_host["id"])

    assert old_stale_timestamp == old_retrieved_host.stale_timestamp
    assert old_reporter == old_retrieved_host.reporter

    new_stale_timestamp = current_timestamp + timedelta(days=1)
    new_reporter = "new reporter"
    host_data = HostWrapper(test_data(stale_timestamp=new_stale_timestamp.isoformat(), reporter=new_reporter))

    create_or_update_host(host_data, status=207, host_status=200)
    new_retrieved_host = get_host_from_db(created_host["id"])

    assert new_stale_timestamp == new_retrieved_host.stale_timestamp
    assert new_reporter == new_retrieved_host.reporter


@pytest.mark.system_culling
def test_update_stale_host_timestamp_from_next_reporter(create_or_update_host, get_host_from_db):
    current_timestamp = now()

    old_stale_timestamp = current_timestamp - timedelta(days=1)  # stale host
    old_reporter = "old reporter"
    host_data = HostWrapper(test_data(stale_timestamp=old_stale_timestamp.isoformat(), reporter=old_reporter))

    created_host = create_or_update_host(host_data, status=207, host_status=201)
    old_retrieved_host = get_host_from_db(created_host["id"])

    assert old_stale_timestamp == old_retrieved_host.stale_timestamp
    assert old_reporter == old_retrieved_host.reporter

    new_stale_timestamp = current_timestamp + timedelta(days=1)
    new_reporter = "new reporter"
    host_data = HostWrapper(test_data(stale_timestamp=new_stale_timestamp.isoformat(), reporter=new_reporter))

    create_or_update_host(host_data, status=207, host_status=200)
    new_retrieved_host = get_host_from_db(created_host["id"])

    assert new_stale_timestamp == new_retrieved_host.stale_timestamp
    assert new_reporter == new_retrieved_host.reporter


@pytest.mark.system_culling
def test_dont_update_stale_timestamp_from_different_reporter(create_or_update_host, get_host_from_db):
    current_timestamp = now()

    old_stale_timestamp = current_timestamp + timedelta(days=1)
    old_reporter = "old reporter"
    host_data = HostWrapper(test_data(stale_timestamp=old_stale_timestamp.isoformat(), reporter=old_reporter))

    created_host = create_or_update_host(host_data, status=207, host_status=201)
    old_retrieved_host = get_host_from_db(created_host["id"])

    assert old_stale_timestamp == old_retrieved_host.stale_timestamp
    assert old_reporter == old_retrieved_host.reporter

    new_stale_timestamp = current_timestamp + timedelta(days=2)
    host_data = HostWrapper(test_data(stale_timestamp=new_stale_timestamp.isoformat(), reporter="new_reporter"))

    create_or_update_host(host_data, status=207, host_status=200)
    new_retrieved_host = get_host_from_db(created_host["id"])

    assert old_stale_timestamp == new_retrieved_host.stale_timestamp
    assert old_reporter == new_retrieved_host.reporter


@pytest.mark.system_culling
def test_create_host_with_stale_timestamp_without_time_zone(create_or_update_host):
    host_data = HostWrapper(test_data(stale_timestamp=datetime.now().isoformat(), reporter="reporter"))
    create_or_update_host(host_data, status=207, host_status=400)
