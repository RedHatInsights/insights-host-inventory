from collections.abc import Generator

import pytest
from fauxfactory import gen_alphanumeric
from iqe.base.application import Application
from iqe.base.application.implementations.rest import ViaREST
from iqe_rbac.entities.group import Group

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.entities.systems import SystemCollection
from iqe_host_inventory.entities.workspaces import Workspace
from iqe_host_inventory.entities.workspaces import WorkspaceCollection
from iqe_host_inventory.modeling.groups_api import GroupData
from iqe_host_inventory.modeling.uploads import HostData
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_operating_system
from iqe_host_inventory.utils.datagen_utils import get_default_os_centos
from iqe_host_inventory.utils.rbac_utils import RBACInventoryPermission
from iqe_host_inventory.utils.rbac_utils import RBACRoles
from iqe_host_inventory.utils.rbac_utils import update_group_with_roles
from iqe_host_inventory.utils.ui_utils import UNIQUE_UI_ID
from iqe_host_inventory.utils.ui_utils import generate_workspace_name
from iqe_host_inventory.utils.upload_utils import IMAGE_MODE_ARCHIVE
from iqe_host_inventory.utils.upload_utils import get_archive_and_collect_method
from iqe_host_inventory_api import GroupOutWithHostCount
from iqe_host_inventory_api import HostOut

PUBLIC_DNS_IP_RHEL_ARCHIVE = "rhel90.public_dns_ip.tar.gz"
EDGE_STAGE_ARCHIVE = "edge-hbi-ui-stage.tar.gz"


@pytest.fixture(scope="session")
def systems_collection(host_inventory_frontend) -> SystemCollection:
    return host_inventory_frontend.collections.systems


@pytest.fixture(scope="session")
def workspaces_collection(host_inventory_frontend) -> WorkspaceCollection:
    return host_inventory_frontend.collections.workspaces


@pytest.fixture(scope="module")
def setup_ui_host_module(host_inventory_frontend: ApplicationHostInventory) -> HostOut:
    return host_inventory_frontend.upload.create_host(cleanup_scope="module")


@pytest.fixture(scope="function")
def setup_ui_host(host_inventory_frontend: ApplicationHostInventory) -> HostOut:
    return host_inventory_frontend.upload.create_host()


@pytest.fixture(scope="module")
def setup_ui_bootc_host(host_inventory_frontend: ApplicationHostInventory) -> HostOut:
    return host_inventory_frontend.upload.create_host(
        base_archive=IMAGE_MODE_ARCHIVE, cleanup_scope="module"
    )


@pytest.fixture
def setup_ui_edge_host(host_inventory_frontend: ApplicationHostInventory) -> HostOut:
    return host_inventory_frontend.upload.create_host(base_archive=EDGE_STAGE_ARCHIVE)


@pytest.fixture
def setup_ui_centos_host(host_inventory_frontend: ApplicationHostInventory) -> HostOut:
    base_archive, core_collect = get_archive_and_collect_method("CentOS Linux")
    return host_inventory_frontend.upload.create_host(
        operating_system=get_default_os_centos(),
        base_archive=base_archive,
        core_collect=core_collect,
    )


@pytest.fixture(scope="module")
def setup_ui_public_dns_ip_host(host_inventory_frontend: ApplicationHostInventory) -> HostOut:
    return host_inventory_frontend.upload.create_host(
        base_archive=PUBLIC_DNS_IP_RHEL_ARCHIVE, cleanup_scope="module"
    )


@pytest.fixture(scope="module")
def setup_ui_empty_workspace_module(
    workspaces_collection: WorkspaceCollection,
    hbi_application_frontend: Generator[Application, None, None],
) -> Generator[Workspace, None, None]:
    with hbi_application_frontend.context.use(ViaREST):
        workspace = workspaces_collection.create(generate_workspace_name(), cleanup_scope="module")

    yield workspace


@pytest.fixture
def setup_ui_empty_workspace(
    workspaces_collection: WorkspaceCollection,
    hbi_application_frontend: Generator[Application, None, None],
) -> Generator[Workspace, None, None]:
    with hbi_application_frontend.context.use(ViaREST):
        workspace = workspaces_collection.create(generate_workspace_name())

    yield workspace


