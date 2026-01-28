import logging
from collections.abc import Callable
from datetime import datetime
from random import sample

import pytest
from iqe.utils.blockers import iqe_blocker

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.api_utils import build_query_string
from iqe_host_inventory.utils.datagen_utils import SYSTEM_PROFILE
from iqe_host_inventory.utils.datagen_utils import Field
from iqe_host_inventory.utils.datagen_utils import fields_having
from iqe_host_inventory.utils.datagen_utils import generate_sp_field_value
from iqe_host_inventory.utils.datagen_utils import get_sp_field_by_name
from iqe_host_inventory.utils.datagen_utils import parametrize_field
from iqe_host_inventory.utils.datagen_utils import sync_workloads_with_individual_fields
from iqe_host_inventory_api import ApiException

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)

# Legacy workloads field mappings (RHINENG-21482)
# Maps legacy field names to their corresponding paths in workloads.*
# Used to verify backward compatibility returns correct values from workloads.*
# Note: rhel_ai is NOT included because its legacy structure differs from workloads.rhel_ai
LEGACY_FIELD_TO_WORKLOADS_PATH: dict[str, tuple[str, ...]] = {
    # SAP flat fields (root level) → workloads.sap.*
    "sap_system": ("sap", "sap_system"),
    "sap_sids": ("sap", "sids"),
    "sap_instance_number": ("sap", "instance_number"),
    "sap_version": ("sap", "version"),
    # SAP nested object → workloads.sap
    "sap": ("sap",),
    # Direct workload mappings → workloads.*
    "ansible": ("ansible",),
    "mssql": ("mssql",),
    "intersystems": ("intersystems",),
    # CrowdStrike: third_party_services.crowdstrike → workloads.crowdstrike
    "third_party_services": ("crowdstrike",),
}

# Derived set of all legacy field names
LEGACY_WORKLOADS_FIELDS = set(LEGACY_FIELD_TO_WORKLOADS_PATH.keys())


def get_expected_value_from_workloads(system_profile: dict, field_name: str):
    """
    Get the expected value for a legacy field from workloads.* structure.

    Args:
        system_profile: The system profile dictionary containing workloads.*
        field_name: The legacy field name (e.g., 'sap_sids', 'ansible')

    Returns:
        The expected value from workloads.* that should match the legacy field
    """
    if field_name not in LEGACY_FIELD_TO_WORKLOADS_PATH:
        raise ValueError(f"Field '{field_name}' is not a legacy workload field")

    workload_path = LEGACY_FIELD_TO_WORKLOADS_PATH[field_name]
    expected_value = system_profile["workloads"]

    for key in workload_path:
        expected_value = expected_value[key]

    return expected_value


@pytest.fixture
def host_for_fields_tests(host_inventory: ApplicationHostInventory):
    host_data = host_inventory.datagen.create_host_data()
    # Generate all system profile fields including workloads
    for field in SYSTEM_PROFILE:
        host_data["system_profile"][field.name] = generate_sp_field_value(field)

    # Sync workloads.* with individual legacy fields to ensure consistency
    # This ensures workloads.sap matches sap.*, workloads.ansible matches ansible.*, etc.
    host_data["system_profile"] = sync_workloads_with_individual_fields(
        host_data["system_profile"]
    )

    return host_inventory.kafka.create_host(host_data=host_data)


def get_hosts_list_fields(
    host_inventory: ApplicationHostInventory,
    host: HostWrapper,
    sp_fields: list[Field],
):
    fields = [field.name for field in sp_fields]
    response = host_inventory.apis.hosts.get_hosts_response(fields=fields)
    for response_host in response.results:
        if response_host.id == host.id:
            return response_host
    pytest.fail(f"Desired host ({host}) not found. Found hosts: {response.results}")


def get_host_by_id_fields(
    host_inventory: ApplicationHostInventory,
    host: HostWrapper,
    sp_fields: list[Field],
):
    fields = [field.name for field in sp_fields]
    return host_inventory.apis.hosts.get_hosts_by_id([host.id], fields=fields)[0]


def get_host_system_profile_fields(
    host_inventory: ApplicationHostInventory,
    host: HostWrapper,
    sp_fields: list[Field],
):
    fields = [field.name for field in sp_fields]
    return host_inventory.apis.hosts.get_hosts_system_profile([host.id], fields=fields)[0]


@pytest.fixture(
    params=[
        pytest.param(get_hosts_list_fields, id="/hosts"),
        pytest.param(get_host_by_id_fields, id="/hosts/<host_id_list>"),
        pytest.param(get_host_system_profile_fields, id="/hosts/<host_id_list>/system_profile"),
    ],
)
def endpoint_func(request):
    return request.param


