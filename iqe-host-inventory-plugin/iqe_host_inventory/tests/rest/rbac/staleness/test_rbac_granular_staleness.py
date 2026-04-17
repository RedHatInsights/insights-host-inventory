"""
metadata:
    requirements: inv-rbac-granular-groups
"""

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.fixtures.rbac_fixtures import RBacResources
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.rbac_utils import RBACInventoryPermission
from iqe_host_inventory.utils.staleness_utils import get_staleness_fields

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.backend,
    pytest.mark.rbac_dependent,
    pytest.mark.usefixtures("hbi_staleness_cleanup"),
]


@pytest.fixture(
    params=["default_workspace", "ungrouped_workspace", "custom_workspace"],
    scope="class",
)
def granular_staleness_user_setup(
    request: pytest.FixtureRequest,
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup_class,
    host_inventory: ApplicationHostInventory,
) -> None:
    """Set up a user with staleness:*:* + inventory:hosts:* permissions scoped
    to a specific workspace. Staleness endpoints are org-wide and require
    global permissions, so all requests from this user should be denied."""
    if (
        host_inventory.application.config.current_env.lower() == "clowder_smoke"
        and not host_inventory.unleash.is_kessel_phase_1_enabled()
        and request.param != "custom_workspace"
    ):
        pytest.skip("Default and ungrouped workspaces are not available if Kessel is disabled")
    if request.param == "default_workspace":
        hbi_groups = [host_inventory.apis.workspaces.get_default_workspace().id]
    elif request.param == "ungrouped_workspace":
        hbi_groups = [host_inventory.apis.workspaces.get_ungrouped_workspace().id]
    else:
        hbi_groups = [rbac_setup_resources_for_granular_rbac[1][0]]

    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.STALENESS_ALL, RBACInventoryPermission.HOSTS_ALL],
        hbi_groups=hbi_groups,
    )


@pytest.mark.usefixtures("granular_staleness_user_setup")
class TestRBACGranularStalenessDenied:
    def test_rbac_granular_staleness_get_defaults_denied(
        self,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """
        Test that a user with staleness permissions scoped to a specific
        workspace cannot retrieve the default staleness settings.

        Staleness endpoints are org-wide and require global permissions —
        workspace-scoped permissions should not grant access.

        1. Issue a GET request on /account/staleness/defaults as a user with
           workspace-scoped staleness permissions
        2. Ensure GET request returns a 403 response

        metadata:
            requirements: inv-staleness-get-defaults
            assignee: fstavela
            importance: high
            negative: true
            title: Inventory: Confirm users with workspace-scoped staleness permissions
                can't access the default staleness settings
        """
        with raises_apierror(403):
            host_inventory_non_org_admin.apis.account_staleness.get_default_staleness()

    def test_rbac_granular_staleness_get_staleness_denied(
        self,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """
        Test that a user with staleness permissions scoped to a specific
        workspace cannot retrieve the current staleness settings.

        Staleness endpoints are org-wide and require global permissions —
        workspace-scoped permissions should not grant access.

        1. Issue a GET request on /account/staleness as a user with
           workspace-scoped staleness permissions
        2. Ensure GET request returns a 403 response

        metadata:
            requirements: inv-staleness-get
            assignee: fstavela
            importance: high
            negative: true
            title: Inventory: Confirm users with workspace-scoped staleness permissions
                can't access the current staleness settings
        """
        with raises_apierror(403):
            host_inventory_non_org_admin.apis.account_staleness.get_staleness()

    def test_rbac_granular_staleness_create_staleness_denied(
        self,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """
        Test that a user with staleness permissions scoped to a specific
        workspace cannot create staleness settings.

        Staleness endpoints are org-wide and require global permissions —
        workspace-scoped permissions should not grant access.

        1. Issue a POST request on /account/staleness as a user with
           workspace-scoped staleness permissions
        2. Ensure POST request returns a 403 response

        metadata:
            requirements: inv-staleness-post
            assignee: fstavela
            importance: high
            negative: true
            title: Inventory: Confirm users with workspace-scoped staleness permissions
                can't create staleness settings
        """
        settings = dict(zip(get_staleness_fields(), [1, 2, 3], strict=False))
        with raises_apierror(403):
            host_inventory_non_org_admin.apis.account_staleness.create_staleness(**settings)

    def test_rbac_granular_staleness_update_staleness_denied(
        self,
        host_inventory: ApplicationHostInventory,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """
        Test that a user with staleness permissions scoped to a specific
        workspace cannot update staleness settings.

        Staleness endpoints are org-wide and require global permissions —
        workspace-scoped permissions should not grant access.

        1. Issue a POST request on /account/staleness as admin to create settings
        2. Issue a PATCH request on /account/staleness as a user with
           workspace-scoped staleness permissions
        3. Ensure PATCH request returns a 403 response

        metadata:
            requirements: inv-staleness-patch
            assignee: fstavela
            importance: high
            negative: true
            title: Inventory: Confirm users with workspace-scoped staleness permissions
                can't update staleness settings
        """
        settings = dict(zip(get_staleness_fields(), [1, 2, 3], strict=False))
        host_inventory.apis.account_staleness.create_staleness(**settings)

        settings = dict(zip(get_staleness_fields(), [4, 5, 6], strict=False))
        with raises_apierror(403):
            host_inventory_non_org_admin.apis.account_staleness.update_staleness(**settings)

    def test_rbac_granular_staleness_delete_staleness_denied(
        self,
        host_inventory: ApplicationHostInventory,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ) -> None:
        """
        Test that a user with staleness permissions scoped to a specific
        workspace cannot delete staleness settings.

        Staleness endpoints are org-wide and require global permissions —
        workspace-scoped permissions should not grant access.

        1. Issue a POST request on /account/staleness as admin to create settings
        2. Issue a DELETE request on /account/staleness as a user with
           workspace-scoped staleness permissions
        3. Ensure DELETE request returns a 403 response

        metadata:
            requirements: inv-staleness-delete
            assignee: fstavela
            importance: high
            negative: true
            title: Inventory: Confirm users with workspace-scoped staleness permissions
                can't delete staleness settings
        """
        settings = dict(zip(get_staleness_fields(), [1, 2, 3], strict=False))
        host_inventory.apis.account_staleness.create_staleness(**settings)

        with raises_apierror(403):
            host_inventory_non_org_admin.apis.account_staleness.delete_staleness()
