import pytest
from iqe.base.application.implementations.web_ui import navigate_to
from wait_for import wait_for

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.entities.systems import SystemCollection

pytestmark = [pytest.mark.ui, pytest.mark.rbac_dependent]


@pytest.fixture
def navigate_to_systems_page(systems_collection_non_org_admin: SystemCollection):
    view = navigate_to(systems_collection_non_org_admin, "Systems")

    yield view


def test_rbac_systems_page_without_access(systems_collection_non_org_admin):
    """
    Test that user without hosts permissions can't access Systems page
    metadata:
        importance: high
        requirements: inv-rbac, inv-hosts-get-list
        assignee: zabikeno
    """
    view = navigate_to(systems_collection_non_org_admin, "SystemsEmptyState")
    assert view.is_displayed, (
        "Without inventory:hosts:read permissions user should see empty state page"
    )


@pytest.mark.usefixtures("setup_ui_user_with_hosts_viewer_role")
class TestUIRBACHostsViewerRole:
    def test_rbac_hosts_viewer_systems_page(
        self,
        systems_collection_non_org_admin,
        setup_ui_host_module,
        navigate_to_systems_page,
    ):
        """
        Test that user with Inventory Hosts Viewer role
        can see all systems and not able to do any modification to systems

        metadata:
            requirements:
                - inv-rbac
                - inv-hosts-patch
                - inv-hosts-delete-by-id
                - inv-groups-remove-hosts
                - inv-groups-add-hosts
            importance: high
            assignee: zabikeno
        """
        view = navigate_to_systems_page
        view.refresh_page()

        view.search(setup_ui_host_module.display_name, column="Name")
        assert view.results == 1, "User should be able to see system from admin account"
        view.bulk_select.select()
        assert view.rbac.bulk_delete_disabled, "Bulk delete systems should be disabled"

        view.system_actions.open()
        assert view.rbac.workspace_actions_disabled, "Workspace bulk actions should be disabled"
        view.bulk_select.unselect()

        view.table.row()[6].widget.open()
        assert view.rbac.workspace_actions_disabled, "Workspace actions per-row should be disabled"
        assert view.rbac.system_actions_disabled, "Systems actions per-row should be disabled"

    def test_rbac_hosts_viewer_details_page(
        self,
        systems_collection_non_org_admin,
        setup_ui_host_module,
    ):
        """
        Test that user with Inventory Hosts Viewer role
        not able to do any modification to system from System's
        Details page

        metadata:
            requirements:
                - inv-rbac
                - inv-hosts-delete-by-id
            importance: high
            assignee: zabikeno
        """
        host = systems_collection_non_org_admin.instantiate_with_id(setup_ui_host_module.id)

        view = navigate_to(host, "SystemDetails")
        assert view.rbac.delete_system_disabled, (
            "Delete button should be disabled for Hosts Viewer role"
        )


@pytest.mark.usefixtures("setup_ui_user_with_hosts_admin_role")
class TestUIRBACHostsAdminRole:
    def test_rbac_hosts_admin_systems_page(
        self,
        systems_collection_non_org_admin,
        setup_ui_host_module,
        navigate_to_systems_page,
    ):
        """
        Test that secondary user with Inventory Hosts Administrator role
        can see system uploaded to admin account and has enabled all system's actions

        metadata:
            requirements:
                - inv-rbac
                - inv-hosts-patch
                - inv-hosts-delete-by-id
                - inv-groups-remove-hosts
                - inv-groups-add-hosts
            importance: high
            assignee: zabikeno
        """
        view = navigate_to_systems_page

        view.search(setup_ui_host_module.display_name, column="Name")
        assert view.results == 1, "User should be able to see system from admin account"

        view.bulk_select.select()
        assert not view.rbac.bulk_delete_disabled, "Bulk delete systems should be enabled"

        view.system_actions.open()
        assert view.rbac.workspace_actions_disabled, (
            "Workspace bulk actions should be disabled - user has only Hosts Administrator role"
        )
        view.bulk_select.unselect()

        view.table.row()[6].widget.open()
        assert not view.rbac.system_actions_disabled, "Systems actions per-row should be enabled"
        assert view.rbac.workspace_actions_disabled, (
            "Workspace actions per-row should be disabled - user has only Hosts Administrator role"
        )

    @pytest.mark.parametrize(
        "empty_workspace", [True, False], ids=["empty-workspace", "workspace-with-system"]
    )
    def test_rbac_hosts_admin_systems_page_workspace_actions(
        self,
        host_inventory_frontend: ApplicationHostInventory,
        systems_collection_non_org_admin,
        setup_ui_user_with_workspaces_admin_role,
        setup_ui_host_module,
        setup_ui_empty_workspace_module,
        empty_workspace: bool,
        navigate_to_systems_page,
    ):
        """
        Test that user with Inventory Workspaces Administrator role can
        use workspace's actions on Systems page

        metadata:
            requirements:
                - inv-rbac
                - inv-groups-remove-hosts
                - inv-groups-add-hosts
            importance: high
            assignee: zabikeno
        """
        if not empty_workspace:
            # add system to workspace to test workspaces features on Systems page
            host_inventory_frontend.apis.groups.add_hosts_to_group(
                group=setup_ui_empty_workspace_module.id, hosts=[setup_ui_host_module.id]
            )

        view = navigate_to_systems_page
        view.refresh_page()
        view.table.clear_cache()
        view.search(setup_ui_host_module.display_name, column="Name")

        view.bulk_select.select()
        view.system_actions.open()
        if empty_workspace:
            assert not view.rbac.add_to_workspace_disabled, (
                "User should be able to add system to workspace."
            )
        else:
            assert not view.rbac.remove_from_workspace_disabled, (
                "User should be able to remove system from workspace."
            )
        view.bulk_select.unselect()

        view.table.row()[6].widget.open()
        if empty_workspace:
            assert not view.rbac.add_to_workspace_disabled, (
                "User should be able to add system to workspace."
            )
        else:
            assert not view.rbac.remove_from_workspace_disabled, (
                "User should be able to remove system from workspace."
            )


