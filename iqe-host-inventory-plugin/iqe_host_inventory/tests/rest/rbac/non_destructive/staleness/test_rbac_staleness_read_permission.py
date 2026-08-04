# mypy: disallow-untyped-defs

"""
metadata:
    requirements: inv-rbac
"""

import logging

import pytest
from pytest_lazy_fixtures import lf

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.staleness_utils import get_staleness_defaults
from iqe_host_inventory.utils.staleness_utils import validate_staleness_response

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.backend,
    pytest.mark.rbac_dependent,
    pytest.mark.usefixtures("hbi_staleness_cleanup_module"),
]


@pytest.fixture(
    params=[
        lf("host_inventory_rbac_stl_vwr_hst_vwr"),
        lf("host_inventory_rbac_stl_vwr_hst_adm"),
        lf("host_inventory_rbac_stl_adm_hst_vwr"),
        lf("host_inventory_rbac_stl_adm_hst_adm"),
    ],
    scope="class",
)
def host_inventory_staleness_read_permissions(
    request: pytest.FixtureRequest,
) -> ApplicationHostInventory:
    return request.param


@pytest.fixture(
    params=[
        lf("host_inventory_rbac_no_perms"),
        lf("host_inventory_rbac_hosts_viewer"),
        lf("host_inventory_rbac_hosts_admin"),
        lf("host_inventory_rbac_staleness_viewer"),
        lf("host_inventory_rbac_staleness_admin"),
        lf("host_inventory_rbac_staleness_all"),
        lf("host_inventory_rbac_stl_wrt_hst_wrt"),
    ],
    scope="class",
)
def host_inventory_staleness_no_read_permissions(
    request: pytest.FixtureRequest,
) -> ApplicationHostInventory:
    return request.param


class TestRBACStalenessReadPermission:
    def test_rbac_staleness_read_permission_get_staleness_defaults(
        self,
        host_inventory_staleness_read_permissions: ApplicationHostInventory,
        hbi_default_org_id: str,
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
        staleness_api = host_inventory_staleness_read_permissions.apis.account_staleness
        response = staleness_api.get_default_staleness_response()
        validate_staleness_response(response.json(), get_staleness_defaults())

        assert response.json()["org_id"] == hbi_default_org_id

    def test_rbac_staleness_read_permission_get_staleness(
        self,
        host_inventory_staleness_read_permissions: ApplicationHostInventory,
        hbi_default_org_id: str,
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
        staleness_api = host_inventory_staleness_read_permissions.apis.account_staleness
        response = staleness_api.get_staleness_response()
        validate_staleness_response(response.json(), hbi_staleness_defaults)

        assert response.json()["org_id"] == hbi_default_org_id


class TestRBACStalenessNoReadPermission:
    def test_rbac_staleness_no_read_permission_get_staleness_defaults(
        self,
        host_inventory_staleness_no_read_permissions: ApplicationHostInventory,
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
        staleness_api = host_inventory_staleness_no_read_permissions.apis.account_staleness
        resp = staleness_api.get_default_staleness_response()

        assert resp.status_code == 403

    def test_rbac_staleness_no_read_permission_get_staleness(
        self,
        host_inventory_staleness_no_read_permissions: ApplicationHostInventory,
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
        staleness_api = host_inventory_staleness_no_read_permissions.apis.account_staleness
        resp = staleness_api.get_staleness_response()

        assert resp.status_code == 403
