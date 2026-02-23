from __future__ import annotations

import logging
import multiprocessing
import warnings
from collections.abc import Callable
from collections.abc import Collection
from collections.abc import Generator
from contextlib import contextmanager
from functools import partial
from time import sleep
from typing import TYPE_CHECKING
from typing import Any
from typing import Protocol
from typing import TypeVar
from urllib.parse import quote

import pytest
from _pytest._code.code import ExceptionInfo

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.deprecations import DEPRECATE_ASYNC_GET_MULTIPLE_HOSTS
from iqe_host_inventory.schemas import PER_REPORTER_STALENESS
from iqe_host_inventory.utils import get_org_id
from iqe_host_inventory.utils.tag_utils import convert_tag_to_string
from iqe_host_inventory_api import ApiException as ApiException_V4
from iqe_host_inventory_api import HostOut
from iqe_host_inventory_api import HostQueryOutput
from iqe_host_inventory_api import HostsApi
from iqe_host_inventory_api import SystemProfileApi
from iqe_host_inventory_api import TagsApi
from iqe_host_inventory_api.api_client import ApiClient
from iqe_host_inventory_api_v7 import ApiException as ApiException_V7

from .retrying import accept_when

if TYPE_CHECKING:
    from iqe_host_inventory.modeling import HBI_API_WRAPPER


logger = logging.getLogger(__name__)

_COLLECTION_PARAMS = (
    "group_name",
    "group_id",
    "staleness",
    "tags",
    "registered_with",
    "system_type",
)


class HasApiClient(Protocol):
    api_client: ApiClient


T = TypeVar("T", bound=HasApiClient)


@contextmanager
def api_disabled_validation[T: HasApiClient](api: T) -> Generator[T]:
    """Temporarily disable client-side validation on the API client."""
    api.api_client.client_side_validation = False
    try:
        yield api
    finally:
        api.api_client.client_side_validation = True


@contextmanager
def temp_headers(api: HasApiClient, headers: dict | None = None) -> Generator[HasApiClient]:
    with headers_patched(api, headers):
        with api_disabled_validation(api) as api_no_validation:
            yield api_no_validation


@contextmanager
def headers_patched(
    api: ApiClient | HasApiClient, headers: dict[str, object] | None = None
) -> Generator[None]:
    client: ApiClient = api if isinstance(api, ApiClient) else api.api_client

    # todo: move to framework
    if headers is not None:
        old_headers = client.default_headers
        client.default_headers = {**old_headers, **headers}
        try:
            yield
        finally:
            client.default_headers = old_headers
    else:
        yield


def async_get_multiple_hosts_by_insights_id(
    openapi_client: HostsApi,
    insights_id_list: list,
    hosts: list | None = None,
    retry_attempt: int = 0,
) -> list[HostOut]:
    warnings.warn(DEPRECATE_ASYNC_GET_MULTIPLE_HOSTS, stacklevel=2)

    hosts = hosts or []

    openapi_client.api_client.pool_threads = multiprocessing.cpu_count()

    threads = []
    for insights_id in insights_id_list:
        thread = openapi_client.api_host_get_host_list(insights_id=insights_id, async_req=True)
        threads.append(thread)

    for thread in threads:
        response = thread.get()
        if response.count == 1:
            host = response.results[0]
            insights_id_list.remove(host.insights_id)
            hosts.append(host)

    if len(insights_id_list) > 0 and retry_attempt < 50:
        retry_attempt = retry_attempt + 1
        sleep(1)

        return async_get_multiple_hosts_by_insights_id(
            openapi_client, insights_id_list, hosts, retry_attempt
        )

    openapi_client.api_client.pool_threads = 1

    return hosts


def get_hosts(
    openapi_client: HostsApi, criteria, headers=None, **filter_kwargs
) -> HostQueryOutput:
    with headers_patched(openapi_client, headers):
        return acceptance(
            openapi_client.api_host_get_host_list, criteria=criteria, **filter_kwargs
        )


def get_host_staleness(openapi_client: HostsApi, host_id: str) -> PER_REPORTER_STALENESS:
    get_hosts(openapi_client, [(criterion_host_in, host_id)])
    return openapi_client.api_host_get_host_by_id([host_id]).results[0].per_reporter_staleness


def get_sap_systems(openapi_client: SystemProfileApi, criteria, headers=None, **api_kwargs):
    with headers_patched(openapi_client, headers):
        return acceptance(
            openapi_client.api_system_profile_get_sap_system, criteria=criteria, **api_kwargs
        )


def get_sap_sids(openapi_client: SystemProfileApi, criteria, headers=None, **api_kwargs):
    with headers_patched(openapi_client, headers):
        return acceptance(
            openapi_client.api_system_profile_get_sap_sids, criteria=criteria, **api_kwargs
        )


def get_operating_systems(openapi_client: SystemProfileApi, criteria, headers=None, **api_kwargs):
    with headers_patched(openapi_client, headers):
        return acceptance(
            openapi_client.api_system_profile_get_operating_system, criteria=criteria, **api_kwargs
        )


