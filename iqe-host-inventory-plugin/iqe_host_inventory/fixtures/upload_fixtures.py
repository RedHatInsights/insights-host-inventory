from __future__ import annotations

import logging
import warnings
from collections.abc import Generator

import pytest
from iqe.base.application import Application
from iqe_ingress_api import IngressApi

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.deprecations import DEPRECATE_UPLOAD_CREATE_MULTIPLE_HOSTS
from iqe_host_inventory.deprecations import DEPRECATE_UPLOAD_CREATE_OR_UPDATE_EDGE_HOST
from iqe_host_inventory.deprecations import DEPRECATE_UPLOAD_CREATE_OR_UPDATE_HOST
from iqe_host_inventory.deprecations import DEPRECATE_UPLOAD_CREATE_OR_UPDATE_HOST_MODULE
from iqe_host_inventory.modeling.uploads import HostData
from iqe_host_inventory.utils.api_utils import ApiException_V4
from iqe_host_inventory.utils.api_utils import ApiException_V7
from iqe_host_inventory.utils.api_utils import async_get_multiple_hosts_by_insights_id
from iqe_host_inventory.utils.api_utils import criterion_count_eq
from iqe_host_inventory.utils.api_utils import delete_hosts
from iqe_host_inventory.utils.api_utils import get_hosts
from iqe_host_inventory.utils.datagen_utils import OperatingSystem
from iqe_host_inventory.utils.retrying import accept_when
from iqe_host_inventory.utils.upload_utils import async_multiple_uploads
from iqe_host_inventory.utils.upload_utils import build_host_archive
from iqe_host_inventory.utils.upload_utils import delete_files
from iqe_host_inventory.utils.upload_utils import get_edge_insights_qa_archive
from iqe_host_inventory.utils.upload_utils import upload
from iqe_host_inventory_api import HostQueryOutput
from iqe_host_inventory_api.api import HostsApi
from iqe_host_inventory_api.models.host_out import HostOut

logger = logging.getLogger(__name__)
MAX_RETRIES = 3


@pytest.fixture(scope="session")
def ingress_openapi_client(application: Application) -> IngressApi:
    warnings.warn(DEPRECATE_UPLOAD_CREATE_OR_UPDATE_HOST, stacklevel=2)
    # in case the env is stage_post_deploy use the user defined in the config
    if application.config.current_env == "stage_post_deploy":
        with application.copy_using(
            user=application.config.USERS.insights_qa,
            auth_type=application.config.HTTP.default_auth_type,
        ) as app:
            return app.ingress.rest_client.ingress_api
    else:
        return application.ingress.rest_client.ingress_api


# TODO: Move away from these upload fixtures (https://issues.redhat.com/browse/ESSNTL-5150)
def _upload_create_or_update_host(
    hbi_openapi_client: HostsApi,
    hbi_ingress_openapi_client: IngressApi,
    display_name: str | None = None,
    insights_id: str | None = None,
    subscription_manager_id: str | None = None,
    mac_address: str | None = None,
    bios_uuid: str | None = None,
    tags: list | None = None,
    operating_system: OperatingSystem | None = None,
    omit_data: list | None = None,
    base_archive: str | None = None,
    core_collect: bool = True,
) -> HostOut:
    warnings.warn(DEPRECATE_UPLOAD_CREATE_OR_UPDATE_HOST, stacklevel=2)
    ia = build_host_archive(
        display_name=display_name,
        insights_id=insights_id,
        subscription_manager_id=subscription_manager_id,
        mac_address=mac_address,
        bios_uuid=bios_uuid,
        tags=tags,
        operating_system=operating_system,
        omit_data=omit_data,
        base_archive=base_archive,
        core_collect=core_collect,
    )

    logger.info("Creating/Updating a host via Ingress/Puptoo")
    upload(hbi_ingress_openapi_client, ia.filename)
    delete_files([ia])  # Otherwise pipelines fail, https://issues.redhat.com/browse/IQE-2110

    logger.info("Retrieving a host via REST API")
    if omit_data and "insights_id" in omit_data:
        args = {"display_name": ia.hostname}
    else:
        args = {"insights_id": ia.insights_id}

    response = get_hosts(
        hbi_openapi_client,
        criteria=[(criterion_count_eq, 1)],
        retries=50,
        delay=0.5,
        **args,
    )
    host = response.results[0]

    return host