@pytest.fixture(scope="module")
def setup_ui_hosts_for_sorting(host_inventory_frontend: ApplicationHostInventory) -> list[HostOut]:
    hosts_data = [HostData(display_name=generate_display_name() + UNIQUE_UI_ID) for _ in range(10)]
    hosts = host_inventory_frontend.upload.create_hosts(
        hosts_data=hosts_data, cleanup_scope="module"
    )

    return hosts


@pytest.fixture(scope="module")
def setup_ui_hosts_to_delete(host_inventory_frontend: ApplicationHostInventory) -> str:
    unique_id = gen_alphanumeric(4)
    hosts_data = [HostData(display_name=generate_display_name(unique_id)) for _ in range(5)]
    host_inventory_frontend.upload.create_hosts(hosts_data=hosts_data, cleanup_scope="module")

    return unique_id


@pytest.fixture(scope="module")
def setup_ui_hosts_with_different_os(
    host_inventory_frontend: ApplicationHostInventory,
) -> list[str]:
    # Let's have 3 hosts
    os_versions = [(7, 5), (7, 10), (9, 0)]
    os_list = [generate_operating_system("RHEL", major, minor) for major, minor in os_versions]
    os_filter_options = [f"RHEL {major}.{minor}" for major, minor in os_versions]

    hosts_data = [
        HostData(display_name_prefix=UNIQUE_UI_ID, operating_system=os) for os in os_list
    ]
    host_inventory_frontend.upload.create_hosts(hosts_data=hosts_data, cleanup_scope="module")

    return os_filter_options


@pytest.fixture(scope="module")
def setup_ui_workspaces_with_hosts_for_sorting(
    host_inventory_frontend: ApplicationHostInventory,
) -> Generator[list[GroupOutWithHostCount], None, None]:
    """Fixture is used to test workspace UI sorting, in this case workspace
    should have at least 1 host to be displayed in systems table"""
    workspaces_data = []
    for _ in range(3):
        host = host_inventory_frontend.upload.create_host(
            display_name=generate_display_name(UNIQUE_UI_ID), cleanup_scope="module"
        )
        workspaces_data.append(GroupData(name=generate_workspace_name(UNIQUE_UI_ID), hosts=[host]))

    workspaces = host_inventory_frontend.apis.groups.create_groups(
        workspaces_data, cleanup_scope="module"
    )

    yield workspaces


@pytest.fixture(scope="module")
def setup_ui_workspace_with_multiple_hosts(
    hbi_application_frontend: Application,
    host_inventory_frontend: ApplicationHostInventory,
    workspaces_collection: WorkspaceCollection,
) -> Generator[tuple[Workspace, list[HostOut]], None, None]:
    """Fixture is used to test workspace with systems"""
    hosts_data = [HostData(display_name=generate_display_name(UNIQUE_UI_ID)) for _ in range(3)]
    systems = host_inventory_frontend.upload.create_hosts(
        hosts_data=hosts_data, cleanup_scope="module"
    )

    with hbi_application_frontend.context.use(ViaREST):
        workspace = workspaces_collection.create(
            generate_workspace_name(UNIQUE_UI_ID), systems=systems, cleanup_scope="module"
        )

    yield workspace, systems


@pytest.fixture(scope="module")
def setup_ui_empty_workspaces(
    host_inventory_frontend: ApplicationHostInventory,
) -> Generator[tuple[list[GroupOutWithHostCount], str], None, None]:
    """Fixture is used to test workspace UI sorting, in this case workspace
    should have at least 1 host to be displayed in systems table"""
    unique_id = gen_alphanumeric(4)
    workspaces_data = []
    for _ in range(3):
        workspaces_data.append(GroupData(name=generate_workspace_name(unique_id)))
    workspaces = host_inventory_frontend.apis.groups.create_groups(
        workspaces_data, cleanup_scope="module"
    )

    yield workspaces, unique_id


# RBAC UI fixtures


@pytest.fixture(scope="session")
def systems_collection_non_org_admin(host_inventory_frontend_non_org_admin) -> SystemCollection:
    return host_inventory_frontend_non_org_admin.collections.systems


@pytest.fixture(scope="session")
def workspaces_collection_non_org_admin(host_inventory_frontend_non_org_admin) -> SystemCollection:
    return host_inventory_frontend_non_org_admin.collections.workspaces


