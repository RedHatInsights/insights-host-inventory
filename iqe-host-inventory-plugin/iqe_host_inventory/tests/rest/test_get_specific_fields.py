import logging
from collections.abc import Callable
from datetime import datetime

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.api_utils import build_query_string
from iqe_host_inventory.utils.datagen_utils import LEGACY_WORKLOAD_ROOT_FIELDS
from iqe_host_inventory.utils.datagen_utils import SYSTEM_PROFILE
from iqe_host_inventory.utils.datagen_utils import Field
from iqe_host_inventory.utils.datagen_utils import generate_sp_field_value
from iqe_host_inventory.utils.datagen_utils import parametrize_field
from iqe_host_inventory.utils.datagen_utils import sync_workloads_with_individual_fields

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)

LEGACY_WORKLOAD_ROOT_FIELDS = set(LEGACY_WORKLOAD_ROOT_FIELDS)


@pytest.fixture
def host_for_fields_tests(host_inventory: ApplicationHostInventory):
    host_data = host_inventory.datagen.create_host_data()
    for field in SYSTEM_PROFILE:
        host_data["system_profile"][field.name] = generate_sp_field_value(field)

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
SKIP_SPARSE_FIELDS = LEGACY_WORKLOAD_ROOT_FIELDS


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

    if isinstance(returned_sp[field.name], datetime):
        assert returned_sp[field.name] == datetime.fromisoformat(
            host_for_fields_tests.system_profile[field.name]
        )
    else:
        assert returned_sp[field.name] == host_for_fields_tests.system_profile[field.name]


# Note: When retrieving hosts, most tests now use the default response_type
# HostQueryOutput (or HostSystemProfileHostOut), which has the drawback that
# all system_profile fields are returned no matter what fields are selected.
# Unselected fields are set to 'None' in these cases.  The following tests set
# the response_type to object. In these cases, only the selected fields are
# returned.  This distinction is not a product issue but rather an openapi
# client issue.


def _call_api(
    host_inventory: ApplicationHostInventory,
    path: str,
    *,
    fields: list[str] | None = None,
    build_fields_query: Callable = build_query_string,
) -> dict:
    """Return host info with the desired fields.  This helper is specific to
    the test cases that follow.

    :param ApplicationHostInventory host_inventory: host_inventory object
    :param str path: Path endpoint
    :param list[str] fields: List of desired fields
    :param build_fields_query: callable that builds the fields query string
    :return dict: Host info
    """
    if fields:
        path += "?" + build_fields_query(fields=fields)

    return host_inventory.apis.hosts.api_client.call_api(
        path, "GET", response_type=object, _return_http_data_only=True
    )