# Fields that are not available as top-level sparse fields
# rhel_ai: Stored only in workloads.rhel_ai with different structure than legacy rhel_ai
SKIP_SPARSE_FIELDS = {"rhel_ai"}


@pytest.mark.ephemeral
@parametrize_field(SYSTEM_PROFILE)
def test_get_specific_fields(
    host_inventory: ApplicationHostInventory,
    host_for_fields_tests,
    field,
    endpoint_func: Callable,
):
    """
    metadata:
        requirements: inv-hosts-get-specific-sp-fields
        importance: high
        assignee: rpfannsc
    """
    if field.name in SKIP_SPARSE_FIELDS:
        pytest.skip(f"Field '{field.name}' is not available as a top-level sparse field")

    returned_host = endpoint_func(host_inventory, host_for_fields_tests, [field])
    returned_sp = {
        k: v for k, v in returned_host.system_profile.to_dict().items() if v is not None
    }

    assert set(returned_sp) == {field.name}

    # For legacy fields, verify they're populated from workloads.* via backward compatibility
    if field.name in LEGACY_WORKLOADS_FIELDS:
        expected_value = get_expected_value_from_workloads(
            host_for_fields_tests.system_profile, field.name
        )

        # For third_party_services, the returned value is nested under crowdstrike
        if field.name == "third_party_services":
            assert returned_sp[field.name]["crowdstrike"] == expected_value
        else:
            assert returned_sp[field.name] == expected_value
    else:
        # For non-legacy fields, compare against the field value directly
        if isinstance(returned_sp[field.name], datetime):
            assert returned_sp[field.name] == datetime.fromisoformat(
                host_for_fields_tests.system_profile[field.name]
            )
        else:
            assert returned_sp[field.name] == host_for_fields_tests.system_profile[field.name]


@pytest.mark.ephemeral
def test_get_specific_fields_multiple_fields(
    host_inventory: ApplicationHostInventory,
    host_for_fields_tests,
    endpoint_func: Callable,
):
    """
    metadata:
        requirements: inv-hosts-get-specific-sp-fields
        assignee: rpfannsc
        importance: high
    """
    # Sample 20 random fields including legacy fields, but exclude fields not available as sparse
    available_fields = [
        f
        for f in fields_having(SYSTEM_PROFILE, x_indexed=True)
        if f.name not in SKIP_SPARSE_FIELDS
    ]
    wanted_fields = sample(available_fields, min(20, len(available_fields)))

    returned_host = endpoint_func(host_inventory, host_for_fields_tests, wanted_fields)
    returned_sp = {
        k: v for k, v in returned_host.system_profile.to_dict().items() if v is not None
    }

    assert set(returned_sp) == {field.name for field in wanted_fields}

    for field in wanted_fields:
        # For legacy fields, verify they're populated from workloads.* via backward compatibility
        if field.name in LEGACY_WORKLOADS_FIELDS:
            expected_value = get_expected_value_from_workloads(
                host_for_fields_tests.system_profile, field.name
            )

            # For third_party_services, the returned value is nested under crowdstrike
            if field.name == "third_party_services":
                assert returned_sp[field.name]["crowdstrike"] == expected_value
            else:
                assert returned_sp[field.name] == expected_value
        else:
            # For non-legacy fields, compare against the field value directly
            if isinstance(returned_sp[field.name], datetime):
                assert returned_sp[field.name] == datetime.fromisoformat(
                    host_for_fields_tests.system_profile[field.name]
                )
            else:
                assert returned_sp[field.name] == host_for_fields_tests.system_profile[field.name]


@pytest.mark.ephemeral
@iqe_blocker(iqe_blocker.jira("RHINENG-11389", category=iqe_blocker.PRODUCT_ISSUE))
def test_get_specific_fields_bad_field(
    host_inventory,
    host_for_fields_tests,
    endpoint_func: Callable,
):
    """
    metadata:
        requirements: inv-hosts-get-specific-sp-fields, inv-api-validation
        assignee: rpfannsc
        importance: low
        negative: true
    """
    with pytest.raises(ApiException) as excinfo:
        endpoint_func(host_inventory, host_for_fields_tests, [Field("bad_field", "str")])

    assert excinfo.value.status == 400
    assert (
        "Requested field 'bad_field' is not present in the system_profile schema."
        in excinfo.value.body
    )


