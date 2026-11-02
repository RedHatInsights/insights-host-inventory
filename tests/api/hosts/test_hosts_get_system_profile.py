import random
from collections.abc import Callable

import pytest

from app.models.host import Host
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host


@pytest.mark.parametrize(
    "query",
    (
        "?filter[system_profile][workloads][sap][sap_system]=Garfield",
        "?filter[system_profile][workloads][sap][sap_system][eq]=Garfield",
    ),
)
def test_get_hosts_sap_system_bad_parameter_values(api_get, query):
    implicit_url = build_hosts_url(query=query)
    status, _ = api_get(implicit_url)

    assert_response_status(status, 400)


def test_sparse_fields_rejects_unknown_system_profile_field(api_get):
    response_status, response_data = api_get(build_hosts_url(query="?fields[system_profile]=not_a_real_field"))

    assert response_status == 400
    assert "not_a_real_field" in response_data["detail"]


@pytest.mark.parametrize("order_how", ("", "ASC", "DESC"))
def test_get_hosts_order_by_operating_system(mq_create_or_update_host, api_get, order_how):
    # Create some operating systems in ASC sort order
    ordered_operating_system_data = [
        {"name": "CentOS", "major": 4, "minor": 0},
        {"name": "CentOS", "major": 4, "minor": 1},
        {"name": "CentOS", "major": 5, "minor": 0},
        {"name": "CentOS", "major": 5, "minor": 1},
        {"name": "RHEL", "major": 3, "minor": 0},
        {"name": "RHEL", "major": 3, "minor": 11},
        {"name": "RHEL", "major": 8, "minor": 0},
        {"name": "RHEL", "major": 8, "minor": 1},
    ]
    ordered_insights_ids = [generate_uuid() for _ in range(len(ordered_operating_system_data))]

    # Create an association between the insights IDs
    ordered_host_data = dict(zip(ordered_insights_ids, ordered_operating_system_data, strict=False))

    # Create a shuffled list of insights_ids so we can create the hosts in a random order
    shuffled_insights_ids = ordered_insights_ids.copy()
    random.shuffle(shuffled_insights_ids)

    # Create hosts for the above host data (in shuffled order)
    created_hosts = [
        mq_create_or_update_host(
            minimal_host(insights_id=insights_id, system_profile={"operating_system": ordered_host_data[insights_id]})
        )
        for insights_id in shuffled_insights_ids
    ]
    # Create host without operating system
    minimal_host(insights_id=generate_uuid(), system_profile={})

    query = "?order_by=operating_system"
    if order_how:
        query += f"&order_how={order_how}"

    url = build_hosts_url(query=query)

    # Validate the basics, i.e. response code and results size
    response_status, response_data = api_get(url)
    assert response_status == 200
    assert len(created_hosts) == len(response_data["results"])

    # If descending order is requested, reverse the expected order of hosts
    if order_how != "ASC":
        ordered_insights_ids.reverse()

    for index in range(len(ordered_insights_ids)):
        assert ordered_insights_ids[index] == response_data["results"][index]["insights_id"]


@pytest.mark.parametrize("num_hosts_to_query", (1, 3))
@pytest.mark.parametrize("sparse_request", (True, False))
@pytest.mark.parametrize("order_by", ("updated", "display_name", "group_name", "operating_system", "last_check_in"))
@pytest.mark.parametrize("order_how", ("ASC", "DESC"))
def test_query_sp_by_id_list_sparse(
    db_create_multiple_hosts, api_get, num_hosts_to_query, sparse_request, order_by, order_how
):
    sp_data = {
        "system_profile_facts": {
            "arch": "x86_64",
            "os_kernel_version": "4.18.2",
            "host_type": "edge",
            "owner_id": "1b36b20f-7fa0-4454-a6d2-008294e06378",
        }
    }
    created_hosts = db_create_multiple_hosts(how_many=3, extra_data=sp_data)
    created_hosts_ids = [str(host.id) for host in created_hosts]
    host_list_url = build_hosts_url(host_list_or_id=created_hosts[:num_hosts_to_query])
    url = f"{host_list_url}/system_profile?order_by={order_by}&order_how={order_how}"
    if sparse_request:
        url += "&fields[system_profile]=arch,os_kernel_version,installed_packages,host_type"

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == num_hosts_to_query
    for response_host in response_data["results"]:
        assert response_host["id"] in created_hosts_ids

        # "!=" works as an XOR
        assert sparse_request != ("owner_id" in response_host["system_profile"])
        for fact in ["arch", "os_kernel_version", "host_type"]:
            assert fact in response_host["system_profile"]