def delete_hosts_matching(host_list, openapi_client: HostsApi):
    """Delete all hosts specified in host_list."""
    hosts_to_delete = []
    for host in host_list:
        full_host = acceptance(
            openapi_client.api_host_get_host_list,
            insights_id=host["insights_id"],
            criteria=[(criterion_insights_id_in, host["insights_id"])],
        )
        if len(full_host.results) == 0:
            continue
        host_id = full_host.results[0].id
        if host_id is not None:
            hosts_to_delete.append(host_id)

    delete_hosts(hosts_to_delete, openapi_client)


def delete_hosts(host_list: list[Any], openapi_client: HostsApi) -> None:
    from iqe_host_inventory.modeling.hosts_api import _ids_from_hosts

    host_id_list = _ids_from_hosts(host_list)
    logger.info(f"Deleting hosts {host_id_list}")
    try:
        while host_id_list:
            openapi_client.api_host_delete_host_by_id(host_id_list[:50])
            acceptance(
                openapi_client.api_host_get_host_by_id,
                host_id_list[:50],
                criteria=[(criterion_hosts_not_in, host_id_list[:50])],
            )
            host_id_list = host_id_list[50:]
    except ApiException_V4 as err:
        if err.status == 404:
            logger.info(f"Couldn't delete hosts {host_id_list}, because they were not found.")
        else:
            logger.info(f"ERROR while deleting hosts: {err}")
            raise


def delete_hosts_by_tags(tag_search_term, openapi_client: HostsApi, openapi_client_tags: TagsApi):
    tags = []
    response = openapi_client_tags.api_tag_get_tags(search=tag_search_term)
    tags.extend(convert_tag_to_string(tag.tag.to_dict()) for tag in response.results)
    pages = response.total // 50 + (response.total % 50 > 0)
    for page in range(2, pages + 1):
        response = openapi_client_tags.api_tag_get_tags(search=tag_search_term, page=page)
        tags.extend(convert_tag_to_string(tag.tag.to_dict()) for tag in response.results)
    logger.info(f"Deleting hosts by {len(tags)} tags: " + str(tags))

    hosts = []
    for tag in tags:
        response = openapi_client.api_host_get_host_list(tags=[tag])
        hosts.extend(response.results)
        # Prevent from "Request Line is too large" error when deleting too many hosts at once
        if len(hosts) >= 50:
            delete_hosts(hosts, openapi_client)
            hosts = []
    if len(hosts):
        delete_hosts(hosts, openapi_client)


def criterion_count_eq(response, expected_count: int) -> bool:
    return response.count == expected_count


def criterion_count_gte(response, expected_count: int):
    return response.count >= expected_count


def criterion_total_eq(response, expected_count):
    return response.total == expected_count


def criterion_total_gte(response, expected_count):
    return response.total >= expected_count


def criterion_host_id_eq(response, host_id):
    return response.results[0].id == host_id


def criterion_insights_id_eq(response, insights_id):
    return response.results[0].insights_id == insights_id


def criterion_display_name_eq(response, display_name):
    return response.results[0].display_name == display_name


def criterion_hostname_eq(response, hostname):
    # todo: lwer was added for the hostname seach fixture, replace with better api
    return (
        response.results[0].display_name.lower() == hostname.lower()
        or response.results[0].fqdn == hostname
    )


def criterion_host_not_in(response, host_id):
    return host_id not in {host.id for host in response.results}


def criterion_host_in(response, host_id):
    return host_id in {host.id for host in response.results}


def criterion_hosts_not_in(response, hosts_ids):
    return all(host_id not in {host.id for host in response.results} for host_id in hosts_ids)


def criterion_hosts_in(response, hosts_ids: list):
    return all(host_id in {host.id for host in response.results} for host_id in hosts_ids)


def criterion_insights_id_in(response, insights_id):
    return insights_id in {host.insights_id for host in response.results}


def criterion_ansible_host_in(response, ansible_host):
    return ansible_host in {host.ansible_host for host in response.results}


def acceptance(func, *func_args, criteria, delay=0.5, retries=10, **func_kwargs):
    """
    This function was created to address the delay issue that came with
    the usage of xjoin as a datasource.

    When HBI is set to use xjoin as a datasource there is a delay between creating a host
    and then to be able to search that host.

    JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-4152

    :param func: open api request function
    :param func_args: open api request parameters
    :param criteria: list of criterion to be verified
    :param delay: time before retrying the request
    :param retries: number of retries
    :param func_kwargs: open api named request parameters
    :return: request response
    """

    def is_valid(response):
        return all(
            validator_function(response, expected_result)
            for validator_function, expected_result in criteria
        )

    return accept_when(
        partial(func, *func_args, **func_kwargs),
        is_valid=is_valid,
        delay=delay,
        retries=retries,
        error=None,
    )


