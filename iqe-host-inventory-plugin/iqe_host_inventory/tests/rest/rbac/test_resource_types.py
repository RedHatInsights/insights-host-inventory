from __future__ import annotations

import logging
from math import ceil

import pytest
from pytest_lazy_fixtures import lf

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.groups_api import GroupData
from iqe_host_inventory.tests.rest.validation.test_system_profile import EMPTY_BASICS
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory_api import GroupOutWithHostCount
from iqe_host_inventory_api import ResourceTypesGroupsQueryOutput
from iqe_host_inventory_api import ResourceTypesOut
from iqe_host_inventory_api import ResourceTypesPaginationOutLinks
from iqe_host_inventory_api import ResourceTypesPaginationOutMeta
from iqe_host_inventory_api import ResourceTypesQueryOutput

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


def check_resource_types_list_response(
    response: ResourceTypesQueryOutput,
    groups_count: int,
    per_page: int | None = None,
    page: int | None = None,
):
    if per_page is None:
        per_page = 10
    if page is None:
        page = 1

    base_url = "/inventory/v1/resource-types"

    response_meta: ResourceTypesPaginationOutMeta = response.meta
    assert response_meta.count == 1

    response_links: ResourceTypesPaginationOutLinks = response.links
    assert response_links.first == f"{base_url}?per_page={per_page}&page=1"
    assert response_links.last == f"{base_url}?per_page={per_page}&page=1"

    if page == 1:
        assert response_links.previous is None
    else:
        assert response_links.previous == f"{base_url}?per_page={per_page}&page={page - 1}"

    assert response_links.next is None

    response_data: list[ResourceTypesOut] = response.data
    assert len(response_data) == 1
    assert response_data[0].count == groups_count
    assert response_data[0].value == "inventory-groups"
    assert response_data[0].path == f"{base_url}/inventory-groups"


def check_resource_types_groups_response(
    response: ResourceTypesGroupsQueryOutput,
    groups_count: int,
    per_page: int | None = None,
    page: int | None = None,
) -> list[GroupOutWithHostCount]:
    if per_page is None:
        per_page = 10
    if page is None:
        page = 1

    base_url = "/inventory/v1/resource-types/inventory-groups"
    last_page = ceil(groups_count / per_page)

    response_meta: ResourceTypesPaginationOutMeta = response.meta
    assert response_meta.count == groups_count

    response_links: ResourceTypesPaginationOutLinks = response.links
    assert response_links.first == f"{base_url}?per_page={per_page}&page=1"
    assert response_links.last == f"{base_url}?per_page={per_page}&page={last_page}"

    if page == 1:
        assert response_links.previous is None
    else:
        assert response_links.previous == f"{base_url}?per_page={per_page}&page={page - 1}"

    if page >= last_page:
        assert response_links.next is None
    else:
        assert response_links.next == f"{base_url}?per_page={per_page}&page={page + 1}"

    response_data: list[GroupOutWithHostCount] = response.data
    groups_ids = [group.id for group in response_data]
    assert None not in response_data
    assert None not in groups_ids
    assert "" not in groups_ids
    assert len(set(groups_ids)) == len(groups_ids)
    return response_data


def test_resource_types_get_list_without_groups(host_inventory):
    """WARNING: Don't run this test in shared accounts. It deletes all groups on account.

    https://issues.redhat.com/browse/ESSNTL-3827

    metadata:
      requirements: inv-resource-types-list
      assignee: fstavela
      importance: medium
      title: Get resource types list without any groups
    """
    host_inventory.apis.groups.delete_all_groups()
    response = host_inventory.apis.resource_types.get_resource_types_response()
    check_resource_types_list_response(response, 1)