@pytest.mark.parametrize(
    "sp_filter_param",
    (
        "[arch]=x86_64",
        "[arch][eq]=x86_64",
        "[arch][neq]=ARM",
        "[insights_client_version]=3.0.1-2.el4_2",
        "[insights_client_version]=3.0.*",
        "[host_type]=edge",
        "[workloads][sap][sap_system]=true",
        "[sap][sap_system]=true",
        "[sap_system]=true",
        "[workloads][mssql][version]=15.3",
        "[workloads][mssql][version][]=15.3",
        "[workloads][mssql][version][]=not_nil",
        "[mssql][version]=15.3",
        "[mssql][version][]=15.3",
        "[mssql][version][]=not_nil",
        "[workloads][ansible][is]=not_nil",
        "[workloads][ansible][controller_version]=1.0",
        "[ansible][controller_version]=1.0",
        "[workloads][ansible][receptor_version]=1.5.2",
        "[ansible][receptor_version]=1.5.2",
        "[workloads][ansible][runner_version]=2.4.1",
        "[ansible][runner_version]=2.4.1",
        "[workloads][ansible][eda_controller_version]=1.1.0",
        "[ansible][eda_controller_version]=1.1.0",
        "[workloads][ansible][gateway_version]=2.5.3",
        "[ansible][gateway_version]=2.5.3",
        "[workloads][sap][sap_system]=True",
        "[workloads][sap][sap_system]=TRUE",
        "[workloads][sap][sap_system][is]=not_nil",
        "[workloads][sap][sap_system][is][]=not_nil",
        "[sap][sap_system]=True",
        "[sap][sap_system]=TRUE",
        "[sap][sap_system][is]=not_nil",
        "[sap][sap_system][is][]=not_nil",
        "[is_marketplace]=false",
        "[is_marketplace]=False",
        "[is_marketplace]=FALSE",
        "[arch]=x86_64&filter[system_profile][host_type]=edge",
        "[insights_client_version][]=3.0.*&filter[system_profile][insights_client_version][]=*el4_2",
        "[greenboot_status][is]=nil",
        "[host_type]=not_nil",
        "[greenboot_status][is][]=nil",
        "[host_type][]=not_nil",
        "[bootc_status][booted][image]=quay.io*",
        "[workloads][sap][sids][contains][]=ABC",
        "[sap][sids][contains][]=ABC",
        "[sap_sids][contains][]=ABC",
        "[workloads][sap][sids][contains][]=ABC&filter[system_profile][workloads][sap][sids][contains][]=DEF",
        "[workloads][sap][sids][contains]=ABC",
        "[workloads][sap][sids][]=ABC",
        "[workloads][sap][sids][]=not_nil",
        "[systemd][failed_services][contains][]=foo",
        "[system_memory_bytes][lte]=9000000000000000",
        "[system_memory_bytes][eq]=8292048963606259",
        "[number_of_cpus][is]=nil",
        "[number_of_cpus]=nil",
        "[bios_version]=2.0/3.5A",
        "[cpu_flags][]=nil",
        "[workloads][rhel_ai][rhel_ai_version_id][is]=not_nil",
        "[workloads][rhel_ai][rhel_ai_version_id]=v1.1.2",
        "[workloads][rhel_ai][rhel_ai_version_id][]=v1.1.2",
        "[workloads][rhel_ai][rhel_ai_version_id][eq]=v1.1.2",
        "[workloads][rhel_ai][rhel_ai_version_id][eq][]=v1.1.2",
        "[workloads][rhel_ai][variant][is]=nil",
        "[workloads][rhel_ai][gpu_models][is]=not_nil",
        "[workloads][satellite][is]=not_nil",
        "[workloads][satellite][type][]=server",
        "[workloads][satellite][type][]=not_nil",
        "[workloads][satellite][version]=6.17.6.1",
        "[workloads][satellite][version][]=6.17.6.1",
        "[workloads][satellite][version][]=not_nil",
        "[workloads][satellite][foremanctl_version]=3.0.0",
        "[workloads][satellite][foremanctl_version][]=3.0.0",
        "[workloads][satellite][foremanctl_version][]=not_nil",
        "[workloads][satellite][foremanctl_version]=3.*",
        # JSON object notation (value is a JSON string instead of square bracket path)
        '={"arch": "x86_64"}',
        '={"arch": {"eq": "x86_64"}}',
        '={"workloads": {"sap": {"sap_system": "true"}}}',
        '={"workloads": {"sap": {"sids": {"contains": ["ABC", "DEF"]}}}}',
    ),
)
def test_query_all_sp_filters_basic(db_create_host, api_get, sp_filter_param):
    # Create host with this system profile
    match_sp_data = {
        "system_profile_facts": {
            "arch": "x86_64",
            "insights_client_version": "3.0.1-2.el4_2",
            "host_type": "edge",
            "bootc_status": {"booted": {"image": "quay.io/centos-bootc/fedora-bootc-cloud:eln"}},
            "workloads": {
                "sap": {"sap_system": True, "sids": ["ABC", "DEF"]},
                "mssql": {"version": "15.3"},
                "ansible": {
                    "controller_version": "1.0",
                    "receptor_version": "1.5.2",
                    "runner_version": "2.4.1",
                    "eda_controller_version": "1.1.0",
                    "gateway_version": "2.5.3",
                    "containers": [
                        {"name": "receptor", "image": "quay.io/ansible/receptor:latest", "state": "running"}
                    ],
                },
                "rhel_ai": {
                    "rhel_ai_version_id": "v1.1.2",
                    "gpu_models": [
                        {"name": "NVIDIA T1000", "vendor": "Nvidia"},
                        {"name": "AMD Device 0c31", "vendor": "AMD"},
                    ],
                },
                "satellite": {
                    "type": "server",
                    "version": "6.17.6.1",
                    "foremanctl_version": "3.0.0",
                    "containers": [
                        {"name": "foreman", "image": "quay.io/foreman/foreman:nightly", "state": "running"}
                    ],
                },
            },
            "is_marketplace": False,
            "systemd": {"failed_services": ["foo", "bar"]},
            "system_memory_bytes": 8292048963606259,
            "bios_version": "2.0/3.5A",
        }
    }
    match_host_id = str(db_create_host(extra_data=match_sp_data).id)

    # Create host with differing SP
    nomatch_sp_data = {
        "system_profile_facts": {
            "arch": "ARM",
            "cpu_flags": ["ex1", "ex2"],
            "insights_client_version": "1.2.3",
            "greenboot_status": "green",
            "workloads": {
                "sap": {},  # No sap_system field = nil
                "rhel_ai": {
                    "variant": "RHEL AI",  # Has variant (not nil) for variant filter
                    # No gpu_models = nil for gpu_models filter
                    # Different version for version filter
                },
            },
            "bootc_status": {"booted": {"image": "192.168.0.1:5000/foo/foo:latest"}},
            "is_marketplace": True,
            "number_of_cpus": 8,
            "bios_version": "2.0-3.5A",
        }
    }
    nomatch_host_id = str(db_create_host(extra_data=nomatch_sp_data).id)

    url = build_hosts_url(query=f"?filter[system_profile]{sp_filter_param}")

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that only the matching host is returned
    response_ids = [result["id"] for result in response_data["results"]]
    assert match_host_id in response_ids
    assert nomatch_host_id not in response_ids