@pytest.fixture(scope="class")
def setup_ui_rbac_group_with_member(
    hbi_application_frontend: Application,
    hbi_frontend_non_org_admin_user_username: str,
) -> Generator[tuple[Group, Application], None, None]:
    with hbi_application_frontend.context.use(ViaREST):
        group = hbi_application_frontend.rbac.collections.groups.create(
            name=generate_workspace_name(),
            members=[
                hbi_application_frontend.rbac.collections.users.instantiate(
                    hbi_frontend_non_org_admin_user_username
                )
            ],
        )

    yield group, hbi_application_frontend

    with hbi_application_frontend.context.use(ViaREST):
        group.delete_if_exists()


@pytest.fixture(scope="class")
def setup_ui_user_with_hosts_viewer_role(setup_ui_rbac_group_with_member) -> None:
    group, app = setup_ui_rbac_group_with_member
    update_group_with_roles(app, group, [RBACRoles.HOSTS_VIEWER])


@pytest.fixture(scope="class")
def setup_ui_user_with_hosts_admin_role(setup_ui_rbac_group_with_member) -> None:
    group, app = setup_ui_rbac_group_with_member
    update_group_with_roles(app, group, [RBACRoles.HOSTS_ADMIN])


@pytest.fixture(scope="function")
def setup_ui_user_with_workspaces_viewer_role(setup_ui_rbac_group_with_member) -> None:
    group, app = setup_ui_rbac_group_with_member
    update_group_with_roles(app, group, [RBACRoles.GROUPS_VIEWER])


@pytest.fixture(scope="class")
def setup_ui_user_with_workspaces_admin_role(setup_ui_rbac_group_with_member) -> None:
    group, app = setup_ui_rbac_group_with_member
    update_group_with_roles(app, group, [RBACRoles.GROUPS_ADMIN])


@pytest.fixture(scope="function")
def setup_ui_user_with_staleness_viewer_role(setup_ui_rbac_group_with_member) -> None:
    group, app = setup_ui_rbac_group_with_member
    update_group_with_roles(app, group, [RBACRoles.STALENESS_VIEWER])


@pytest.fixture(scope="function")
def setup_ui_user_with_staleness_admin_hosts_viewer_roles(setup_ui_rbac_group_with_member) -> None:
    group, app = setup_ui_rbac_group_with_member
    update_group_with_roles(app, group, [RBACRoles.STALENESS_ADMIN, RBACRoles.HOSTS_VIEWER])


@pytest.fixture(scope="function")
def setup_ui_user_with_user_access_admin_role(setup_ui_rbac_group_with_member) -> None:
    """
    Give User Access Administrator role to non-admin user:
    without this role "Manage access" button in Workspace info tab
    will be disabled
    """
    group, app = setup_ui_rbac_group_with_member
    update_group_with_roles(app, group, [RBACRoles.USER_ACCESS])


@pytest.fixture
def setup_ui_user_with_rhel_admin_role(setup_ui_rbac_group_with_member) -> str:
    group, app = setup_ui_rbac_group_with_member
    update_group_with_roles(app, group, [RBACRoles.RHEL_ADMIN])

    return RBACRoles.RHEL_ADMIN


@pytest.fixture
def setup_ui_user_with_rhel_operator_role(setup_ui_rbac_group_with_member) -> str:
    group, app = setup_ui_rbac_group_with_member
    update_group_with_roles(app, group, [RBACRoles.RHEL_OPERATOR])

    return RBACRoles.RHEL_OPERATOR


@pytest.fixture
def setup_ui_user_with_rhel_viewer_role(setup_ui_rbac_group_with_member) -> str:
    group, app = setup_ui_rbac_group_with_member
    update_group_with_roles(app, group, [RBACRoles.RHEL_VIEWER])

    return RBACRoles.RHEL_VIEWER


