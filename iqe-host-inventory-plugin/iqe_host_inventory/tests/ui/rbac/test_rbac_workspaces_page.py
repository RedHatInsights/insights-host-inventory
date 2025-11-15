import pytest
from iqe.base.application.implementations.web_ui import navigate_to

pytestmark = [pytest.mark.ui, pytest.mark.rbac_dependent]


def test_rbac_workspaces_page_without_access(workspaces_collection_non_org_admin):
    """
    Test that non admin user doesn't have permissions to view Inventory Workspaces UI
    metadata:
        importance: high
        requirements: inv-rbac
        assignee: zabikeno
    """
    view = navigate_to(workspaces_collection_non_org_admin, "WorkspacesEmptyState")
    assert view.is_displayed, (
        "Without inventory:groups:read permission user not able to see Workspaces page"
    )


@pytest.mark.usefixtures("setup_ui_user_with_workspaces_viewer_role")
class TestUIRBACWorkspacesViewerRole:
    def test_rbac_workspaces_viewer_workspaces_page(
        self,
        workspaces_collection_non_org_admin,
        setup_ui_workspaces_with_hosts_for_sorting,
    ):
        """
        Test that user with Inventory Workspace Viewer role
        can see all workspaces and not able to do any modification to workspace

        metadata:
            requirements:
                - inv-rbac
                - inv-groups-remove-hosts
                - inv-groups-add-hosts
                - inv-groups-post
            importance: high
            assignee: zabikeno
        """
        workspace, _, _ = setup_ui_workspaces_with_hosts_for_sorting
        view = navigate_to(workspaces_collection_non_org_admin, "All")
        view.refresh_page()

        assert view.rbac.create_disabled, (
            "'Create workspace' button should be disabled for Inventory Workspace Viewer role"
        )

        view.search(workspace.name)
        assert view.results == 1, "User should be able to see created workspace from admin account"

        view.table.row()[4].widget.open()
        assert view.rbac.workspace_actions_disabled, (
            "Per-row workspace's actions should be disabled"
        )

        view.bulk_select.select()
        view.workspace_actions.open()
        assert view.rbac.delete_disabled, "Bulk workspace's actions should be disabled"

    def test_rbac_workspaces_viewer_workspace_details_page(
        self,
        workspaces_collection_non_org_admin,
        setup_ui_workspaces_with_hosts_for_sorting,
    ):
        """
        Test that user with Inventory Workspace Viewer role
        not able to do any modification to workspace in details page
        (without hosts permissions)

        metadata:
            requirements:
                - inv-rbac
                - inv-groups-remove-hosts
                - inv-groups-add-hosts
            importance: high
            assignee: zabikeno
        """
        workspace, _, _ = setup_ui_workspaces_with_hosts_for_sorting
        workspace = workspaces_collection_non_org_admin.instantiate_with_name(workspace.name)
        view = navigate_to(workspace, "WorkspaceDetails")

        assert view.title.text == workspace.name
        assert view.rbac.workspace_actions_disabled, "Workspace's actions should be disabled"
        assert "Access needed for systems in this workspace" in view.no_access.text

    @pytest.mark.parametrize(
        "empty_workspace", [True, False], ids=["empty-workspace", "workspace-with-systems"]
    )
    def test_rbac_workspaces_and_hosts_viewer_workspace_details_page(
        self,
        workspaces_collection_non_org_admin,
        setup_ui_user_with_hosts_viewer_role,
        empty_workspace,
        setup_ui_empty_workspace_module,
        setup_ui_workspaces_with_hosts_for_sorting,
    ):
        """
        Test that user with Inventory Workspace Viewer role and Inventory Hosts
        Viewer can see systems in workspace, but not able to do any modification to workspace

        metadata:
            requirements:
                - inv-rbac
                - inv-groups-remove-hosts
                - inv-groups-add-hosts
            importance: high
            assignee: zabikeno
        """
        workspace_with_host, _, _ = setup_ui_workspaces_with_hosts_for_sorting
        expected_workspace = (
            setup_ui_empty_workspace_module if empty_workspace else workspace_with_host
        )
        workspace = workspaces_collection_non_org_admin.instantiate_with_name(
            expected_workspace.name
        )
        view = navigate_to(workspace, "SystemsTab")
        view.refresh_page()

        if empty_workspace:
            assert view.rbac.add_systems_disabled, "'Add systems' button should be disabled"
            assert not view.table.is_displayed
        else:
            assert view.rbac.add_systems_disabled, "'Add systems' button should be disabled"
            view.table.row()[5].widget.open()
            assert view.rbac.remove_from_workspace_disabled, (
                "'Remove from workspace' button should be disabled"
            )


@pytest.mark.usefixtures("setup_ui_user_with_workspaces_admin_role")
class TestUIRBACWorkspacesAdminRole:
    def test_rbac_workspaces_admin_workspaces_page(
        self,
        workspaces_collection_non_org_admin,
        setup_ui_workspaces_with_hosts_for_sorting,
    ):
        """
        Test that user with Inventory Workspaces Administrator role
        can see all workspaces, able see all actions require to modify a workspace

        metadata:
            requirements:
                - inv-rbac
                - inv-groups-post
            importance: high
            assignee: zabikeno
        """
        workspace, _, _ = setup_ui_workspaces_with_hosts_for_sorting
        view = navigate_to(workspaces_collection_non_org_admin, "All")
        view.refresh_page()

        assert not view.rbac.create_disabled, (
            "'Create workspace' button should be enabled for "
            "Inventory Workspaces Administartor role"
        )

        view.search(workspace.name)
        assert view.results == 1, "User should be able to see workspace"

        total_systems = view.table.row().total_systems.text
        assert int(total_systems) == 1, (
            "User without Systems's roles able to see total systems in workspace"
        )

    def test_rbac_workspaces_admin_workspace_info(
        self,
        workspaces_collection_non_org_admin,
        setup_ui_workspaces_with_hosts_for_sorting,
    ):
        """
        Test that user with Inventory Workspaces Administrator role
        and without User Access Administrator role has disabled
        'Manage Access" button

        metadata:
            requirements: inv-rbac
            importance: high
            assignee: zabikeno
        """
        workspace, _, _ = setup_ui_workspaces_with_hosts_for_sorting
        workspace = workspaces_collection_non_org_admin.instantiate_with_name(workspace.name)
        view = navigate_to(workspace, "InfoTab")

        assert view.rbac.manage_access_disabled, (
            "Without User Access administrator role Manage access button should be disabled"
        )

    def test_rbac_workspaces_admin_workspaces_info_with_user_access_role(
        self,
        workspaces_collection_non_org_admin,
        setup_ui_workspaces_with_hosts_for_sorting,
        setup_ui_user_with_user_access_admin_role,
    ):
        """
        Test that user with Inventory Workspaces Administrator role
        and User Access Administrator role has enabled
        'Manage Access" button

        metadata:
            requirements: inv-rbac
            importance: high
            assignee: zabikeno
        """
        workspace, _, _ = setup_ui_workspaces_with_hosts_for_sorting
        workspace = workspaces_collection_non_org_admin.instantiate_with_name(workspace.name)
        view = navigate_to(workspace, "InfoTab")
        view.refresh_page()
        assert not view.rbac.manage_access_disabled