@pytest.mark.parametrize(
    "sp_filter_bool_field",
    (
        "katello_agent_running",
        "satellite_managed",
        "is_marketplace",
        "greenboot_fallback_detected",
    ),
)
def test_query_all_sp_filters_bools_use_or_logic(db_create_host, api_get, sp_filter_bool_field):
    # Create host with true value for the boolean field
    host_1_data = {
        "system_profile_facts": {
            sp_filter_bool_field: True,
        }
    }
    host_1_id = str(db_create_host(extra_data=host_1_data).id)

    # Create host with false value for the boolean field
    host_2_data = {
        "system_profile_facts": {
            sp_filter_bool_field: False,
        }
    }
    host_2_id = str(db_create_host(extra_data=host_2_data).id)

    # Create host with no value for the boolean field
    nomatch_host_data = {"system_profile_facts": {}}
    nomatch_host_id = str(db_create_host(extra_data=nomatch_host_data).id)

    url = build_hosts_url(
        query=f"?filter[system_profile][{sp_filter_bool_field}][]=true"
        + f"&filter[system_profile][{sp_filter_bool_field}][]=false"
    )
    response_status, response_data = api_get(url)
    assert response_status == 200

    response_ids = [result["id"] for result in response_data["results"]]
    assert len(response_ids) == 2
    assert host_1_id in response_ids
    assert host_2_id in response_ids
    assert nomatch_host_id not in response_ids


@pytest.mark.parametrize(
    "sp_filter_bool_field",
    (
        "katello_agent_running",
        "satellite_managed",
        "is_marketplace",
        "greenboot_fallback_detected",
        "sap_system",
    ),
)
@pytest.mark.parametrize("filter_append", ("", "[]", "[is]"))
def test_query_all_sp_filters_bools_nil(db_create_host, api_get, sp_filter_bool_field, filter_append):
    # Create host with no value for the boolean field
    host_data = {"system_profile_facts": {}}
    host_id = str(db_create_host(extra_data=host_data).id)

    # Note: sap_system is now stored in workloads.sap.sap_system, not at root level.
    # db_create_host fixture bypasses schema validation (which would migrate legacy fields),
    # so we need to use the correct workloads structure directly.
    if sp_filter_bool_field == "sap_system":
        nomatch_host_data_1 = {"system_profile_facts": {"workloads": {"sap": {"sap_system": True}}}}
        nomatch_host_data_2 = {"system_profile_facts": {"workloads": {"sap": {"sap_system": False}}}}
    else:
        nomatch_host_data_1 = {"system_profile_facts": {sp_filter_bool_field: True}}
        nomatch_host_data_2 = {"system_profile_facts": {sp_filter_bool_field: False}}

    nomatch_host_id_1 = str(db_create_host(extra_data=nomatch_host_data_1).id)
    nomatch_host_id_2 = str(db_create_host(extra_data=nomatch_host_data_2).id)

    url = build_hosts_url(query=f"?filter[system_profile][{sp_filter_bool_field}]{filter_append}=nil")
    response_status, response_data = api_get(url)
    assert response_status == 200

    response_ids = [result["id"] for result in response_data["results"]]
    assert len(response_ids) == 1
    assert host_id in response_ids
    assert nomatch_host_id_1 not in response_ids
    assert nomatch_host_id_2 not in response_ids


