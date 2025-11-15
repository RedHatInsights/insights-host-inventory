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
from iqe_host_inventory_api import ApiException

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


@pytest.fixture
def host_for_fields_tests(host_inventory: ApplicationHostInventory):
    host_data = host_inventory.datagen.create_host_data()
    for field in SYSTEM_PROFILE:
        host_data["system_profile"][field.name] = generate_sp_field_value(field)
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
    wanted_fields = sample(fields_having(SYSTEM_PROFILE, x_indexed=True), 20)

    returned_host = endpoint_func(host_inventory, host_for_fields_tests, wanted_fields)
    returned_sp = {
        k: v for k, v in returned_host.system_profile.to_dict().items() if v is not None
    }

    assert set(returned_sp) == {field.name for field in wanted_fields}

    for field in wanted_fields:
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
    selected_fields = sample(fields_having(SYSTEM_PROFILE, x_indexed=True), 20)
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

    selected_fields = sample(fields_having(SYSTEM_PROFILE, x_indexed=True), 20)
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

    selected_fields = sample(fields_having(SYSTEM_PROFILE, x_indexed=True), 20)
    fields = [field.name for field in selected_fields]

    response = _call_api(host_inventory, f"/hosts/{host.id}/system_profile", fields=fields)[
        "results"
    ][0]

    response_fields = response["system_profile"].keys()
    assert set(response_fields) == set(fields)