@contextmanager
def raises_apierror(
    expected_status: int | tuple[int, ...], match_message: str | tuple[str, ...] | None = None
) -> Generator[ExceptionInfo[ApiException_V4] | ExceptionInfo[ApiException_V7]]:
    exc: ExceptionInfo[ApiException_V4] | ExceptionInfo[ApiException_V7]
    with pytest.raises((ApiException_V4, ApiException_V7)) as exc:
        yield exc

    api_error = exc.value
    logger.info(f"API ERROR: Status: {api_error.status}, Body: {api_error.body}")
    if isinstance(expected_status, int):
        assert api_error.status == expected_status, (
            f"Expected status: {expected_status}, Returned status: {api_error.status}"
        )
    else:
        assert api_error.status in expected_status, (
            f"Expected status one of: {expected_status}, Returned status: {api_error.status}"
        )

    if match_message is not None:
        assert api_error.body is not None  # type guard for bad openapi code
        if isinstance(match_message, str):
            match_message = (match_message,)

        for message in match_message:
            assert message in api_error.body, f"'{message}' not in error message: {api_error.body}"


def find_nested_fields(field_name: str, data: dict | list) -> Generator[str]:
    def _find_in_list(list_data: list) -> Generator[str]:
        for item in list_data:
            if isinstance(item, (dict, list)):
                yield from find_nested_fields(field_name, item)

    if isinstance(data, list):
        yield from _find_in_list(data)
    else:
        for key, value in data.items():
            if key == field_name:
                yield value
            if isinstance(value, dict):
                yield from find_nested_fields(field_name, value)
            if isinstance(value, list):
                yield from _find_in_list(value)


def check_org_id(api_wrapper_method: Callable):
    """
    Use this as a decorator in all the API Wrappers methods where we use raw OpenAPI methods.
    This decorator will check the `org_id` in all data received in any API response. This will
    help us catch critical security (data leaking) bugs.
    If the API endpoint doesn't return org_ids in the response, this decorator won't do anything.

    Currently, only these endpoints return org_ids in the response:

    - GET /account/staleness
    - PATCH /account/staleness
    - POST /account/staleness
    - GET /account/staleness/defaults

    - GET /groups
    - POST /groups
    - GET /groups/<groups_ids>
    - PATCH /groups/<groups_ids>
    - POST /groups/<groups_ids>/hosts

    - GET /hosts
    - POST /hosts/checkin
    - GET /hosts/<hosts_ids>

    - GET /resource-types/inventory-groups
    """

    def _method_wrapper(self: HBI_API_WRAPPER, *args, **kwargs):
        orig_response = api_wrapper_method(self, *args, **kwargs)
        my_org_id = get_org_id(self.application)

        def _check_org_id(response_org_id: str):
            assert response_org_id == my_org_id, (
                f"Critical data leak! Org {my_org_id} accessed data from org {response_org_id}!"
            )

        if orig_response is None or orig_response == "":
            return orig_response

        if not isinstance(orig_response, dict):
            if not hasattr(orig_response, "to_dict"):
                raise AttributeError(f"Can't parse an API response of type {type(orig_response)}")
            dict_response = orig_response.to_dict()
        else:
            dict_response = orig_response

        for org_id in find_nested_fields("org_id", dict_response):
            _check_org_id(org_id)

        return orig_response

    return _method_wrapper


def build_query_string(
    filter: list[str] | None = None,
    fields: list[str] | None = None,
    **api_kwargs,
) -> str:
    """
    This helper processes parameters to form an api query string.

    :param list[str] filter: list of system_profile filters
    :param list[str] fields: list of system_profile fields
    :return: api query string

    All other params are assumed to be field names and their values.
    """

    query_params = []

    for key, val in api_kwargs.items():
        if key in _COLLECTION_PARAMS and isinstance(val, (list, tuple)):
            query_params.extend(f"{quote(key)}={quote(str(v))}" for v in val if v is not None)
        elif val is not None:
            query_params.append(f"{quote(key)}={quote(str(val))}")

    if filter is not None:
        query_params.extend(f"filter[system_profile]{f}" for f in filter)

    if fields is not None:
        query_params.append(f"fields[system_profile]={','.join(fields)}")

    return "&".join(query_params)


def set_per_page(
    per_page: int | None, items: Collection[Any], *, item_name: str = "item"
) -> int | None:
    """
    If per_page is set, check that it is higher than or equal to the number of requested items.
    If per_page is not set and the number of requested items is higher than the default
    per_page (50), set the per_page to the number of requested items, up to the maximum allowed
    number (100).
    """
    if per_page is not None and per_page < len(items):
        raise ValueError(
            f"per_page must be higher than or equal to the number of requested {item_name}s"
        )

    if per_page is None and len(items) > 50:
        return min(len(items), 100)

    return per_page


def is_ungrouped_host(host: HostOut):
    return len(host.groups) == 0 or (len(host.groups) == 1 and host.groups[0].ungrouped)


def ungrouped_host_groups(host_inventory: ApplicationHostInventory) -> list[dict | None]:
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    return [
        {
            "id": ungrouped_group.id,
            "name": ungrouped_group.name,
            "ungrouped": ungrouped_group.ungrouped,
        }
    ]