@pytest.mark.parametrize(
    "sp_filter_param",
    (
        "[system_memory_bytes][eq]=8292048963606259",
        "[system_memory_bytes][]=8292048963606259",
        "[system_memory_bytes]=8292048963606259",
        "[arch]=x86",  # EQ field, no wildcard
        "[host_type]=",  # Valid bc it's a string field, but no match
        "[host_type][eq]=",  # Same for this one
        "[workloads][sap][sids][contains][]=ABC&filter[system_profile][workloads][sap][sids][contains][]=GHI",
        "[sap][sids][contains][]=ABC&filter[system_profile][sap][sids][contains][]=GHI",
        "[virtual_host_uuid]=",  # Valid field, but no match
        "[arch]=",
    ),
)
def test_query_all_sp_filters_not_found(db_create_host, api_get, sp_filter_param):
    # Create host with this system profile
    nomatch_sp_data = {
        "system_profile_facts": {
            "arch": "x86_64",
            "host_type": "edge",
            "workloads": {"sap": {"sap_system": True, "sids": ["ABC", "DEF"]}},
            "system_memory_bytes": 8192,
        }
    }
    db_create_host(extra_data=nomatch_sp_data)

    # This host has none of the fields, so it shouldn't be returned either
    nomatch_sp_data = {"system_profile_facts": {"bios_vendor": "ex1"}}
    db_create_host(extra_data=nomatch_sp_data)

    url = build_hosts_url(query=f"?filter[system_profile]{sp_filter_param}")

    response_status, response_data = api_get(url)

    # Assert that the request succeeds but no hosts are returned
    assert response_status == 200
    assert len(response_data["results"]) == 0


@pytest.mark.parametrize(
    "sp_filter_param",
    (
        "[RHEL][version]=8.11",
        "[RHEL][version][eq]=8.11",
        "[RHEL][version][eq][]=8.11",
        "[RHEL][version][eq][]=8.11&filter[system_profile][operating_system][RHEL][version][gt][]=8",
        "[RHEL][version][eq][]=8.11&filter[system_profile][operating_system][RHEL][version][eq][]=9.1",
        "[RHEL][version][gte]=8",
        "[RHEL][version][gte][]=8",
        "[RHEL][version][gt]=7",  # Minor version should be ignored
        "[RHEL][version][gt][]=7",
        "[RHEL][version][eq]=8",  # Minor version should be ignored
        "[RHEL][version][eq][]=8",
        "[RHEL][version]=8",  # Minor version should be ignored
        "[RHEL][version][gte]=8&filter[system_profile][operating_system][RHEL][version][lte]=8",
        # RHINENG-15763: range comparators must match stored OS name case-insensitively
        "[Rhel][version][gt][]=7",
        "[rHeL][version][gte]=8",
        "[rhel][version][gt][]=7&filter[system_profile][operating_system][rhel][version][lt][]=9",
        "[rhel][version][gt][]=7&filter[system_profile][operating_system][rhel][version][lte][]=8",
        "[rhel][version][gte]=8&filter[system_profile][operating_system][rhel][version][lte]=8",
    ),
)
def test_query_all_sp_filters_operating_system(db_create_host, api_get, sp_filter_param):
    # Create host with this system profile
    match_sp_data = {"system_profile_facts": {"operating_system": {"name": "RHEL", "major": "8", "minor": "11"}}}
    match_host_id = str(db_create_host(extra_data=match_sp_data).id)

    # Create host with differing SP
    nomatch_sp_data = {"system_profile_facts": {"operating_system": {"name": "RHEL", "major": "7", "minor": "12"}}}
    nomatch_host_id_1 = str(db_create_host(extra_data=nomatch_sp_data).id)

    # Create host with differing SP
    nomatch_sp_data = {"system_profile_facts": {"operating_system": {"name": "RHEL", "major": "7", "minor": "5"}}}
    nomatch_host_id_2 = str(db_create_host(extra_data=nomatch_sp_data).id)

    # Create host with differing SP
    nomatch_sp_data = {"system_profile_facts": {"operating_system": {"name": "CentOS", "major": "7", "minor": "0"}}}
    nomatch_host_id_3 = str(db_create_host(extra_data=nomatch_sp_data).id)

    url = build_hosts_url(query=f"?filter[system_profile][operating_system]{sp_filter_param}")

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that only the matching host is returned
    response_ids = [result["id"] for result in response_data["results"]]
    assert match_host_id in response_ids
    assert nomatch_host_id_1 not in response_ids
    assert nomatch_host_id_2 not in response_ids
    assert nomatch_host_id_3 not in response_ids