@pytest.fixture
def upload_create_or_update_host(
    openapi_client: HostsApi,
    ingress_openapi_client: IngressApi,
):
    warnings.warn(DEPRECATE_UPLOAD_CREATE_OR_UPDATE_HOST, stacklevel=2)

    hosts_to_delete = []
    openapi_clients = []

    def _create_host(
        display_name: str | None = None,
        insights_id: str | None = None,
        subscription_manager_id: str | None = None,
        mac_address: str | None = None,
        bios_uuid: str | None = None,
        tags: list | None = None,
        operating_system: OperatingSystem | None = None,
        omit_data: list | None = None,
        base_archive: str | None = None,
        core_collect: bool = True,
        hbi_ingress_openapi_client: IngressApi = ingress_openapi_client,
        hbi_openapi_client: HostsApi = openapi_client,
    ) -> HostOut:
        host = _upload_create_or_update_host(
            hbi_openapi_client=hbi_openapi_client,
            hbi_ingress_openapi_client=hbi_ingress_openapi_client,
            display_name=display_name,
            insights_id=insights_id,
            subscription_manager_id=subscription_manager_id,
            mac_address=mac_address,
            bios_uuid=bios_uuid,
            tags=tags,
            operating_system=operating_system,
            omit_data=omit_data,
            base_archive=base_archive,
            core_collect=core_collect,
        )
        hosts_to_delete.append(host)
        openapi_clients.append(hbi_openapi_client)
        return host

    yield _create_host

    if len(hosts_to_delete):
        for client in openapi_clients:
            delete_hosts(hosts_to_delete, client)


@pytest.fixture(scope="module")
def upload_create_or_update_host_module(
    openapi_client: HostsApi,
    ingress_openapi_client: IngressApi,
):
    warnings.warn(DEPRECATE_UPLOAD_CREATE_OR_UPDATE_HOST_MODULE, stacklevel=2)

    hosts_to_delete = []
    openapi_clients = []

    def _create_host(
        display_name: str | None = None,
        insights_id: str | None = None,
        subscription_manager_id: str | None = None,
        mac_address: str | None = None,
        bios_uuid: str | None = None,
        tags: list | None = None,
        operating_system: OperatingSystem | None = None,
        omit_data: list | None = None,
        base_archive: str | None = None,
        core_collect: bool = True,
        hbi_ingress_openapi_client: IngressApi = ingress_openapi_client,
        hbi_openapi_client: HostsApi = openapi_client,
    ) -> HostOut:
        host = _upload_create_or_update_host(
            hbi_openapi_client=hbi_openapi_client,
            hbi_ingress_openapi_client=hbi_ingress_openapi_client,
            display_name=display_name,
            insights_id=insights_id,
            subscription_manager_id=subscription_manager_id,
            mac_address=mac_address,
            bios_uuid=bios_uuid,
            tags=tags,
            operating_system=operating_system,
            omit_data=omit_data,
            base_archive=base_archive,
            core_collect=core_collect,
        )
        hosts_to_delete.append(host)
        openapi_clients.append(hbi_openapi_client)
        return host

    yield _create_host

    if len(hosts_to_delete):
        for client in openapi_clients:
            delete_hosts(hosts_to_delete, client)


