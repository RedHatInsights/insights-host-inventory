import pytest
from iqe.base.application.implementations.web_ui import navigate_to
from iqe.utils.blockers import iqe_blocker

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory_api import HostOut

pytestmark = [pytest.mark.ui, pytest.mark.rbac_dependent]


class TestUIRBACCustomStalenessAccountLevel:
    def test_rbac_custom_staleness_page_without_access(
        self, host_inventory_frontend_non_org_admin: ApplicationHostInventory
    ):
        """
        Test that user without staleness permissions can't access Staleness and Deletion page

        metadata:
            requirements: inv-rbac, inv-staleness-get
            importance: high
            assignee: zabikeno
        """
        view = navigate_to(host_inventory_frontend_non_org_admin, "CustomStaleness")
        assert view.no_access.is_displayed, (
            "User without staleness permissions should not have access to Staleness "
            "and Deletion page"
        )

    def test_rbac_custom_staleness_admin_and_hosts_viewer(
        self,
        host_inventory_frontend_non_org_admin: ApplicationHostInventory,
        setup_ui_host_module: HostOut,
        setup_ui_user_with_staleness_admin_hosts_viewer_roles,
    ):
        """
        User with Staleness Admin role, but without Hosts Admin role not able to edit
        staleness setting

        metadata:
            requirements: inv-rbac, inv-staleness-patch
            importance: high
            assignee: zabikeno
        """
        view = navigate_to(host_inventory_frontend_non_org_admin, "CustomStaleness")
        view.browser.refresh()
        assert view.organization_level_card.rbac.edit_disabled, (
            "Edit button should be disabled without inventory:hosts:write permission"
        )

    @iqe_blocker(iqe_blocker.jira("RHINENG-14129", category=iqe_blocker.PRODUCT_ISSUE))
    def test_rbac_custom_staleness_viewer(
        self,
        host_inventory_frontend_non_org_admin: ApplicationHostInventory,
        setup_ui_host_module: HostOut,
        setup_ui_user_with_staleness_viewer_role,
    ):
        """
        Test that user with staleness:read permission can't modify Staleness and Deletion page

        metadata:
            requirements: inv-rbac, inv-staleness-patch
            importance: high
            assignee: zabikeno
        """
        view = navigate_to(host_inventory_frontend_non_org_admin, "CustomStaleness")
        view.browser.refresh()
        assert view.organization_level_card.rbac.edit_disabled, (
            "Edit button should be disabled for staleness:stalenss:read permission."
        )