@pytest.mark.parametrize(
    "sp_filter_param,match",
    (
        ("[name][eq]=CentOS", True),
        ("[name][eq]=centos", True),
        ("[name][eq]=CENTOS", True),
        ("[name][eq]=centos&filter[system_profile][operating_system][RHEL][version][eq][]=8", True),
        ("[name][neq]=CENTOS", False),
        ("[name][neq]=CentOS", False),
    ),
)
def test_query_sp_filters_operating_system_name(db_create_host, api_get, sp_filter_param, match):
    # Create host with this OS
    match_sp_data = {"system_profile_facts": {"operating_system": {"name": "CentOS", "major": "8", "minor": "11"}}}
    match_host_id = str(db_create_host(extra_data=match_sp_data).id)

    # Create host with differing OS
    nomatch_sp_data = {"system_profile_facts": {"operating_system": {"name": "RHEL", "major": "7", "minor": "12"}}}
    nomatch_host_id = str(db_create_host(extra_data=nomatch_sp_data).id)

    url = build_hosts_url(query=f"?filter[system_profile][operating_system]{sp_filter_param}")

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that only the matching host is returned
    response_ids = [result["id"] for result in response_data["results"]]

    if match:
        assert match_host_id in response_ids
        assert nomatch_host_id not in response_ids
    else:
        assert nomatch_host_id in response_ids
        assert match_host_id not in response_ids


@pytest.mark.parametrize(
    "sp_filter_param_list",
    (
        ["[arch][eq][]=x86_64", "[arch][eq][]=ARM"],  # Uses OR (same comparator)
        [
            "[operating_system][name][eq][]=CentOS Linux",
            "[operating_system][name][eq][]=RHEL",
        ],  # Uses OR
        [
            "[operating_system][CentOS Linux][version][eq][]=8.0",
            "[operating_system][RHEL][version][eq][]=7.5",
        ],
        ["[insights_client_version][]=3.0.1*", "[insights_client_version][]=1.2.3"],  # Uses OR
        ["[systemd][jobs_queued][lt][]=10", "[systemd][jobs_queued][gte][]=1"],  # Uses AND (different comparators)
    ),
)
def test_query_all_sp_filters_multiple_of_same_field(db_create_host, api_get, sp_filter_param_list):
    # Create two hosts that we want to show up in the results
    match_1_sp_data = {
        "system_profile_facts": {
            "operating_system": {"name": "RHEL", "major": "7", "minor": "5"},
            "arch": "x86_64",
            "insights_client_version": "3.0.1-2.el4_2",
            "systemd": {"jobs_queued": "1"},
        }
    }
    match_1_host_id = str(db_create_host(extra_data=match_1_sp_data).id)

    match_2_sp_data = {
        "system_profile_facts": {
            "operating_system": {"name": "CentOS Linux", "major": "8", "minor": "0"},
            "arch": "ARM",
            "insights_client_version": "1.2.3",
            "systemd": {"jobs_queued": "5"},
        }
    }
    match_2_host_id = str(db_create_host(extra_data=match_2_sp_data).id)

    # Create a host that we don't want to appear in the results
    nomatch_sp_data = {
        "system_profile_facts": {
            "operating_system": {"name": "CentOS"},
            "arch": "RISC-V",
            "insights_client_version": "4.5.6",
            "systemd": {"jobs_queued": "10"},
        }
    }
    nomatch_host_id = str(db_create_host(extra_data=nomatch_sp_data).id)

    sp_query_filter = "&".join([f"filter[system_profile]{param}" for param in sp_filter_param_list])
    url = build_hosts_url(query=f"?{sp_query_filter}")

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that only the matching host is returned
    response_ids = [result["id"] for result in response_data["results"]]
    assert match_1_host_id in response_ids
    assert match_2_host_id in response_ids
    assert nomatch_host_id not in response_ids


