"""
metadata:
    requirements: inv-rbac
"""

import logging
from typing import Any

import pytest
from pytest_lazy_fixtures import lf

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.staleness_utils import get_staleness_defaults
from iqe_host_inventory.utils.staleness_utils import validate_staleness_response
from iqe_host_inventory_api_v7.exceptions import ForbiddenException

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.backend,
    pytest.mark.rbac_dependent,
    pytest.mark.usefixtures("hbi_staleness_cleanup_module"),
]


@pytest.fixture(
    params=[
        lf("rbac_staleness_read_hosts_read_user_setup_class"),
        lf("rbac_staleness_read_hosts_all_user_setup_class"),
        lf("rbac_staleness_all_hosts_read_user_setup_class"),
        lf("rbac_staleness_all_hosts_all_user_setup_class"),
    ],
    scope="class",
)
def read_permission_user_setup(request: pytest.FixtureRequest) -> Any:
    return request.param


@pytest.fixture(
    params=[
        lf("rbac_inventory_user_without_permissions_setup_class"),
        lf("rbac_inventory_hosts_read_user_setup_class"),
        lf("rbac_inventory_hosts_all_user_setup_class"),
        lf("rbac_staleness_read_user_setup_class"),
        lf("rbac_staleness_read_hosts_write_user_setup_class"),
        lf("rbac_staleness_write_hosts_read_user_setup_class"),
        lf("rbac_staleness_all_user_setup_class"),
    ],
    scope="class",
)
def no_read_permission_user_setup(request: pytest.FixtureRequest) -> None:
    return request.param


class TestRBACStalenessReadPermission:
    @pytest.mark.usefixtures("read_permission_user_setup")
    def test_rbac_staleness_read_permission_get_staleness_defaults(
        self,
        host_inventory_non_org_admin: ApplicationHostInventory,
        hbi_non_org_admin_user_org_id: str,
    ) -> None:
        """
        Test response when a user who has read permission tries to retrieve the
        default staleness settings via REST API

        1. Issue a GET request on /account/staleness/defaults as the user who has
           read permission
        2. Ensure GET request returns a 200 response with the staleness defaults
           associated with the user's org_id

        metadata:
            requirements: inv-staleness-get-defaults
            assignee: msager
            importance: high
            title: Inventory: Confirm users who have read permission have access to
                the default staleness settings
        """
        response = (
            host_inventory_non_org_admin.apis.account_staleness.get_default_staleness_response()
        )
        validate_staleness_response(response.to_dict(), get_staleness_defaults())

        assert response.org_id == hbi_non_org_admin_user_org_id

    @pytest.mark.usefixtures("read_permission_user_setup")
    def test_rbac_staleness_read_permission_get_staleness(
        self,
        host_inventory_non_org_admin: ApplicationHostInventory,
        hbi_non_org_admin_user_org_id: str,
        hbi_staleness_defaults: dict[str, int],
    ) -> None:
        """
        Test response when a user who has read permission tries to retrieve the
        current staleness settings via REST API

        1. Issue a GET request on /account/staleness as the user who has read permission
        2. Ensure GET request returns a 200 response with the staleness settings
           associated with the user's org_id

        metadata:
            requirements: inv-staleness-get
            assignee: msager
            importance: high
            title: Inventory: Confirm users who have read permission have access to
                the current staleness settings
        """
        response = host_inventory_non_org_admin.apis.account_staleness.get_staleness_response()
        validate_staleness_response(response.to_dict(), hbi_staleness_defaults)

        assert response.org_id == hbi_non_org_admin_user_org_id


class TestRBACHostsNoReadPermission:
    @pytest.mark.usefixtures("no_read_permission_user_setup")
    def test_rbac_staleness_no_read_permission_get_staleness_defaults(
        self,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """
        Test response when a user who doesn't have read permission tries to retrieve
        the default staleness settings via REST API

        1. Issue a GET request on /account/staleness/defaults as the user who
           doesn't have read permission
        2. Ensure GET request returns a 403 response

        metadata:
            requirements: inv-staleness-get-defaults
            assignee: msager
            importance: high
            title: Inventory: Confirm users without read permission can't access the
                default staleness settings
        """
        with pytest.raises(ForbiddenException) as err:
            host_inventory_non_org_admin.apis.account_staleness.get_default_staleness()

        assert err.value.status == 403

    @pytest.mark.usefixtures("no_read_permission_user_setup")
    def test_rbac_staleness_no_read_permission_get_staleness(
        self,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """
        Test response when a user who doesn't have read permission tries to retrieve
        the current staleness settings via REST API

        1. Issue a GET request on /account/staleness as the user who doesn't have
           read permission
        2. Ensure GET request returns a 403 response

        metadata:
            requirements: inv-staleness-get
            assignee: msager
            importance: high
            title: Inventory: Confirm users without read permission can't access the
                current staleness settings
        """
        with pytest.raises(ForbiddenException) as err:
            host_inventory_non_org_admin.apis.account_staleness.get_staleness()

        assert err.value.status == 403