@pytest.fixture(scope="class")
def setup_ui_user_granular_hosts_permissions(
    host_inventory_frontend: ApplicationHostInventory,
    hbi_frontend_non_org_admin_user_username: str,
):
    """
    Fixture to test diffrent hosts granular access.

    User that has hosts and groups granular access to groups:
        workspace_hosts_rw: inventory:hosts:*
        workspace_hosts_r_groups_rw: inventory:hosts:read, inventory:groups:*
        workspace_groups_rw: inventory:groups:*, (to tests groups features on systems page)
    """
    rbac_apis = host_inventory_frontend.apis.rbac
    to_delete: list[tuple[str, list[str]]] = []

    # prepare workspaces that will have diffrent permissions
    workspaces_data = [GroupData(hosts=[]) for i in range(3)]
    workspace_hosts_r_groups_rw, workspace_hosts_rw, workspace_groups_rw = (
        host_inventory_frontend.apis.groups.create_groups(workspaces_data, cleanup_scope="class")
    )

    # create RBAC group and add user to it
    group = rbac_apis.create_group(permission=RBACInventoryPermission.HOSTS_READ)
    rbac_apis.add_user_to_a_group(hbi_frontend_non_org_admin_user_username, group.uuid)

    # assign hosts:read permission to first workspace
    role_1 = rbac_apis.create_role(
        permission=RBACInventoryPermission.HOSTS_READ,
        hbi_groups=[workspace_hosts_r_groups_rw.id],
    )
    # assign hosts:* permission to second workspace
    role_2 = rbac_apis.create_role(
        permission=RBACInventoryPermission.HOSTS_ALL, hbi_groups=[workspace_hosts_rw.id]
    )
    # assign groups:* permission to first workspace and
    # workspace only groups premissions
    role_3 = rbac_apis.create_role(
        permission=RBACInventoryPermission.GROUPS_ALL,
        hbi_groups=[workspace_hosts_r_groups_rw.id, workspace_groups_rw.id],
    )
    rbac_apis.add_roles_to_a_group([role_1, role_2, role_3], group.uuid)

    to_delete.append((group.uuid, [role.uuid for role in [role_1, role_2, role_3]]))

    yield workspace_hosts_r_groups_rw, workspace_hosts_rw, workspace_groups_rw

    for rbac_setup in to_delete:
        rbac_apis.delete_group(rbac_setup[0])
        for uuid in rbac_setup[1]:
            rbac_apis.delete_role(uuid)


@pytest.fixture(scope="class")
def setup_user_granular_hosts_all_null_permissions(
    host_inventory_frontend: ApplicationHostInventory,
    hbi_frontend_non_org_admin_user_username: str,
):
    """
    User that has hosts and groups granular access to workspaces:
        group_hosts_read: inventory:hosts:read, inventory:groups:*

    and inventory:hosts:* granular access to ungrouped hosts

    "{"resourceDefinitions":
        [{"attributeFilter":
            {"key":"group.id",
            "value":[null],
            "operation":"in"}}],
        "permission":"inventory:hosts:*"},
    """
    rbac_apis = host_inventory_frontend.apis.rbac
    to_delete: list[tuple[str, str, str, str]] = []

    # prepare workspaces that will have diffrent permissions
    workspace_hosts_r_groups_rw = host_inventory_frontend.apis.groups.create_group(
        name=generate_workspace_name(), cleanup_scope="class"
    )
    # create RBAC group and add user to it
    group = rbac_apis.create_group(permission=RBACInventoryPermission.HOSTS_READ)
    rbac_apis.add_user_to_a_group(hbi_frontend_non_org_admin_user_username, group.uuid)

    role_1 = rbac_apis.create_role(
        permission=RBACInventoryPermission.HOSTS_ALL,
        hbi_groups=[None],
    )
    role_2 = rbac_apis.create_role(
        permission=RBACInventoryPermission.HOSTS_READ,
        hbi_groups=[workspace_hosts_r_groups_rw.id],
    )
    role_3 = rbac_apis.create_role(
        permission=RBACInventoryPermission.GROUPS_ALL,
        hbi_groups=[workspace_hosts_r_groups_rw.id],
    )
    roles = [role_1, role_2, role_3]
    rbac_apis.add_roles_to_a_group(roles, group.uuid)

    to_delete.append((
        group.uuid,
        role_1.uuid,
        role_2.uuid,
        role_3.uuid,
    ))

    yield workspace_hosts_r_groups_rw

    for rbac_setup in to_delete:
        rbac_apis.delete_group(rbac_setup[0])
        rbac_apis.delete_role(rbac_setup[1])
        rbac_apis.delete_role(rbac_setup[2])
        rbac_apis.delete_role(rbac_setup[3])