@pytest.mark.parametrize(
    "sp_filter_param",
    (
        "[arch]=RkFz%60Z%2Ag%5D9_tW%3A%2CR%27v%22sjJsEo%23R%5D%27%27n.N2%3D%60G%22R%7C%7C.ER/1/wd6%603w-71%3CxC2",
        "[arch]=%5B%3Cb_Tu%7Dd%21%5D%7C/%22%29IS-%3Ct%28EwU%3F%3C4s7%7Cv%5DRE5hSU%3AQRJ%7D%29%230%27Vcf7%60eU%25k%2B/Cp%3CSxgKopb%3E%60",  # noqa E501
        "[arch]=%26.%40%7DE%21_A%2AE%26dgjV%7D%60yPc%22wO%7B%21b0%28kAGL%24-3mh%5EV%3E86%27RmG%7D.%2C5xQI~W/d%23/n%5DAr%22T",  # noqa E501
        "[arch]=EElM%298Z%28%29HjNL%21oRSc/gxC2%24%5Dpc%27tv%2A~mW%22kiF%7Ddos%60TE%7D%7DpAZ9C%3CNCRsEb%5BxH0",
    ),
)
def test_query_all_sp_filters_sql_character_issues(api_get, sp_filter_param):
    url = build_hosts_url(query=f"?filter[system_profile]{sp_filter_param}")

    response_status, _ = api_get(url)

    assert response_status == 200


@pytest.mark.parametrize(
    "sp_filter_param",
    (
        "[arch]=qbe%5Dd%3Fsdx%60.%7B0%60sTfX%3AGP%26dp%24kf%3By0%60F3%3B%60%5EZ1aa-b-%5B%3A9%24%26s4",  # noqa: E501
        "[arch]=%25T%5E%3EGYlS%22Q%2A2K%3A6v57YGLU5.7H%2Ap%23kEHqhTH1u6yEX%3AyaJyFkC",
        "[arch]=0~j%40TiIP%5ExYk%26yoFc0f%28%22El%6073g2%3B%22pqm%250z",
        "[arch]=%5Bw%7B%22%28caY4%28m%605A%7D%5B%2Cn8Eif%25%25%25E8%3FFg%3FC%3By%7BA%23Viv3SZVgAUhQ",
        "[arch]=Zk0%2A%2CgJjkL%3E%7CM%25b2W%60KZgY%5BjIaH%7DB-c%2CtfWv%2AdkpHR%29%7Cje",
        "[arch]=7%25%23a%40%7CyEptSf7_%3F%28SQ%60G%7CMc_Q8P1%3F",
    ),
)
def test_query_all_sp_filters_sql_char_contents(db_create_host, api_get, sp_filter_param):
    # Create host with this system profile
    sp_data = {
        "system_profile_facts": {
            "arch": "qbe]d?sdx`.{0`sTfX:GP&dp$kf;y0`F3;`^Z1aa-b-[:9$&s4",
            "host_type": "edge",
            "workloads": {"sap": {"sids": ["ABC", "DEF"]}},
            "system_memory_bytes": 8192,
        }
    }
    db_create_host(extra_data=sp_data)
    sp_data = {
        "system_profile_facts": {
            "arch": '%T^>GYlS"Q*2K:6v57YGLU5.7H*p#kEHqhTH1u6yEX:yaJyFkC',
            "host_type": "edge",
            "workloads": {"sap": {"sids": ["ABC", "DEF"]}},
            "system_memory_bytes": 8192,
        }
    }
    db_create_host(extra_data=sp_data)
    sp_data = {
        "system_profile_facts": {
            "arch": '0~j@TiIP^xYk&yoFc0f("El`73g2;"pqm%0z',
            "host_type": "edge",
            "workloads": {"sap": {"sids": ["ABC", "DEF"]}},
            "system_memory_bytes": 8192,
        }
    }
    db_create_host(extra_data=sp_data)
    sp_data = {
        "system_profile_facts": {
            "arch": '[w{"(caY4(m`5A}[,n8Eif%%%E8?Fg?C;y{A#Viv3SZVgAUhQ',
            "host_type": "edge",
            "workloads": {"sap": {"sids": ["ABC", "DEF"]}},
            "system_memory_bytes": 8192,
        }
    }
    db_create_host(extra_data=sp_data)
    sp_data = {
        "system_profile_facts": {
            "arch": "Zk0*,gJjkL>|M%b2W`KZgY[jIaH}B-c,tfWv*dkpHR)|je",
            "host_type": "edge",
            "workloads": {"sap": {"sids": ["ABC", "DEF"]}},
            "system_memory_bytes": 8192,
        }
    }
    db_create_host(extra_data=sp_data)
    sp_data = {
        "system_profile_facts": {
            "arch": "7%#a@|yEptSf7_?(SQ`G|Mc_Q8P1?",
            "host_type": "edge",
            "workloads": {"sap": {"sids": ["ABC", "DEF"]}},
            "system_memory_bytes": 8192,
        }
    }
    db_create_host(extra_data=sp_data)

    url = build_hosts_url(query=f"?filter[system_profile]{sp_filter_param}")

    response_status, response_data = api_get(url)

    # Assert that the request succeeds but no hosts are returned
    assert response_status == 200
    assert len(response_data["results"]) == 1