@pytest.mark.ephemeral
def test_resource_types_get_list_with_group_with_host(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3827

    metadata:
      requirements: inv-resource-types-list
      assignee: fstavela
      importance: high
      title: Get resource types list with existing groups with hosts
    """
    host = host_inventory.kafka.create_host()
    host_inventory.apis.groups.create_group(generate_display_name(), hosts=host)

    response = host_inventory.apis.resource_types.get_resource_types_response()
    groups_count = host_inventory.apis.groups.get_groups_response(group_type="all").total
    check_resource_types_list_response(response, groups_count)


def test_resource_types_get_groups_without_groups(host_inventory):
    """WARNING: Don't run this test in shared accounts. It deletes all groups on account.

    https://issues.redhat.com/browse/ESSNTL-3827

    metadata:
      requirements: inv-resource-types-groups
      assignee: fstavela
      importance: medium
      title: Get groups resources without any groups
    """
    host_inventory.apis.groups.delete_all_groups()
    response = host_inventory.apis.resource_types.get_groups_response()
    groups = check_resource_types_groups_response(response, 0)
    assert groups == []


@pytest.mark.ephemeral
def test_resource_types_get_groups_with_group_with_host(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3827

    metadata:
      requirements: inv-resource-types-groups
      assignee: fstavela
      importance: high
      title: Get groups resources with existing groups with hosts
    """
    host = host_inventory.kafka.create_host()
    host_inventory.apis.groups.create_group(generate_display_name(), hosts=host)

    response = host_inventory.apis.resource_types.get_groups_response()
    groups_count = host_inventory.apis.groups.get_groups_response().total
    groups = check_resource_types_groups_response(response, groups_count)
    if groups_count >= 10:
        assert len(groups) == 10
    else:
        assert len(groups) == groups_count


@pytest.mark.ephemeral
@pytest.mark.parametrize("with_hosts", [True, False], ids=["with hosts", "without hosts"])
def test_resource_types_get_groups_pagination_only_my_groups(
    host_inventory: ApplicationHostInventory,
    with_hosts: bool,
):
    """WARNING: Don't run this test in shared accounts. It deletes all groups on account.

    https://issues.redhat.com/browse/ESSNTL-3827

    metadata:
      requirements: inv-resource-types-groups
      assignee: fstavela
      importance: high
      title: Test pagination while getting groups resources with limited amount of groups
    """
    host_inventory.apis.groups.delete_all_groups()

    hosts = host_inventory.kafka.create_random_hosts(10)

    groups_data = [GroupData(hosts=[hosts[i]] if with_hosts else []) for i in range(10)]
    groups = host_inventory.apis.groups.create_groups(groups_data)
    all_groups_ids = {group.id for group in groups}

    found_groups_ids = set()
    for i in range(4):
        response = host_inventory.apis.resource_types.get_groups_response(per_page=3, page=i + 1)
        response_groups = check_resource_types_groups_response(
            response, 10, per_page=3, page=i + 1
        )
        if i == 3:
            # last page
            assert len(response_groups) == 1
        else:
            assert len(response_groups) == 3
        found_groups_ids.update({group.id for group in response_groups})

    assert found_groups_ids == all_groups_ids


class TestResourceTypesEmptyGroups:
    """
    This class is used for test scenarios on resource-types endpoints
    that use just empty groups and don't require any special groups or hosts.
    """

    @pytest.mark.parametrize("page", [None, 1])
    @pytest.mark.parametrize("per_page", [None, 1, 10, 100])
    def test_resource_types_get_list_with_empty_groups(
        self, setup_empty_groups_primary, host_inventory, page, per_page
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3827

        metadata:
          requirements: inv-resource-types-list
          assignee: fstavela
          importance: high
          title: Get resource types list with existing empty groups
        """
        response = host_inventory.apis.resource_types.get_resource_types_response(
            page=page, per_page=per_page
        )
        groups_count = host_inventory.apis.groups.get_groups_response(group_type="all").total
        check_resource_types_list_response(response, groups_count, per_page=per_page, page=page)

    @pytest.mark.parametrize("page", [2, 21474837])
    @pytest.mark.parametrize("per_page", [None, 1, 10, 100])
    def test_resource_types_get_list_page_without_results(
        self, setup_empty_groups_primary, host_inventory, page, per_page
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3827

        metadata:
          requirements: inv-resource-types-list
          assignee: fstavela
          importance: low
          title: Get resource types list - page without results
        """
        response = host_inventory.apis.resource_types.get_resource_types_response(
            page=page, per_page=per_page
        )
        groups_count = host_inventory.apis.groups.get_groups_response(group_type="all").total
        # TODO: check that there is no data returned
        check_resource_types_list_response(response, groups_count, per_page=per_page, page=page)

    @pytest.mark.parametrize("page", [-1, 0, 21474838])
    def test_resource_types_get_list_page_out_of_bounds(
        self, setup_empty_groups_primary, host_inventory, page
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3827

        metadata:
          requirements: inv-resource-types-list
          assignee: fstavela
          importance: low
          negative: true
          title: Get resource types list - 'page' out of bounds
        """
        error_msgs: tuple[str, ...]
        if page < 1:
            error_msgs = (f"{page} is less than the minimum of 1",)
        else:
            error_msgs = (f"{page} is greater than the maximum of 21474837",)
        error_msgs += ("{'type': 'integer', 'minimum': 1, 'maximum': 21474837, 'default': 1}",)

        with raises_apierror(400, error_msgs):
            host_inventory.apis.resource_types.get_resource_types_response(page=page)

    @pytest.mark.parametrize(
        "page",
        (
            *EMPTY_BASICS,
            pytest.param([1], id="list of single int"),
            pytest.param([1, 2], id="list of multiple ints"),
            pytest.param(1.5, id="float"),
            pytest.param(generate_uuid(), id="string"),
            pytest.param(True, id="True"),
            pytest.param(False, id="False"),
            pytest.param("None", id="None"),
            pytest.param("", id="empty string"),
        ),
    )
    def test_resource_types_get_list_page_bad_type(
        self, setup_empty_groups_primary, host_inventory, page
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3827

        metadata:
          requirements: inv-resource-types-list
          assignee: fstavela
          importance: low
          negative: true
          title: Get resource types list - wrong value for 'page' param (wrong data type)
        """
        # TODO: Uncomment when https://issues.redhat.com/browse/RHINENG-11389 is fixed
        # with raises_apierror(400, "Wrong type, expected 'integer' for query parameter 'page'"):
        with raises_apierror(400, "Wrong type, expected 'integer' for"):
            host_inventory.apis.resource_types.get_resource_types_response(page=page)

    @pytest.mark.parametrize("per_page", [-1, 0, 101])
    def test_resource_types_get_list_per_page_out_of_bounds(
        self, setup_empty_groups_primary, host_inventory, per_page
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3827

        metadata:
          requirements: inv-resource-types-list
          assignee: fstavela
          importance: low
          negative: true
          title: Get resource types list - 'per_page' out of bounds
        """
        error_msgs: tuple[str, ...]
        if per_page < 1:
            error_msgs = (f"{per_page} is less than the minimum of 1",)
        else:
            error_msgs = (f"{per_page} is greater than the maximum of 100",)
        error_msgs += ("{'type': 'integer', 'minimum': 1, 'maximum': 100, 'default': 10}",)

        with raises_apierror(400, error_msgs):
            host_inventory.apis.resource_types.get_resource_types_response(per_page=per_page)

    @pytest.mark.parametrize(
        "per_page",
        (
            *EMPTY_BASICS,
            pytest.param([1], id="list of single int"),
            pytest.param([1, 2], id="list of multiple ints"),
            pytest.param(1.5, id="float"),
            pytest.param(generate_uuid(), id="string"),
            pytest.param(True, id="True"),
            pytest.param(False, id="False"),
            pytest.param("None", id="None"),
            pytest.param("", id="empty string"),
        ),
    )
    def test_resource_types_get_list_per_page_bad_type(
        self, setup_empty_groups_primary, host_inventory, per_page
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3827

        metadata:
          requirements: inv-resource-types-list
          assignee: fstavela
          importance: low
          negative: true
          title: Get resource types list - wrong value for 'per_page' param (wrong data type)
        """
        # TODO: Uncomment when https://issues.redhat.com/browse/RHINENG-11389 is fixed
        # with raises_apierror(
        #     400, "Wrong type, expected 'integer' for query parameter 'per_page'"
        # ):
        with raises_apierror(400, "Wrong type, expected 'integer' for"):
            host_inventory.apis.resource_types.get_resource_types_response(per_page=per_page)

    @pytest.mark.parametrize("page", [None, 1])
    @pytest.mark.parametrize("per_page", [None, 1, 10, 100])
    def test_resource_types_get_groups_with_empty_groups(
        self, setup_empty_groups_primary, host_inventory, page, per_page
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3827

        metadata:
          requirements: inv-resource-types-groups
          assignee: fstavela
          importance: high
          title: Get groups resources with existing empty groups
        """
        response = host_inventory.apis.resource_types.get_groups_response(
            page=page, per_page=per_page
        )
        groups_count = host_inventory.apis.groups.get_groups_response().total
        groups = check_resource_types_groups_response(
            response, groups_count, per_page=per_page, page=page
        )
        per_page = per_page or 10
        assert len(groups) == per_page

    @pytest.mark.parametrize("per_page", [None, 1, 10, 100])
    def test_resource_types_get_groups_page_without_results(
        self, setup_empty_groups_primary, host_inventory, per_page
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3827

        metadata:
          requirements: inv-resource-types-groups
          assignee: fstavela
          importance: medium
          title: Get groups resources - page without results
        """
        response = host_inventory.apis.resource_types.get_groups_response(
            page=21474837, per_page=per_page
        )
        groups_count = host_inventory.apis.groups.get_groups_response().total
        groups = check_resource_types_groups_response(
            response, groups_count, per_page=per_page, page=21474837
        )
        assert groups == []

    @pytest.mark.parametrize("page", [-1, 0, 21474838])
    def test_resource_types_get_groups_page_out_of_bounds(
        self, setup_empty_groups_primary, host_inventory, page
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3827

        metadata:
          requirements: inv-resource-types-groups
          assignee: fstavela
          importance: low
          negative: true
          title: Get groups resources - 'page' out of bounds
        """
        error_msgs: tuple[str, ...]
        if page < 1:
            error_msgs = (f"{page} is less than the minimum of 1",)
        else:
            error_msgs = (f"{page} is greater than the maximum of 21474837",)
        error_msgs += ("{'type': 'integer', 'minimum': 1, 'maximum': 21474837, 'default': 1}",)

        with raises_apierror(400, error_msgs):
            host_inventory.apis.resource_types.get_groups_response(page=page)

    @pytest.mark.parametrize(
        "page",
        (
            *EMPTY_BASICS,
            pytest.param([1], id="list of single int"),
            pytest.param([1, 2], id="list of multiple ints"),
            pytest.param(1.5, id="float"),
            pytest.param(generate_uuid(), id="string"),
            pytest.param(True, id="True"),
            pytest.param(False, id="False"),
            pytest.param("None", id="None"),
            pytest.param("", id="empty string"),
        ),
    )
    def test_resource_types_get_groups_page_bad_type(
        self, setup_empty_groups_primary, host_inventory, page
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3827

        metadata:
          requirements: inv-resource-types-groups
          assignee: fstavela
          importance: low
          negative: true
          title: Get groups resources - wrong value for 'page' param (wrong data type)
        """
        # TODO: Uncomment when https://issues.redhat.com/browse/RHINENG-11389 is fixed
        # with raises_apierror(400, "Wrong type, expected 'integer' for query parameter 'page'"):
        with raises_apierror(400, "Wrong type, expected 'integer' for"):
            host_inventory.apis.resource_types.get_groups_response(page=page)

    @pytest.mark.parametrize("per_page", [-1, 0, 101])
    def test_resource_types_get_groups_per_page_out_of_bounds(
        self, setup_empty_groups_primary, host_inventory, per_page
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3827

        metadata:
          requirements: inv-resource-types-groups
          assignee: fstavela
          importance: low
          negative: true
          title: Get groups resources - 'per_page' out of bounds
        """
        error_msgs: tuple[str, ...]
        if per_page < 1:
            error_msgs = (f"{per_page} is less than the minimum of 1",)
        else:
            error_msgs = (f"{per_page} is greater than the maximum of 100",)
        error_msgs += ("{'type': 'integer', 'minimum': 1, 'maximum': 100, 'default': 10}",)

        with raises_apierror(400, error_msgs):
            host_inventory.apis.resource_types.get_groups_response(per_page=per_page)

    @pytest.mark.parametrize(
        "per_page",
        (
            *EMPTY_BASICS,
            pytest.param([1], id="list of single int"),
            pytest.param([1, 2], id="list of multiple ints"),
            pytest.param(1.5, id="float"),
            pytest.param(generate_uuid(), id="string"),
            pytest.param(True, id="True"),
            pytest.param(False, id="False"),
            pytest.param("None", id="None"),
            pytest.param("", id="empty string"),
        ),
    )
    def test_resource_types_get_groups_per_page_bad_type(
        self, setup_empty_groups_primary, host_inventory, per_page
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3827

        metadata:
          requirements: inv-resource-types-groups
          assignee: fstavela
          importance: low
          negative: true
          title: Get groups resources - wrong value for 'per_page' param (wrong data type)
        """
        # TODO: Uncomment when https://issues.redhat.com/browse/RHINENG-11389 is fixed
        # with raises_apierror(
        #     400, "Wrong type, expected 'integer' for query parameter 'per_page'"
        # ):
        with raises_apierror(400, "Wrong type, expected 'integer' for"):
            host_inventory.apis.resource_types.get_groups_response(per_page=per_page)

    @pytest.mark.parametrize("per_page", [None, 3])
    def test_resource_types_get_groups_pagination(
        self, setup_empty_groups_primary, host_inventory, per_page
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3827

        metadata:
          requirements: inv-resource-types-groups
          assignee: fstavela
          importance: high
          title: Test pagination while getting groups resources
        """
        groups_count = host_inventory.apis.groups.get_groups_response().total
        found_groups_ids = set()
        for i in range(3):
            response = host_inventory.apis.resource_types.get_groups_response(
                per_page=per_page, page=i + 1
            )
            groups = check_resource_types_groups_response(
                response, groups_count, per_page=per_page, page=i + 1
            )
            assert len(groups) == per_page or 10
            found_groups_ids.update({group.id for group in groups})

        per_page = per_page or 10
        assert len(found_groups_ids) == 3 * per_page

    @pytest.mark.parametrize(
        "case_insensitive", [True, False], ids=["case insensitive", "case sensitive"]
    )
    def test_resource_types_get_groups_by_name_exact(
        self,
        setup_empty_groups_primary,
        host_inventory,
        case_insensitive,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4501

        metadata:
          requirements: inv-resource-types-groups
          assignee: fstavela
          importance: high
          title: Get groups resources by name - provide exact name
        """
        group = setup_empty_groups_primary[1]
        searched_name = group.name.upper() if case_insensitive else group.name

        response = host_inventory.apis.resource_types.get_groups_response(name=searched_name)
        response_groups = check_resource_types_groups_response(response, 1)
        assert len(response_groups) == 1
        assert response_groups[0] == group

    @pytest.mark.parametrize(
        "case_insensitive", [True, False], ids=["case insensitive", "case sensitive"]
    )
    def test_resource_types_get_groups_by_name_part(
        self, setup_empty_groups_primary, host_inventory, case_insensitive
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4501

        metadata:
          requirements: inv-resource-types-groups
          assignee: fstavela
          importance: high
          title: Get groups resources by name - provide only part of the name
        """
        group = setup_empty_groups_primary[1]
        searched_name = group.name[5:10].upper() if case_insensitive else group.name[5:10]

        response = host_inventory.apis.resource_types.get_groups_response(name=searched_name)
        response_groups = check_resource_types_groups_response(response, 1)
        assert len(response_groups) == 1
        assert response_groups[0] == group

    def test_resource_types_get_groups_different_account(
        self,
        setup_empty_groups_primary,
        host_inventory,
        host_inventory_secondary,
        hbi_default_org_id,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4501

        metadata:
          requirements: inv-resource-types-groups, inv-account-integrity
          assignee: fstavela
          importance: high
          negative: true
          title: Get groups resources - check I can't get group from different account
        """
        group = setup_empty_groups_primary[0]
        host_inventory_secondary.apis.groups.create_group(group.name)

        response = host_inventory.apis.resource_types.get_groups_response(name=group.name)
        response_groups = check_resource_types_groups_response(response, 1)
        assert len(response_groups) == 1
        assert response_groups[0].org_id == hbi_default_org_id
        assert response_groups[0] == group


@pytest.fixture(scope="module")
def setup_empty_groups(host_inventory) -> list[GroupOutWithHostCount]:
    return host_inventory.apis.groups.create_n_empty_groups(5)


@pytest.mark.rbac_dependent
@pytest.mark.parametrize(
    "host_inventory_app",
    [
        lf("rbac_non_org_admin_rbac_admin_setup_class"),
        lf("host_inventory"),
    ],
    ids=["rbac:*:*", "org_admin"],
    scope="class",
)
class TestRBACResourceTypesRBACPermissions:
    """
    metadata:
        requirements: inv-rbac
    """

    def test_rbac_resource_types_rbac_permissions_get_list(
        self, setup_empty_groups, host_inventory, host_inventory_app
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4501

        metadata:
          requirements: inv-resource-types-list
          assignee: fstavela
          importance: high
          title: Test that users with "rbac:*:*" and org admins can get a list of resource types
        """
        response = host_inventory_app.apis.resource_types.get_resource_types_response()
        groups_count = host_inventory.apis.groups.get_groups_response(group_type="all").total
        check_resource_types_list_response(response, groups_count)

    def test_rbac_resource_types_rbac_permissions_get_groups(
        self, setup_empty_groups, host_inventory, host_inventory_app
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4501

        metadata:
          requirements: inv-resource-types-groups
          assignee: fstavela
          importance: high
          title: Test that users with "rbac:*:*" and org admins can get a list of groups resources
        """
        response = host_inventory_app.apis.resource_types.get_groups_response()
        groups_count = host_inventory.apis.groups.get_groups_response().total
        groups = check_resource_types_groups_response(response, groups_count)
        paginated_count = min(groups_count, 10)
        assert len(groups) == paginated_count


@pytest.mark.rbac_dependent
class TestRBACResourceTypesNoRBACPermissions:
    """
    metadata:
        requirements: inv-rbac
    """

    def test_rbac_resource_types_no_rbac_permissions_get_list(
        self,
        setup_empty_groups,
        rbac_inventory_admin_user_setup_class,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4501

        metadata:
          requirements: inv-resource-types-list
          assignee: fstavela
          importance: high
          negative: true
          title: Test that users without "rbac:*:*" can't get a list of resource types
        """
        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.resource_types.get_resource_types_response()

    def test_rbac_resource_types_no_rbac_permissions_get_groups(
        self,
        setup_empty_groups,
        rbac_inventory_admin_user_setup_class,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4501

        metadata:
          requirements: inv-resource-types-groups
          assignee: fstavela
          importance: high
          negative: true
          title: Test that users without "rbac:*:*" can't get a list of groups resources
        """
        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.resource_types.get_groups_response()
