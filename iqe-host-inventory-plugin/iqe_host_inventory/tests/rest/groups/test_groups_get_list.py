import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.groups_api import GroupData
from iqe_host_inventory.tests.rest.groups.test_groups_get_by_id import in_order
from iqe_host_inventory.tests.rest.validation.test_system_profile import EMPTY_BASICS
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_string_of_length
from iqe_host_inventory.utils.datagen_utils import generate_uuid

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


def test_groups_get_list_no_groups(host_inventory):
    """WARNING: Don't run this test in shared accounts. It deletes all groups on account.

    https://issues.redhat.com/browse/ESSNTL-3829

    metadata:
      requirements: inv-groups-get-list
      assignee: fstavela
      importance: high
      title: Get groups list when there are no groups
    """
    host_inventory.apis.groups.delete_all_groups()

    response = host_inventory.apis.groups.get_groups_response()
    assert response.total == 0
    assert response.count == 0
    assert response.page == 1
    assert response.results == []


@pytest.mark.ephemeral
@pytest.mark.parametrize("n_hosts", [0, 1, 3])
@pytest.mark.parametrize("n_groups", [1, 3])
def test_groups_get_list(
    host_inventory: ApplicationHostInventory,
    n_hosts: int,
    n_groups: int,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3829

    metadata:
      requirements: inv-groups-get-list
      assignee: fstavela
      importance: high
      title: Get groups list
    """
    hosts = host_inventory.kafka.create_random_hosts(9)

    groups_data = [
        GroupData(hosts=hosts[(i * n_hosts) : (i * n_hosts + n_hosts)]) for i in range(n_groups)
    ]
    host_inventory.apis.groups.create_groups(groups_data)

    response = host_inventory.apis.groups.get_groups_response()
    assert response.total >= n_groups
    assert response.count >= n_groups
    assert response.page == 1
    assert len(response.results) >= n_groups


@pytest.mark.ephemeral
@pytest.mark.parametrize("n_hosts", [0, 1, 3])
@pytest.mark.parametrize("n_groups", [1, 3])
def test_groups_get_list_only_my_groups(
    host_inventory: ApplicationHostInventory,
    n_hosts: int,
    n_groups: int,
):
    """WARNING: Don't run this test in shared accounts. It deletes all groups on account.

    https://issues.redhat.com/browse/ESSNTL-3829

    metadata:
      requirements: inv-groups-get-list
      assignee: fstavela
      importance: high
      title: Get groups list with limited amount of groups
    """
    host_inventory.apis.groups.delete_all_groups()

    hosts = host_inventory.kafka.create_random_hosts(9)

    groups_data = [
        GroupData(hosts=hosts[(i * n_hosts) : (i * n_hosts + n_hosts)]) for i in range(n_groups)
    ]
    groups = host_inventory.apis.groups.create_groups(groups_data)
    orig_groups_dict = {group.id: group for group in groups}

    response = host_inventory.apis.groups.get_groups_response()
    assert response.total == n_groups
    assert response.count == n_groups
    assert response.page == 1
    assert len(response.results) == n_groups
    assert {group.id for group in response.results} == set(orig_groups_dict.keys())
    for group in response.results:
        assert group == orig_groups_dict[group.id]


@pytest.mark.ephemeral
@pytest.mark.parametrize("with_hosts", [True, False], ids=["with hosts", "without hosts"])
def test_groups_get_list_pagination(host_inventory: ApplicationHostInventory, with_hosts: bool):
    """
    https://issues.redhat.com/browse/ESSNTL-3829

    metadata:
      requirements: inv-groups-get-list
      assignee: fstavela
      importance: high
      title: Test pagination while getting groups list
    """
    hosts = host_inventory.kafka.create_random_hosts(9)

    groups_data = [GroupData(hosts=[hosts[i]] if with_hosts else []) for i in range(9)]
    host_inventory.apis.groups.create_groups(groups_data)

    found_groups_ids = set()
    for i in range(3):
        response = host_inventory.apis.groups.get_groups_response(per_page=3, page=i + 1)
        assert response.page == i + 1
        assert response.per_page == 3
        assert response.total >= 9
        assert response.count == 3
        assert len(response.results) == 3
        found_groups_ids.update({group.id for group in response.results})

    assert len(found_groups_ids) == 9


@pytest.mark.ephemeral
@pytest.mark.parametrize("with_hosts", [True, False], ids=["with hosts", "without hosts"])
def test_groups_get_list_pagination_only_my_groups(
    host_inventory: ApplicationHostInventory, with_hosts: bool
):
    """WARNING: Don't run this test in shared accounts. It deletes all groups on account.

    https://issues.redhat.com/browse/ESSNTL-3829

    metadata:
      requirements: inv-groups-get-list
      assignee: fstavela
      importance: high
      title: Test pagination while getting groups list with limited amount of groups
    """
    host_inventory.apis.groups.delete_all_groups()

    hosts = host_inventory.kafka.create_random_hosts(10)

    groups_data = [GroupData(hosts=[hosts[i]] if with_hosts else []) for i in range(10)]

    groups = host_inventory.apis.groups.create_groups(groups_data)
    all_groups_ids = {group.id for group in groups}

    found_groups_ids = set()
    for i in range(4):
        response = host_inventory.apis.groups.get_groups_response(per_page=3, page=i + 1)
        assert response.page == i + 1
        assert response.per_page == 3
        assert response.total == 10
        if i == 3:
            # last page
            assert response.count == 1
            assert len(response.results) == 1
        else:
            assert response.count == 3
            assert len(response.results) == 3
        found_groups_ids.update({group.id for group in response.results})

    assert found_groups_ids == all_groups_ids


@pytest.mark.ephemeral
@pytest.mark.parametrize("order_by", ["name", "host_count", "updated", "created", "type"])
@pytest.mark.parametrize("order_how", ["ASC", "DESC"])
def test_groups_get_list_ordering(
    host_inventory,
    setup_groups_for_ordering,
    order_by,
    order_how,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3829

    metadata:
      requirements: inv-groups-get-list
      assignee: fstavela
      importance: high
      title: Get groups list - test ordering parameters
    """
    response = host_inventory.apis.groups.get_groups_response(
        order_by=order_by, order_how=order_how
    )
    assert response.page == 1
    assert response.total >= 10
    assert response.count >= 10
    assert len(response.results) >= 10
    assert in_order(response.results, None, ascending=(order_how == "ASC"), sort_field=order_by)


@pytest.mark.ephemeral
@pytest.mark.parametrize("order_by", ["name", "host_count", "updated", "created", "type"])
@pytest.mark.parametrize("order_how", ["ASC", "DESC"])
def test_groups_get_list_ordering_and_pagination(
    host_inventory,
    setup_groups_for_ordering,
    order_by,
    order_how,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3829

    metadata:
      requirements: inv-groups-get-list
      assignee: fstavela
      importance: high
      title: Get groups list - paginate through ordered results
    """
    found_groups = []
    for i in range(3):
        response = host_inventory.apis.groups.get_groups_response(
            per_page=3, page=i + 1, order_how=order_how, order_by=order_by
        )
        assert response.page == i + 1
        assert response.per_page == 3
        assert response.total >= 10
        assert response.count == 3
        assert len(response.results) == 3
        found_groups += response.results

    assert len({group.id for group in found_groups}) == 9
    assert in_order(found_groups, None, ascending=(order_how == "ASC"), sort_field=order_by)


@pytest.mark.ephemeral
@pytest.mark.parametrize("order_by", ["name", "host_count", "updated", "created", "type"])
def test_groups_get_list_order_how_default(
    host_inventory,
    setup_groups_for_ordering,
    order_by,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3829

    metadata:
      requirements: inv-groups-get-list
      assignee: fstavela
      importance: high
      title: Get groups list - default values for order_how parameter
    """
    # Default order_how is ASC for 'name' and 'type',
    # DESC for 'host_count', 'updated', and 'created'
    ascending = order_by in ["name", "type"]

    response = host_inventory.apis.groups.get_groups_response(order_by=order_by)
    assert response.page == 1
    assert response.total >= 10
    assert response.count >= 10
    assert len(response.results) >= 10
    assert in_order(response.results, None, ascending=ascending, sort_field=order_by)


@pytest.mark.ephemeral
def test_groups_get_list_order_by_default(host_inventory, setup_groups_for_ordering):
    """
    https://issues.redhat.com/browse/ESSNTL-3829

    metadata:
      requirements: inv-groups-get-list
      assignee: fstavela
      importance: high
      title: Get groups list - default value for order_by parameter
    """
    response = host_inventory.apis.groups.get_groups_response()
    assert response.page == 1
    assert response.total >= 10
    assert response.count >= 10
    assert len(response.results) >= 10
    assert in_order(response.results, None, ascending=True, sort_field="name")


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "case_insensitive", [True, False], ids=["case insensitive", "case sensitive"]
)
@pytest.mark.parametrize("with_hosts", [True, False], ids=["with hosts", "without hosts"])
def test_groups_get_list_by_name_exact(
    host_inventory: ApplicationHostInventory,
    case_insensitive: bool,
    with_hosts: bool,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3829

    metadata:
      requirements: inv-groups-get-list
      assignee: fstavela
      importance: high
      title: Get groups list by name - provide exact name
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    groups_data = [
        GroupData(
            name=generate_display_name("filtering"), hosts=([hosts[i]] if with_hosts else [])
        )
        for i in range(3)
    ]
    groups = host_inventory.apis.groups.create_groups(groups_data)

    searched_name = groups[1].name.upper() if case_insensitive else groups[1].name
    response = host_inventory.apis.groups.get_groups_response(name=searched_name)
    assert response.count == 1
    assert response.total == 1
    assert response.page == 1
    assert len(response.results) == 1
    assert response.results[0] == groups[1]


@pytest.mark.parametrize(
    "case_insensitive", [True, False], ids=["case insensitive", "case sensitive"]
)
def test_groups_get_list_by_name_part(host_inventory, case_insensitive):
    """
    https://issues.redhat.com/browse/ESSNTL-3829

    metadata:
      requirements: inv-groups-get-list
      assignee: fstavela
      importance: high
      title: Get groups list by name - provide only part of the name
    """
    groups_data = [GroupData(name=generate_display_name("filtering"), hosts=[]) for _ in range(3)]
    groups = host_inventory.apis.groups.create_groups(groups_data)
    groups += host_inventory.apis.groups.create_n_empty_groups(3)
    wanted_groups_dict = {group.id: group for group in groups[:3]}

    searched_name = "ILTERIN" if case_insensitive else "ilterin"
    response = host_inventory.apis.groups.get_groups_response(name=searched_name)
    assert response.count == 3
    assert response.total == 3
    assert response.page == 1
    assert len(response.results) == 3
    assert {group.id for group in response.results} == set(wanted_groups_dict.keys())
    for group in response.results:
        assert group == wanted_groups_dict[group.id]


@pytest.mark.ephemeral
@pytest.mark.parametrize("order_by", ["name", "host_count", "updated", "created", "type"])
@pytest.mark.parametrize("order_how", ["ASC", "DESC"])
def test_groups_get_list_by_name_ordering_and_pagination(
    host_inventory,
    setup_groups_for_ordering,
    order_by,
    order_how,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3829

    metadata:
      requirements: inv-groups-get-list
      assignee: fstavela
      importance: high
      title: Get groups list by name - paginate through ordered results
    """
    groups = setup_groups_for_ordering
    wanted_groups_ids = {group.id for group in groups}
    host_inventory.apis.groups.create_n_empty_groups(3)

    found_groups = []
    for i in range(4):
        response = host_inventory.apis.groups.get_groups_response(
            name="hbi-ordering-test",
            per_page=3,
            page=i + 1,
            order_how=order_how,
            order_by=order_by,
        )
        assert response.page == i + 1
        assert response.per_page == 3
        assert response.total == 10
        if i == 3:
            # last page
            assert response.count == 1
            assert len(response.results) == 1
        else:
            assert response.count == 3
            assert len(response.results) == 3
        found_groups += response.results

    assert {group.id for group in found_groups} == wanted_groups_ids
    assert in_order(found_groups, None, ascending=(order_how == "ASC"), sort_field=order_by)


@pytest.mark.ephemeral
@pytest.mark.parametrize("with_hosts", [True, False], ids=["with hosts", "without hosts"])
def test_groups_get_list_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    hbi_default_org_id: str,
    with_hosts: bool,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3829

    metadata:
      requirements: inv-groups-get-list, inv-account-integrity
      assignee: fstavela
      importance: critical
      negative: true
      title: Get groups list - check I can't get group from different account
    """
    hosts_primary = host_inventory.kafka.create_random_hosts(3)
    hosts_secondary = host_inventory_secondary.kafka.create_random_hosts(3)

    groups_data_primary = [
        GroupData(hosts=[hosts_primary[i]] if with_hosts else []) for i in range(3)
    ]
    groups_data_secondary = [
        GroupData(hosts=[hosts_secondary[i]] if with_hosts else []) for i in range(3)
    ]
    host_inventory.apis.groups.create_groups(groups_data_primary)
    host_inventory_secondary.apis.groups.create_groups(groups_data_secondary)

    response = host_inventory.apis.groups.get_groups_response()
    assert response.count >= 3
    assert response.total >= 3
    assert response.page == 1
    assert len(response.results) >= 3
    for group in response.results:
        assert group.org_id == hbi_default_org_id


@pytest.mark.ephemeral
@pytest.mark.parametrize("with_hosts", [True, False], ids=["with hosts", "without hosts"])
def test_groups_get_list_by_name_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    with_hosts: bool,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3829

    metadata:
      requirements: inv-groups-get-list, inv-account-integrity
      assignee: fstavela
      importance: critical
      negative: true
      title: Get groups list by name - try to get group from different account
    """
    hosts_primary = host_inventory.kafka.create_random_hosts(3)
    hosts_secondary = host_inventory_secondary.kafka.create_random_hosts(3)

    groups_data_primary = [
        GroupData(hosts=[hosts_primary[i]] if with_hosts else []) for i in range(3)
    ]
    groups_data_secondary = [
        GroupData(hosts=[hosts_secondary[i]] if with_hosts else []) for i in range(3)
    ]
    host_inventory.apis.groups.create_groups(groups_data_primary)
    groups_secondary = host_inventory_secondary.apis.groups.create_groups(groups_data_secondary)

    response = host_inventory.apis.groups.get_groups_response(name=groups_secondary[1].name)
    assert response.count == 0
    assert response.total == 0
    assert response.page == 1
    assert response.results == []


@pytest.mark.ephemeral
@pytest.mark.parametrize("with_hosts", [True, False], ids=["with hosts", "without hosts"])
def test_groups_get_list_by_name_my_and_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    with_hosts: bool,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3829

    metadata:
      requirements: inv-groups-get-list, inv-account-integrity
      assignee: fstavela
      importance: critical
      negative: true
      title: Get groups list by name - try to get group from my and different account
    """
    hosts_primary = host_inventory.kafka.create_random_hosts(3)
    hosts_secondary = host_inventory_secondary.kafka.create_random_hosts(3)

    groups_data_primary = [
        GroupData(name=generate_display_name(), hosts=[hosts_primary[i]] if with_hosts else [])
        for i in range(3)
    ]
    groups_data_secondary = [
        GroupData(
            name=groups_data_primary[i].name, hosts=([hosts_secondary[i]] if with_hosts else [])
        )
        for i in range(3)
    ]
    groups_primary = host_inventory.apis.groups.create_groups(groups_data_primary)
    groups_secondary = host_inventory_secondary.apis.groups.create_groups(groups_data_secondary)

    response = host_inventory.apis.groups.get_groups_response(name=groups_secondary[1].name)
    assert response.count == 1
    assert response.total == 1
    assert response.page == 1
    assert len(response.results) == 1
    assert response.results[0] == groups_primary[1]


class TestGetGroupListEmptyGroups:
    """
    This class is used for test scenarios on GET /groups/<groups_ids> endpoint
    that use just empty groups and don't require any special groups or hosts.
    """

    def test_groups_get_list_per_page_min(self, setup_empty_groups_primary, host_inventory):
        """
        https://issues.redhat.com/browse/ESSNTL-3829

        metadata:
          requirements: inv-groups-get-list
          assignee: fstavela
          importance: medium
          title: Get groups list - minimum for per_page param (1)
        """
        response = host_inventory.apis.groups.get_groups_response(per_page=1)
        assert response.page == 1
        assert response.per_page == 1
        assert response.total >= len(setup_empty_groups_primary)
        assert response.count == 1
        assert len(response.results) == 1

    def test_groups_get_list_per_page_max(self, setup_empty_groups_primary, host_inventory):
        """
        https://issues.redhat.com/browse/ESSNTL-3829

        metadata:
          requirements: inv-groups-get-list
          assignee: fstavela
          importance: medium
          title: Get groups list - maximum for per_page param (100)
        """
        response = host_inventory.apis.groups.get_groups_response(per_page=100)
        assert response.page == 1
        assert response.per_page == 100
        assert response.total >= len(setup_empty_groups_primary)
        assert response.count == 100
        assert len(response.results) == 100

    @pytest.mark.parametrize("per_page", [0, -1, 101])
    def test_groups_get_list_per_page_out_of_bounds(
        self, setup_empty_groups_primary, host_inventory, per_page
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3829

        metadata:
          requirements: inv-groups-get-list
          assignee: fstavela
          importance: low
          negative: true
          title: Get groups list - wrong value for per_page param (out of bounds)
        """
        error_msgs: tuple[str, ...]
        if per_page < 1:
            error_msgs = (f"{per_page} is less than the minimum of 1",)
        else:
            error_msgs = (f"{per_page} is greater than the maximum of 100",)
        error_msgs += ("{'type': 'integer', 'minimum': 1, 'maximum': 100, 'default': 50}",)

        with raises_apierror(400, error_msgs):
            host_inventory.apis.groups.get_groups_response(per_page=per_page)

    @pytest.mark.parametrize(
        "per_page",
        (
            *EMPTY_BASICS,
            pytest.param([1], id="list of single int"),
            pytest.param([1, 2], id="list of multiple ints"),
            pytest.param(1.5, id="float"),
            pytest.param(generate_uuid(), id="str"),
            pytest.param(True, id="True"),
            pytest.param(False, id="False"),
            pytest.param("None", id="None"),
            pytest.param("", id="empty string"),
        ),
    )
    def test_groups_get_list_per_page_bad_type(
        self, setup_empty_groups_primary, host_inventory, per_page
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3829

        metadata:
          requirements: inv-groups-get-list
          assignee: fstavela
          importance: low
          negative: true
          title: Get groups list - wrong value for per_page param (wrong data type)
        """
        # TODO: Uncomment when https://issues.redhat.com/browse/RHINENG-11389 is fixed
        # with raises_apierror(
        #     400, "Wrong type, expected 'integer' for query parameter 'per_page'"
        # ):
        with raises_apierror(400, "Wrong type, expected 'integer' for"):
            host_inventory.apis.groups.get_groups_response(per_page=per_page)

    def test_groups_get_list_page_min(self, setup_empty_groups_primary, host_inventory):
        """
        https://issues.redhat.com/browse/ESSNTL-3829

        metadata:
          requirements: inv-groups-get-list
          assignee: fstavela
          importance: high
          title: Get groups list - minimum for page param (1)
        """
        response = host_inventory.apis.groups.get_groups_response(page=1)
        assert response.page == 1
        assert response.total >= len(setup_empty_groups_primary)
        assert response.count == 50
        assert len(response.results) == 50

    def test_groups_get_list_page_max(self, setup_empty_groups_primary, host_inventory):
        """
        https://issues.redhat.com/browse/ESSNTL-3829

        metadata:
          requirements: inv-groups-get-list
          assignee: fstavela
          importance: medium
          title: Get groups list - maximum for page param (21474837)
        """
        response = host_inventory.apis.groups.get_groups_response(page=21474837)
        assert response.page == 21474837
        assert response.total >= len(setup_empty_groups_primary)
        assert response.count == 0
        assert len(response.results) == 0

    @pytest.mark.parametrize("page", [0, -1, 21474838])
    def test_groups_get_list_page_out_of_bounds(
        self, setup_empty_groups_primary, host_inventory, page
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3829

        metadata:
          requirements: inv-groups-get-list
          assignee: fstavela
          importance: low
          negative: true
          title: Get groups list - wrong value for page param (out of bounds)
        """
        error_msgs: tuple[str, ...]
        if page < 1:
            error_msgs = (f"{page} is less than the minimum of 1",)
        else:
            error_msgs = (f"{page} is greater than the maximum of 21474837",)
        error_msgs += ("{'type': 'integer', 'minimum': 1, 'maximum': 21474837, 'default': 1}",)

        with raises_apierror(400, error_msgs):
            host_inventory.apis.groups.get_groups_response(page=page)

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
    def test_groups_get_list_page_bad_type(self, setup_empty_groups_primary, host_inventory, page):
        """
        https://issues.redhat.com/browse/ESSNTL-3829

        metadata:
          requirements: inv-groups-get-list
          assignee: fstavela
          importance: low
          negative: true
          title: Get groups list - wrong value for page param (wrong data type)
        """
        # TODO: Uncomment when https://issues.redhat.com/browse/RHINENG-11389 is fixed
        # with raises_apierror(400, "Wrong type, expected 'integer' for query parameter 'page'"):
        with raises_apierror(400, "Wrong type, expected 'integer' for"):
            host_inventory.apis.groups.get_groups_response(page=page)

    def test_groups_get_list_pagination_default(self, setup_empty_groups_primary, host_inventory):
        """
        https://issues.redhat.com/browse/ESSNTL-3829

        metadata:
          requirements: inv-groups-get-list
          assignee: fstavela
          importance: high
          title: Get groups list - default values for pagination parameters
        """
        response = host_inventory.apis.groups.get_groups_response()
        assert response.page == 1
        assert response.per_page == 50
        assert response.total >= len(setup_empty_groups_primary)
        assert response.count == 50
        assert len(response.results) == 50

    @pytest.mark.parametrize(
        "order_by",
        (
            *EMPTY_BASICS,
            pytest.param(1, id="int"),
            pytest.param(["name", "host_count"], id="list of values"),
            pytest.param(1.5, id="float"),
            pytest.param(generate_uuid(), id="random string"),
            pytest.param(True, id="True"),
            pytest.param(False, id="False"),
            pytest.param("None", id="None"),
            pytest.param("", id="empty string"),
        ),
    )
    def test_groups_get_list_order_by_bad_type(
        self, setup_empty_groups_primary, host_inventory, order_by
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3829

        metadata:
          requirements: inv-groups-get-list
          assignee: fstavela
          importance: low
          negative: true
          title: Get groups list - wrong value for order_by param (wrong data type)
        """
        with raises_apierror(
            400,
            (
                f"{order_by}",
                "is not one of ['name', 'host_count', 'updated']",
                "{'type': 'string', 'enum': ['name', 'host_count', 'updated']}",
            ),
        ):
            host_inventory.apis.groups.get_groups_response(order_by=order_by)

    @pytest.mark.parametrize(
        "order_how",
        (
            *EMPTY_BASICS,
            pytest.param(1, id="int"),
            pytest.param(1.5, id="float"),
            pytest.param(generate_uuid(), id="random string"),
            pytest.param(True, id="True"),
            pytest.param(False, id="False"),
            pytest.param("None", id="None"),
            pytest.param("", id="empty string"),
        ),
    )
    @pytest.mark.parametrize("order_by", ["name", "host_count"])
    def test_groups_get_list_order_how_bad_type(
        self, setup_empty_groups_primary, host_inventory, order_how, order_by
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3829

        metadata:
          requirements: inv-groups-get-list
          assignee: fstavela
          importance: low
          negative: true
          title: Get groups list - wrong value for order_how param (wrong data type)
        """
        with raises_apierror(
            400, f"'{order_how}' does not match '^([Aa][Ss][Cc])|([Dd][Ee][Ss][Cc])$'"
        ):
            host_inventory.apis.groups.get_groups_response(order_how=order_how, order_by=order_by)

    def test_groups_get_list_by_name_min(self, setup_empty_groups_primary, host_inventory):
        """
        https://issues.redhat.com/browse/ESSNTL-3829

        metadata:
          requirements: inv-groups-get-list
          assignee: fstavela
          importance: medium
          title: Get groups list by name - minimum length for name param (1)
        """
        searched_name = setup_empty_groups_primary[0].name[0]
        response = host_inventory.apis.groups.get_groups_response(name=searched_name)
        assert response.page == 1
        assert response.total >= 1
        assert response.count >= 1
        assert len(response.results) >= 1

    def test_groups_get_list_by_name_max(self, setup_empty_groups_primary, host_inventory):
        """
        https://issues.redhat.com/browse/ESSNTL-3829

        metadata:
          requirements: inv-groups-get-list
          assignee: fstavela
          importance: medium
          title: Get groups list by name - maximum length for name param (256)
        """
        response = host_inventory.apis.groups.get_groups_response(
            name=generate_string_of_length(256, use_punctuation=False)
        )
        assert response.page == 1
        assert response.total == 0
        assert response.count == 0
        assert response.results == []

    def test_groups_get_list_by_name_empty_string(
        self, setup_empty_groups_primary, host_inventory
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3829

        metadata:
          requirements: inv-groups-get-list
          assignee: fstavela
          importance: low
          negative: true
          title: Get groups list by name - empty string in name param
        """
        response = host_inventory.apis.groups.get_groups_response(name="")
        assert response.total >= len(setup_empty_groups_primary)

    def test_groups_get_list_by_name_not_existing(
        self, setup_empty_groups_primary, host_inventory
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3829

        metadata:
          requirements: inv-groups-get-list
          assignee: fstavela
          importance: medium
          title: Get groups list by name - not existing group name
        """
        response = host_inventory.apis.groups.get_groups_response(name=generate_display_name())
        assert response.page == 1
        assert response.total == 0
        assert response.count == 0
        assert response.results == []
