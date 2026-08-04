# mypy: disallow-untyped-defs

"""
metadata:
    requirements: inv-rbac
"""

import logging

import pytest
from pytest_lazy_fixtures import lf

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.staleness_utils import get_staleness_fields
from iqe_host_inventory.utils.staleness_utils import validate_staleness_response

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.backend,
    pytest.mark.rbac_dependent,
    pytest.mark.usefixtures("hbi_staleness_cleanup"),
]


@pytest.fixture(
    params=[
        lf("host_inventory_rbac_stl_wrt_hst_wrt"),
        lf("host_inventory_rbac_stl_adm_hst_adm"),
    ],
    scope="class",
)
def host_inventory_staleness_write_permissions(
    request: pytest.FixtureRequest,
) -> ApplicationHostInventory:
    return request.param


@pytest.fixture(
    params=[
        lf("host_inventory_rbac_no_perms"),
        lf("host_inventory_rbac_hosts_write"),
        lf("host_inventory_rbac_hosts_admin"),
        lf("host_inventory_rbac_staleness_write"),
        lf("host_inventory_rbac_staleness_admin"),
        lf("host_inventory_rbac_staleness_all"),
        lf("host_inventory_rbac_stl_adm_hst_vwr"),
        lf("host_inventory_rbac_stl_vwr_hst_adm"),
    ],
    scope="class",
)
def host_inventory_staleness_no_write_permissions(
    request: pytest.FixtureRequest,
) -> ApplicationHostInventory:
    return request.param


@pytest.mark.usefixtures("hbi_staleness_defaults")
class TestRBACStalenessWritePermission:
    def test_rbac_staleness_write_permission_create_staleness(
        self,
        host_inventory_staleness_write_permissions: ApplicationHostInventory,
        hbi_default_org_id: str,
        hbi_staleness_defaults: dict[str, int],
    ) -> None:
        """
        Test response when a user who has write permission tries to create staleness
        settings via REST API

        1. Issue a POST request on /account/staleness as the user who has write
           permission
        2. Ensure POST request returns a 200 response with the staleness record
           created associated with the user's org_id

        metadata:
            requirements: inv-staleness-post
            assignee: msager
            importance: high
            title: Inventory: Confirm users who have write permission can create
                staleness settings
        """
        settings = dict(zip(get_staleness_fields(), [1, 2, 3], strict=False))

        response = (
            host_inventory_staleness_write_permissions.apis.account_staleness.create_staleness(
                **settings
            )
        )
        validate_staleness_response(response.json(), hbi_staleness_defaults, settings)

        assert response.json()["org_id"] == hbi_default_org_id

    def test_rbac_staleness_write_permission_update_staleness(
        self,
        host_inventory: ApplicationHostInventory,
        host_inventory_staleness_write_permissions: ApplicationHostInventory,
        hbi_default_org_id: str,
    ) -> None:
        """
        Test response when a user who has "write" permission tries to update staleness
        settings via REST API

        1. Issue a POST request on /account/staleness to create settings
        2. Issue a PATCH request on /account/staleness as the user who has write
           permission
        3. Ensure PATCH request returns a 200 response with the staleness record updated
           associated with the user's org_id

        metadata:
            requirements: inv-staleness-patch
            assignee: msager
            importance: high
            title: Inventory: Confirm users who have write permission can update
                staleness settings
        """
        settings = dict(zip(get_staleness_fields(), [1, 2, 3], strict=False))
        original = host_inventory.apis.account_staleness.create_staleness(**settings).json()

        settings = dict(zip(get_staleness_fields(), [4, 5, 6], strict=False))
        response = (
            host_inventory_staleness_write_permissions.apis.account_staleness.update_staleness(
                **settings
            )
        )
        validate_staleness_response(response.json(), original, settings)

        assert response.json()["org_id"] == hbi_default_org_id

    @pytest.mark.usefixtures("hbi_staleness_defaults")
    def test_rbac_staleness_write_permission_delete_staleness(
        self,
        host_inventory: ApplicationHostInventory,
        host_inventory_staleness_write_permissions: ApplicationHostInventory,
    ) -> None:
        """
        Test response when a user who has write permission tries to delete staleness
        settings via REST API

        1. Issue a POST request on /account/staleness to create settings
        2. Issue a DELETE request on /account/staleness as the user who has write
           permission
        3. Ensure DELETE request returns a 200 response with the staleness record deleted
           associated with the user's org_id

        metadata:
            requirements: inv-staleness-delete
            assignee: msager
            importance: high
            title: Inventory: Confirm users who have write permission can delete
                staleness settings
        """
        settings = dict(zip(get_staleness_fields(), [1, 2, 3], strict=False))
        host_inventory.apis.account_staleness.create_staleness(**settings).json()

        response = host_inventory.apis.account_staleness.get_staleness_response()
        assert response.json()["id"] != "system_default"

        host_inventory_staleness_write_permissions.apis.account_staleness.delete_staleness()
        response = host_inventory.apis.account_staleness.get_staleness_response()
        assert response.json()["id"] == "system_default"