def test_query_sp_filters_os_and_rhc_client_id(db_create_host, api_get):
    # Create host with this system profile
    match_sp_data = {
        "system_profile_facts": {
            "arch": "x86_64",
            "insights_client_version": "3.0.1-2.el4_2",
            "host_type": "edge",
            "workloads": {"sap": {"sap_system": True, "sids": ["ABC", "DEF"]}},
            "bootc_status": {"booted": {"image": "quay.io/centos-bootc/fedora-bootc-cloud:eln"}},
            "systemd": {"failed_services": ["foo", "bar"]},
            "system_memory_bytes": 8292048963606259,
            "rhc_client_id": "6b655c07-0daf-4564-9e1b-f6fb95510370",
            "operating_system": {"name": "RHEL", "major": 8, "minor": 6},
        }
    }
    match_host_id = str(db_create_host(extra_data=match_sp_data).id)

    # Create host with differing SP
    nomatch_sp_data = {
        "system_profile_facts": {
            "arch": "ARM",
            "insights_client_version": "1.2.3",
            "greenboot_status": "green",
            "bootc_status": {"booted": {"image": "192.168.0.1:5000/foo/foo:latest"}},
            "workloads": {"sap": {"sids": ["DEF"]}},
            "number_of_cpus": 8,
        }
    }
    nomatch_host_id = str(db_create_host(extra_data=nomatch_sp_data).id)

    url = build_hosts_url(
        query="?filter[system_profile][operating_system][RHEL][version][eq][]=8.6&filter[system_profile][rhc_client_id][]=not_nil"  # noqa: E501
    )

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that only the matching host is returned
    response_ids = [result["id"] for result in response_data["results"]]
    assert match_host_id in response_ids
    assert nomatch_host_id not in response_ids


@pytest.mark.parametrize(
    "sp_filter_param",
    (
        "[bootc_status][is]=nil",
        "[bootc_status][is]=not_nil",
        "[bootc_status][booted][is]=nil",
        "[bootc_status][booted][is]=not_nil",
    ),
)
def test_query_sp_filters_query_on_object_with_is_successful_request(db_create_host, api_get, sp_filter_param):
    # Create host with this system profile
    match_sp_data = {
        "system_profile_facts": {
            "arch": "x86_64",
            "insights_client_version": "3.0.1-2.el4_2",
            "host_type": "edge",
            "workloads": {"sap": {"sap_system": True, "sids": ["ABC", "DEF"]}},
            "bootc_status": {"booted": {"image": "quay.io/centos-bootc/fedora-bootc-cloud:eln"}},
            "systemd": {"failed_services": ["foo", "bar"]},
            "system_memory_bytes": 8292048963606259,
            "rhc_client_id": "6b655c07-0daf-4564-9e1b-f6fb95510370",
            "operating_system": {"name": "RHEL", "major": 8, "minor": 6},
        }
    }
    db_create_host(extra_data=match_sp_data)

    url = build_hosts_url(query=f"?filter[system_profile]{sp_filter_param}")

    response_status, _ = api_get(url)

    assert response_status == 200


def test_api_hosts_get_system_profile_multiple_values_without_brackets(api_get):
    """Test that multiple values are not allowed for a field without brackets."""
    url = build_hosts_url(
        query="?filter[system_profile][workloads][mssql][version]=value1"
        + "&filter[system_profile][workloads][mssql][version]=value2"
    )
    response_status, response_data = api_get(url)
    assert response_status == 400
    assert "Param filter must be appended with [] to accept multiple values." in response_data["detail"]


def test_query_operating_system_and_sap_workload_presence_not_nil(db_create_host, api_get):
    """OS filter AND SAP workload presence (not_nil) narrow results; both must match."""
    rhel_86_os = {"name": "RHEL", "major": 8, "minor": 6}
    match_id = str(
        db_create_host(
            extra_data={
                "system_profile_facts": {
                    "operating_system": rhel_86_os,
                    "workloads": {"sap": {"sap_system": True}},
                }
            }
        ).id
    )
    same_os_no_sap = str(
        db_create_host(
            extra_data={
                "system_profile_facts": {
                    "operating_system": rhel_86_os,
                    "workloads": {},
                }
            }
        ).id
    )
    sap_wrong_os = str(
        db_create_host(
            extra_data={
                "system_profile_facts": {
                    "operating_system": {"name": "RHEL", "major": 7, "minor": 7},
                    "workloads": {"sap": {"sap_system": True}},
                }
            }
        ).id
    )

    url = build_hosts_url(
        query="?filter[system_profile][operating_system][RHEL][version][eq][]=8.6"
        "&filter[system_profile][workloads][sap][is]=not_nil"
    )
    response_status, response_data = api_get(url)
    assert response_status == 200
    response_ids = {r["id"] for r in response_data["results"]}
    assert response_ids == {match_id}
    assert same_os_no_sap not in response_ids
    assert sap_wrong_os not in response_ids