class TestUIRBACHostsGranularPermissions:
    def test_rbac_hosts_granular_systems_page_read(
        self,
        systems_collection_non_org_admin,
        host_inventory_frontend: ApplicationHostInventory,
        setup_ui_host,
        setup_ui_user_granular_hosts_permissions,
    ):
        """
        User should only see workspace from specific group that has
        inventory:hosts:read permission and can not
        make any modification to this host

        metadata:
            requirements:
                - inv-rbac-granular-groups
                - inv-hosts-patch
                - inv-hosts-delete-by-id
                - inv-groups-get-list
            importance: high
            assignee: zabikeno
        """
        workspace, _, _ = setup_ui_user_granular_hosts_permissions
        host = setup_ui_host
        # add system to workspace to test workspaces features on Systems page
        host_inventory_frontend.apis.groups.add_hosts_to_group(group=workspace.id, hosts=[host.id])

        view = navigate_to(systems_collection_non_org_admin, "Systems")
        view.refresh_page()

        # ensure right host is displayed
        actual_hosts = {row.name.text for row in view.table.rows()}
        assert len(actual_hosts) == 1 and host.display_name in actual_hosts, (
            f"User can see system from workspace '{workspace.name}': it has 1 system"
        )

        # ensure right workspace name is displayed
        workspace_column = view.table.row().workspace.text
        assert workspace.name == workspace_column

        view.bulk_select.select()
        assert view.rbac.bulk_delete_disabled, "Bulk delete systems should be disabled"
        view.bulk_select.unselect()

        view.table.row()[6].widget.open()
        assert view.rbac.system_actions_disabled, "Systems actions per-row should be disabled"

    def test_rbac_hosts_granular_systems_page_write(
        self,
        systems_collection_non_org_admin,
        host_inventory_frontend: ApplicationHostInventory,
        setup_ui_host,
        setup_ui_user_granular_hosts_permissions,
    ):
        """
        User should only see system from specific workspace that has
        inventory:hosts:* permission and can make any modification to this host

        metadata:
            requirements:
                - inv-rbac-granular-groups
                - inv-hosts-patch
                - inv-hosts-delete-by-id
            importance: high
            assignee: zabikeno
        """
        _, workspace, _ = setup_ui_user_granular_hosts_permissions
        host = setup_ui_host
        # add system to workspace to test workspaces features on Systems page
        host_inventory_frontend.apis.groups.add_hosts_to_group(group=workspace.id, hosts=[host.id])

        view = navigate_to(systems_collection_non_org_admin, "Systems")
        view.refresh_page()

        view.search(host.display_name, column="Name")
        view.bulk_select.select()
        assert not view.rbac.bulk_delete_disabled, "Bulk delete systems should be enabled"
        view.bulk_select.unselect()

        view.table.row()[6].widget.open()
        assert not view.rbac.system_actions_disabled, "Systems actions per-row should be enabled"

    @pytest.mark.parametrize(
        "without_workspace_permissions",
        [True, False],
        ids=["without-workspace-permissions", "workspace-permissions"],
    )
    def test_rbac_groups_granular_systems_page_workspace_actions(
        self,
        systems_collection_non_org_admin,
        host_inventory_frontend: ApplicationHostInventory,
        setup_ui_host,
        setup_ui_user_granular_hosts_permissions,
        without_workspace_permissions: bool,
    ):
        """
        Test workspace actions on Systems page with workspaces that has different
        granular permissions

        metadata:
            requirements:
                - inv-rbac-granular-groups
                - inv-groups-remove-hosts
                - inv-groups-add-hosts
            importance: high
            assignee: zabikeno
        """
        workspace_hosts_r_groups_rw, workspace_hosts_rw, workspace_groups_rw = (
            setup_ui_user_granular_hosts_permissions
        )
        host = setup_ui_host
        # add system to workspace that doesn't have groups permission
        # or add system to workspace that has at least groups:read permission
        workspace = (
            workspace_hosts_rw if without_workspace_permissions else workspace_hosts_r_groups_rw
        )
        host_inventory_frontend.apis.groups.add_hosts_to_group(group=workspace.id, hosts=[host.id])

        view = navigate_to(systems_collection_non_org_admin, "Systems")
        view.refresh_page()

        # ensure right workspace name is displayed
        assert view.results == 1, "Only 1 system is uploaded for granular access"
        workspace_column = view.table.row().workspace.text
        assert workspace.name == workspace_column

        # verify workspace bulk actions for system in current workspace
        view.bulk_select.select()
        view.system_actions.open()
        if without_workspace_permissions:
            assert view.rbac.workspace_actions_disabled
        else:
            assert not view.rbac.remove_from_workspace_disabled
        view.bulk_select.unselect()

        # verify workspace per-row actions for system in current workspace
        view.table.row()[6].widget.open()
        if without_workspace_permissions:
            assert view.rbac.workspace_actions_disabled
        else:
            assert not view.rbac.remove_from_workspace_disabled

        # workspace filter menu should display workspaces that have groups:read access
        if not without_workspace_permissions:
            view.column_selector.item_select("Workspace")
            expected_workspaces = [workspace.name, workspace_groups_rw.name]
            workspaces_menu = view.checkbox_select_workspace.group_items
            # "No workspace" is filter for ungrouped systems
            workspaces_menu.remove("Ungrouped hosts")

            assert len(workspaces_menu) == len(expected_workspaces)
            assert all(workspace in expected_workspaces for workspace in workspaces_menu), (
                "Workspace filter menu should display workspaces that has groups:read access"
            )

    @pytest.mark.parametrize(
        "hosts_read_permission", [True, False], ids=["inventory:hosts:read", "inventory:hosts:*"]
    )
    def test_rbac_hosts_granular_details_page(
        self,
        host_inventory_frontend,
        systems_collection_non_org_admin,
        setup_ui_host,
        setup_ui_user_granular_hosts_permissions,
        hosts_read_permission,
    ):
        """
        Test that user with specific inventory:hosts permission
        able/not able to do any modification to system in System's
        Details page

        https://issues.redhat.com/browse/ESSNTL-5110

        metadata:
            requirements: inv-rbac-granular-groups, inv-hosts-delete-by-id
            importance: high
            assignee: zabikeno
        """
        workspace_hosts_r, workspace_hosts_rw, _ = setup_ui_user_granular_hosts_permissions
        # add system to workspace that doesn't have hosts:* permission
        # or add system to workspace that has at least hosts:read permission
        workspace = workspace_hosts_r if hosts_read_permission else workspace_hosts_rw
        host_inventory_frontend.apis.groups.add_hosts_to_group(
            group=workspace.id, hosts=[setup_ui_host.id]
        )

        host = systems_collection_non_org_admin.instantiate_with_id(setup_ui_host.id)
        view = navigate_to(host, "SystemDetails")
        if hosts_read_permission:
            assert view.rbac.delete_system_disabled, (
                "'Delete' button should be disabled with inventory:hosts:read permission."
            )
        else:
            assert not view.rbac.delete_system_disabled, (
                "'Delete' button should be enabled with inventory:hosts:* permission."
            )