def _upload_create_or_update_edge_host(
    base_archive: str,
    host_inventory_app: ApplicationHostInventory,
    hbi_ingress_openapi_client: IngressApi,
    display_name: str | None = None,
    insights_id: str | None = None,
    subscription_manager_id: str | None = None,
    mac_address: str | None = None,
    bios_uuid: str | None = None,
    tags: list | None = None,
    omit_data: list | None = None,
    core_collect: bool = True,
) -> HostOut:
    warnings.warn(DEPRECATE_UPLOAD_CREATE_OR_UPDATE_EDGE_HOST, stacklevel=2)

    ia = build_host_archive(
        display_name=display_name,
        insights_id=insights_id,
        subscription_manager_id=subscription_manager_id,
        mac_address=mac_address,
        bios_uuid=bios_uuid,
        tags=tags,
        omit_data=omit_data,
        base_archive=base_archive,
        core_collect=core_collect,
    )

    logger.info("Creating/Updating an edge host via Ingress/Puptoo")
    upload(hbi_ingress_openapi_client, ia.filename)
    delete_files([ia])  # Otherwise pipelines fail, https://issues.redhat.com/browse/IQE-2110

    logger.info("Retrieving a host via REST API")

    args = {}
    filter = "[host_type]=edge"
    if omit_data and "insights_id" in omit_data:
        args["display_name"] = ia.hostname
    else:
        args["insights_id"] = ia.insights_id

    def _get_created_host() -> HostQueryOutput:
        return host_inventory_app.apis.hosts.get_hosts_response(**args, filter=[filter])

    def _is_created(response: HostQueryOutput) -> bool:
        return response.count == 1

    api_response = accept_when(_get_created_host, _is_created, delay=0.5, retries=50)

    host = api_response.results[0]

    return host


@pytest.fixture(scope="class")
def upload_create_or_update_edge_host(
    ingress_openapi_client: IngressApi,
    host_inventory: ApplicationHostInventory,
):
    warnings.warn(DEPRECATE_UPLOAD_CREATE_OR_UPDATE_EDGE_HOST, stacklevel=2)

    hosts_to_delete = []
    host_inventory_apps = []

    def _upload_edge_host(
        display_name: str | None = None,
        insights_id: str | None = None,
        subscription_manager_id: str | None = None,
        mac_address: str | None = None,
        bios_uuid: str | None = None,
        tags: list | None = None,
        omit_data: list | None = None,
        base_archive: str | None = None,
        core_collect: bool = True,
        hbi_ingress_openapi_client: IngressApi = ingress_openapi_client,
        host_inventory_app: ApplicationHostInventory = host_inventory,
    ) -> HostOut:
        if base_archive is None:
            base_archive = get_edge_insights_qa_archive()

        host = _upload_create_or_update_edge_host(
            base_archive=base_archive,
            host_inventory_app=host_inventory_app,
            hbi_ingress_openapi_client=hbi_ingress_openapi_client,
            display_name=display_name,
            insights_id=insights_id,
            subscription_manager_id=subscription_manager_id,
            mac_address=mac_address,
            bios_uuid=bios_uuid,
            tags=tags,
            omit_data=omit_data,
            core_collect=core_collect,
        )

        hosts_to_delete.append(host.id)
        host_inventory_apps.append(host_inventory_app)

        return host

    yield _upload_edge_host

    if len(hosts_to_delete):
        for host_inventory_app in host_inventory_apps:
            host_inventory_app.apis.hosts.delete_by_id(hosts_to_delete)


def _upload_create_multiple_hosts(
    hbi_openapi_client: HostsApi,
    hbi_ingress_openapi_client: IngressApi,
    how_many: int = 3,
    hosts_data: list[dict] | None = None,
    base_archive: str | None = None,
    core_collect: bool = True,
) -> list[HostOut]:
    warnings.warn(DEPRECATE_UPLOAD_CREATE_MULTIPLE_HOSTS, stacklevel=2)

    if hosts_data:
        files = [
            build_host_archive(
                display_name=host.get("display_name"),
                operating_system=host.get("system_profile", {}).get("operating_system"),
                base_archive=base_archive,
                core_collect=core_collect,
            )
            for host in hosts_data
        ]
    else:
        files = [
            build_host_archive(base_archive=base_archive, core_collect=core_collect)
            for _ in range(how_many)
        ]

    logger.info("Creating/Updating hosts via Ingress/Puptoo")
    tries = 0
    while tries < MAX_RETRIES:
        try:
            async_multiple_uploads(hbi_ingress_openapi_client, files)
            break
        except (ApiException_V4, ApiException_V7) as a:
            if a.status in (502, 504):
                tries += 1
            else:
                raise
    hosts = async_get_multiple_hosts_by_insights_id(
        hbi_openapi_client, insights_id_list=[file.insights_id for file in files]
    )

    delete_files(files)  # Otherwise pipelines fail, https://issues.redhat.com/browse/IQE-2110
    return hosts