class TestRBACStalenessNoWritePermission:
    def test_rbac_staleness_no_write_permission_create_staleness(
        self,
        host_inventory_staleness_no_write_permissions: ApplicationHostInventory,
    ) -> None:
        """
        Test response when a user who doesn't have write permission tries to create
        staleness settings via REST API

        1. Issue a POST request on /account/staleness as the user who doesn't have
           write permission
        2. Ensure POST request returns a 403 response

        metadata:
            requirements: inv-staleness-post
            assignee: msager
            importance: high
            title: Inventory: Confirm users without write permission can't create
                staleness settings
        """
        settings = dict(zip(get_staleness_fields(), [1, 2, 3], strict=False))
        resp = (
            host_inventory_staleness_no_write_permissions.apis.account_staleness.create_staleness(
                **settings
            )
        )
        assert resp.status_code == 403

    def test_rbac_staleness_no_write_permission_update_staleness(
        self,
        host_inventory: ApplicationHostInventory,
        host_inventory_staleness_no_write_permissions: ApplicationHostInventory,
    ) -> None:
        """
        Test response when a user who doesn't have write permission tries to update
        staleness settings via REST API

        1. Issue a POST request on /account/staleness as admin to create settings
        2. Issue a PATCH request on /account/staleness as the user who doesn't have
           write permission
        3. Ensure PATCH request returns a 403 response

        metadata:
            requirements: inv-staleness-patch
            assignee: msager
            importance: high
            title: Inventory: Confirm users without write permission can't update
                staleness settings
        """
        settings = dict(zip(get_staleness_fields(), [1, 2, 3], strict=False))
        host_inventory.apis.account_staleness.create_staleness(**settings)

        settings = dict(zip(get_staleness_fields(), [4, 5, 6], strict=False))
        resp = (
            host_inventory_staleness_no_write_permissions.apis.account_staleness.update_staleness(
                **settings
            )
        )
        assert resp.status_code == 403

    def test_rbac_staleness_no_write_permission_delete_staleness(
        self,
        host_inventory: ApplicationHostInventory,
        host_inventory_staleness_no_write_permissions: ApplicationHostInventory,
    ) -> None:
        """
        Test response when a user who doesn't have write permission tries to delete
        staleness settings via REST API

        1. Issue a POST request on /account/staleness as admin to create settings
        2. Issue a DELETE request on /account/staleness as the user who doesn't have
           write permission
        3. Ensure DELETE request returns a 403 response

        metadata:
            requirements: inv-staleness-delete
            assignee: msager
            importance: high
            title: Inventory: Confirm users without write permission can't delete
                staleness settings
        """
        settings = dict(zip(get_staleness_fields(), [1, 2, 3], strict=False))
        host_inventory.apis.account_staleness.create_staleness(**settings).json()

        resp = (
            host_inventory_staleness_no_write_permissions.apis.account_staleness.delete_staleness()
        )
        assert resp.status_code == 403