@pytest.mark.ephemeral
@iqe_blocker(iqe_blocker.jira("RHINENG-11389", category=iqe_blocker.PRODUCT_ISSUE))
def test_get_specific_fields_bad_type(
    host_inventory,
    host_for_fields_tests,
    endpoint_func: Callable,
):
    """
    metadata:
        requirements: inv-hosts-get-specific-sp-fields, inv-api-validation
        assignee: rpfannsc
        negative: true
        importance: low

    REVISIT: With the api filter client removal work, this test will no longer
    work as intended.  The url is now built in the hosts_api wrapper and the
    endpoint_func no longer takes a query_prefix (leaving it here for context).
    Since the test is low priority and currently blocked by a product issue,
    revisit it at a later time.
    """

    with pytest.raises(ApiException) as excinfo:
        endpoint_func(
            host_inventory,
            host_for_fields_tests,
            [get_sp_field_by_name("operating_system")],
            query_prefix="fields[system_failure]=",
        )
    assert excinfo.value.status == 400
    assert (
        "The browser (or proxy) sent a request that this server could not understand."
        in excinfo.value.body
    )


# Note: When retrieving hosts, most tests now use the default response_type
# HostQueryOutput (or HostSystemProfileHostOut), which has the drawback that
# all system_profile fields are returned no matter what fields are selected.
# Unselected fields are set to 'None' in these cases.  The following tests set
# the response_type to object. In these cases, only the selected fields are
# returned.  This distinction is not a product issue but rather an openapi
# client issue.


def _call_api(
    host_inventory: ApplicationHostInventory, path: str, *, fields: list[str] | None = None
) -> dict:
    """Return host info with the desired fields.  This helper is specific to
    the test cases that follow.

    :param ApplicationHostInventory host_inventory: host_inventory object
    :param str path: Path endpoint
    :param list[str] fields: List of desired fields
    :return dict: Host info
    """
    query = build_query_string(fields=fields)
    if query:
        path += "?" + query

    return host_inventory.apis.hosts.api_client.call_api(
        path, "GET", response_type=object, _return_http_data_only=True
    )


@pytest.mark.ephemeral
def test_get_host_list_selected_fields(
    host_inventory: ApplicationHostInventory,
    host_for_fields_tests,
):
    """
    metadata:
        requirements: inv-hosts-get-specific-sp-fields
        assignee: msager
        importance: high
        title: Verify that GET /hosts returns only the selected fields
    """
    # Sample 20 random fields including legacy fields, but exclude fields not available as sparse
    available_fields = [
        f
        for f in fields_having(SYSTEM_PROFILE, x_indexed=True)
        if f.name not in SKIP_SPARSE_FIELDS
    ]
    selected_fields = sample(available_fields, min(20, len(available_fields)))
    fields = [field.name for field in selected_fields]

    response_hosts = _call_api(host_inventory, "/hosts", fields=fields)["results"]

    for host in response_hosts:
        response_fields = host["system_profile"].keys()
        if host["id"] == host_for_fields_tests.id:
            assert set(response_fields) == set(fields)
        else:
            assert set(response_fields).issubset(set(fields))


@pytest.mark.ephemeral
def test_get_host_by_id_selected_fields(
    host_inventory: ApplicationHostInventory,
    host_for_fields_tests,
):
    """
    metadata:
        requirements: inv-hosts-get-specific-sp-fields
        assignee: msager
        importance: high
        title: Verify that GET /hosts/{host_id} returns only the selected fields
    """
    host = host_for_fields_tests

    # Sample 20 random fields including legacy fields, but exclude fields not available as sparse
    available_fields = [
        f
        for f in fields_having(SYSTEM_PROFILE, x_indexed=True)
        if f.name not in SKIP_SPARSE_FIELDS
    ]
    selected_fields = sample(available_fields, min(20, len(available_fields)))
    fields = [field.name for field in selected_fields]

    response_host = _call_api(host_inventory, f"/hosts/{host.id}", fields=fields)["results"][0]

    response_fields = response_host["system_profile"].keys()
    assert set(response_fields) == set(fields)


@pytest.mark.ephemeral
def test_get_host_system_profile_by_id_selected_fields(
    host_inventory: ApplicationHostInventory,
    host_for_fields_tests,
):
    """
    metadata:
        requirements: inv-hosts-get-specific-sp-fields
        assignee: msager
        importance: high
        title: Verify that GET /hosts/{host_id}/system_profile returns only
            the selected fields
    """
    host = host_for_fields_tests

    # Sample 20 random fields including legacy fields, but exclude fields not available as sparse
    available_fields = [
        f
        for f in fields_having(SYSTEM_PROFILE, x_indexed=True)
        if f.name not in SKIP_SPARSE_FIELDS
    ]
    selected_fields = sample(available_fields, min(20, len(available_fields)))
    fields = [field.name for field in selected_fields]

    response = _call_api(host_inventory, f"/hosts/{host.id}/system_profile", fields=fields)[
        "results"
    ][0]

    response_fields = response["system_profile"].keys()
    assert set(response_fields) == set(fields)