@pytest.fixture
def upload_create_multiple_hosts(openapi_client: HostsApi, ingress_openapi_client: IngressApi):
    warnings.warn(DEPRECATE_UPLOAD_CREATE_MULTIPLE_HOSTS, stacklevel=2)

    hosts_to_delete = []
    openapi_clients = []

    def _create_hosts(
        how_many: int = 3,
        hosts_data: list[dict] | None = None,
        base_archive: str | None = None,
        core_collect: bool = True,
        hbi_openapi_client: HostsApi = openapi_client,
        hbi_ingress_openapi_client: IngressApi = ingress_openapi_client,
    ) -> list[HostOut]:
        hosts = _upload_create_multiple_hosts(
            hbi_openapi_client=hbi_openapi_client,
            hbi_ingress_openapi_client=hbi_ingress_openapi_client,
            how_many=how_many,
            hosts_data=hosts_data,
            base_archive=base_archive,
            core_collect=core_collect,
        )
        hosts_to_delete.extend(hosts)
        openapi_clients.append(hbi_openapi_client)
        return hosts

    yield _create_hosts

    if hosts_to_delete:
        for client in openapi_clients:
            delete_hosts(hosts_to_delete, client)


@pytest.fixture(scope="module")
def hbi_setup_hosts_for_pagination(
    host_inventory: ApplicationHostInventory,
) -> Generator[list[HostOut]]:
    hosts_data = [HostData(display_name_prefix="pagination") for _ in range(20)]
    hosts = host_inventory.upload.create_hosts(hosts_data=hosts_data, register_for_cleanup=False)
    yield hosts

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory.apis.hosts.delete_by_id(hosts)


@pytest.fixture
def hbi_upload_prepare_host(host_inventory: ApplicationHostInventory) -> Generator[HostOut]:
    host = host_inventory.upload.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory.apis.hosts.delete_by_id(host)


@pytest.fixture(scope="class")
def hbi_upload_prepare_host_class(host_inventory: ApplicationHostInventory) -> Generator[HostOut]:
    host = host_inventory.upload.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory.apis.hosts.delete_by_id(host)


@pytest.fixture(scope="module")
def hbi_upload_prepare_host_module(host_inventory: ApplicationHostInventory) -> Generator[HostOut]:
    host = host_inventory.upload.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory.apis.hosts.delete_by_id(host)


@pytest.fixture
def hbi_secondary_upload_prepare_host(
    host_inventory_secondary: ApplicationHostInventory,
) -> Generator[HostOut]:
    host = host_inventory_secondary.upload.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory_secondary.apis.hosts.delete_by_id(host)


@pytest.fixture(scope="class")
def hbi_secondary_upload_prepare_host_class(
    host_inventory_secondary: ApplicationHostInventory,
) -> Generator[HostOut]:
    host = host_inventory_secondary.upload.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory_secondary.apis.hosts.delete_by_id(host)


@pytest.fixture(scope="module")
def hbi_secondary_upload_prepare_host_module(
    host_inventory_secondary: ApplicationHostInventory,
) -> Generator[HostOut]:
    host = host_inventory_secondary.upload.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory_secondary.apis.hosts.delete_by_id(host)


@pytest.fixture()
def hbi_cert_auth_upload_prepare_host(
    host_inventory_cert_auth: ApplicationHostInventory,
) -> Generator[HostOut]:
    host = host_inventory_cert_auth.upload.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory_cert_auth.apis.hosts.delete_by_id(host)


@pytest.fixture(scope="class")
def hbi_cert_auth_upload_prepare_host_class(
    host_inventory_cert_auth: ApplicationHostInventory,
) -> Generator[HostOut]:
    host = host_inventory_cert_auth.upload.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory_cert_auth.apis.hosts.delete_by_id(host)


@pytest.fixture(scope="module")
def hbi_cert_auth_upload_prepare_host_module(
    host_inventory_cert_auth: ApplicationHostInventory,
) -> Generator[HostOut]:
    host = host_inventory_cert_auth.upload.create_host(register_for_cleanup=False)
    yield host

    # Explicit cleanup needed if this fixture is used by other plugins
    host_inventory_cert_auth.apis.hosts.delete_by_id(host)