class TestRBACHostsUngrouped:
    def test_rbac_hosts_granular_ungrouped_hosts_systems_page(
        self,
        host_inventory_frontend,
        systems_collection_non_org_admin,
        setup_ui_host,
        setup_user_granular_hosts_all_null_permissions,
    ):
        """
        User with inventory:hosts:* should see all systems from "Ungrouped Hosts"
        workspace

        metadata:
            requirements: inv-rbac-granular-groups
            importance: high
            assignee: zabikeno
        """
        view = navigate_to(systems_collection_non_org_admin, "Systems")
        wait_for(lambda: view.top_paginator.is_displayed, timeout=40)
        view.search(setup_ui_host.display_name, column="Name")

        workspace_column = view.table.row().workspace.text
        assert workspace_column == "Ungrouped Hosts"

        view.bulk_select.select()
        assert not view.rbac.bulk_delete_disabled, "Bulk delete systems should be enabled."
        view.bulk_select.unselect()

        view.table.row()[6].widget.open()
        assert not view.rbac.system_actions_disabled, "Systems actions per-row should be enabled"

        host = systems_collection_non_org_admin.instantiate_with_id(setup_ui_host.id)
        view = navigate_to(host, "SystemDetails")
        assert not view.rbac.delete_system_disabled, (
            "Delete button should be enabled for inventory:hosts:* permissions"
        )