def test_query_workload_presence_or_logic_combined_with_operating_system_filter(db_create_host, api_get):
    """Top-level workload existence filters use OR among themselves; OS remains AND (narrowing)."""
    rhel_86_os = {"name": "RHEL", "major": 8, "minor": 6}
    sap_on_rhel86 = str(
        db_create_host(
            extra_data={
                "system_profile_facts": {
                    "operating_system": rhel_86_os,
                    "workloads": {"sap": {"sap_system": True}},
                }
            }
        ).id
    )
    ansible_on_rhel86 = str(
        db_create_host(
            extra_data={
                "system_profile_facts": {
                    "operating_system": rhel_86_os,
                    "workloads": {"ansible": {"controller_version": "1.2"}},
                }
            }
        ).id
    )
    sap_on_rhel77 = str(
        db_create_host(
            extra_data={
                "system_profile_facts": {
                    "operating_system": {"name": "RHEL", "major": 7, "minor": 7},
                    "workloads": {"sap": {"sap_system": True}},
                }
            }
        ).id
    )
    neither_on_rhel86 = str(
        db_create_host(
            extra_data={
                "system_profile_facts": {
                    "operating_system": rhel_86_os,
                    "workloads": {},
                }
            }
        ).id
    )

    url = build_hosts_url(
        query="?filter[system_profile][workloads][sap][is]=not_nil"
        "&filter[system_profile][workloads][ansible][is]=not_nil"
        "&filter[system_profile][operating_system][RHEL][version][eq][]=8.6"
    )
    response_status, response_data = api_get(url)
    assert response_status == 200
    response_ids = {r["id"] for r in response_data["results"]}
    assert response_ids == {sap_on_rhel86, ansible_on_rhel86}
    assert sap_on_rhel77 not in response_ids
    assert neither_on_rhel86 not in response_ids


def test_get_hosts_sp_workload_filters_no_matches(db_create_host, api_get):
    db_create_host(extra_data={"system_profile_facts": {"workloads": {"sap": {"sap_system": False}}}})
    db_create_host(extra_data={"system_profile_facts": {"workloads": {"sap": {"sids": ["ABC", "DEF"]}}}})
    db_create_host(extra_data={"system_profile_facts": {"workloads": {"ansible": {}}}})

    url = build_hosts_url(
        query="?filter[system_profile][workloads][sap][sids][contains][]=NONEXISTENT_SID"
        "&filter[system_profile][workloads][sap][sap_system][]=true"
        "&filter[system_profile][workloads][ansible][controller_version][is]=not_nil"
    )
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["results"] == []


def test_workloads_exists_subquery_with_mixed_static_sp_filter(db_create_host, api_get):
    """When workloads filter is combined with a static SP filter (e.g. arch),
    the static filter must stay on the outer query, not inside EXISTS over dynamic table.
    Verifies both filters narrow results correctly (AND semantics).
    """
    match_host = str(
        db_create_host(
            extra_data={
                "system_profile_facts": {
                    "arch": "x86_64",
                    "workloads": {"sap": {"sap_system": True}},
                }
            }
        ).id
    )
    wrong_arch = str(
        db_create_host(
            extra_data={
                "system_profile_facts": {
                    "arch": "aarch64",
                    "workloads": {"sap": {"sap_system": True}},
                }
            }
        ).id
    )
    no_sap = str(
        db_create_host(
            extra_data={
                "system_profile_facts": {
                    "arch": "x86_64",
                    "workloads": {"sap": {"sap_system": False}},
                }
            }
        ).id
    )

    url = build_hosts_url(
        query="?filter[system_profile][arch]=x86_64&filter[system_profile][workloads][sap][sap_system]=true"
    )
    response_status, response_data = api_get(url)
    assert response_status == 200
    response_ids = {r["id"] for r in response_data["results"]}
    assert match_host in response_ids
    assert wrong_arch not in response_ids
    assert no_sap not in response_ids


def test_system_profile_nil_not_nil_not_escaped(
    db_create_host: Callable[..., Host],
    api_get: Callable[..., tuple[int, dict]],
) -> None:
    # Create a host with insights_client_version key
    host_with_val = db_create_host(extra_data={"system_profile_facts": {"insights_client_version": "Version1"}})
    # Create a host without insights_client_version key
    host_without_val = db_create_host(extra_data={"system_profile_facts": {}})

    # 1. Query with nil: should return host_without_val, but not host_with_val
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=nil")
    status, response = api_get(url)
    assert status == 200
    ids = [r["id"] for r in response["results"]]
    assert str(host_without_val.id) in ids
    assert str(host_with_val.id) not in ids

    # 2. Query with not_nil: should return host_with_val, but not host_without_val
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=not_nil")
    status, response = api_get(url)
    assert status == 200
    ids = [r["id"] for r in response["results"]]
    assert str(host_with_val.id) in ids
    assert str(host_without_val.id) not in ids
