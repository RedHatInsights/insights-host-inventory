# mypy: disallow-untyped-defs

import logging
import multiprocessing
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cached_property

import attr
from iqe.base.modeling import BaseEntity
from iqe.utils.archive_memory import InsightsArchiveInMemory
from iqe_ingress_api import IngressApi

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.hosts_api import HostsAPIWrapper
from iqe_host_inventory.utils.datagen_utils import OperatingSystem
from iqe_host_inventory.utils.datagen_utils import TagDict
from iqe_host_inventory.utils.upload_utils import build_host_archive
from iqe_host_inventory.utils.upload_utils import delete_files
from iqe_host_inventory_api import HostOut

logger = logging.getLogger(__name__)

_FILE_TYPE = "application/vnd.redhat.advisor.payload+tgz"

HOSTS_NOT_CREATED_ERROR = Exception("Some hosts were not created")


@dataclass
class HostData:
    """Used in 'create_hosts' method"""

    display_name: str | None = None
    display_name_prefix: str = "hbiqe"
    insights_id: str | None = None
    subscription_manager_id: str | None = None
    mac_address: str | None = None
    tags: list[TagDict] | None = None
    operating_system: OperatingSystem | None = None
    base_archive: str | None = None
    archive_repo: str = "ingress"
    core_collect: bool = True


def _build_archives_from_data(hosts_data: list[HostData]) -> list[InsightsArchiveInMemory]:
    return [
        build_host_archive(
            display_name=host_data.display_name,
            name_prefix=host_data.display_name_prefix,
            insights_id=host_data.insights_id,
            subscription_manager_id=host_data.subscription_manager_id,
            mac_address=host_data.mac_address,
            tags=host_data.tags,
            operating_system=host_data.operating_system,
            base_archive=host_data.base_archive,
            archive_repo=host_data.archive_repo,
            core_collect=host_data.core_collect,
        )
        for host_data in hosts_data
    ]


def _find_host_by_insights_id(hosts: list[HostOut], insights_id: str) -> HostOut:
    matching_hosts = [host for host in hosts if host.insights_id == insights_id]

    if len(matching_hosts) != 1:
        raise ValueError(
            f"Expected exactly one matching host message with insights_id == {insights_id}, "
            f"found {len(matching_hosts)}"
        )

    return matching_hosts[0]


def _sort_hosts_by_insights_ids(insights_ids: list[str], hosts: list[HostOut]) -> list[HostOut]:
    """When we upload multiple archives asynchronously the hosts will get created in seemingly
    random order. This function is used to ensure that the order of the returned created hosts will
    match the order of the input data (represented by the order of input insights_ids)."""
    if len(insights_ids) != len(hosts):
        raise ValueError(
            f"Number of insights IDs is different than number of hosts: "
            f"{len(insights_ids)} != {len(hosts)}"
        )

    sorted_hosts = []
    for insights_id in insights_ids:
        sorted_hosts.append(_find_host_by_insights_id(hosts, insights_id))

    return sorted_hosts


@attr.s
class HBIUploads(BaseEntity):
    @cached_property
    def _host_inventory(self) -> ApplicationHostInventory:
        return self.application.host_inventory

    @cached_property
    def _ingress_api(self) -> IngressApi:
        return self.application.ingress.rest_client.ingress_api

    @cached_property
    def _hosts_api(self) -> HostsAPIWrapper:
        return self._host_inventory.apis.hosts

    @contextmanager
    def async_ingress(self) -> Generator[None, None, None]:
        """Set the number of upload threads to match the number of available CPUs."""
        self._ingress_api.api_client.pool_threads = multiprocessing.cpu_count()
        yield
        self._ingress_api.api_client.pool_threads = 1

    def upload_archive(
        self,
        *,
        display_name: str | None = None,
        display_name_prefix: str = "hbiqe",
        insights_id: str | None = None,
        subscription_manager_id: str | None = None,
        mac_address: str | None = None,
        tags: list[TagDict] | None = None,
        operating_system: OperatingSystem | None = None,
        base_archive: str | None = None,
        archive_repo: str = "ingress",
        core_collect: bool = True,
    ) -> InsightsArchiveInMemory:
        """Create a new host by uploading an insights archive to ingress.

        :param str display_name: This will update the FQDN in the insights archive. When a host
            is created via puptoo, the display name is always set to match the FQDN, so you can
            set the display name via this parameter.
            Default: random string
        :param str display_name_prefix: If 'display_name' parameter is not set, the host's FQDN
            will use this prefix + random string.
            Default: "hbiqe"
        :param str insights_id: Set the host's Insights ID.
            Default: random UUID
        :param str subscription_manager_id: Set the host's Subscription Manager ID.
            Default: random UUID
        :param str mac_address: Set the host's MAC address.
            Default: random MAC address
        :param list[TagDict] tags: Set the host's tags.
            Default: 5 random tags
        :param OperatingSystem operating_system: Set the host's operating system.
            Default: RHEL 8.7
        :param str base_archive: Name of the pre-collected insights archive file to be used as a
            base for the new host.
            Default: "rhel87_core_collect.tar.gz"
        :param str archive_repo: IQE plugin where we can find the 'base_archive' file
            Default: "ingress" (iqe-ingress-plugin)
        :param bool core_collect: Whether the archive structure should follow the newer core
            collection style.
            Default: True
        :return InsightsArchiveInMemory: The uploaded insights archive
        """
        logger.info("Creating/Updating a host via Ingress/Puptoo")
        archive = build_host_archive(
            display_name=display_name,
            name_prefix=display_name_prefix,
            insights_id=insights_id,
            subscription_manager_id=subscription_manager_id,
            mac_address=mac_address,
            tags=tags,
            operating_system=operating_system,
            base_archive=base_archive,
            archive_repo=archive_repo,
            core_collect=core_collect,
        )
        self._ingress_api.upload_post(
            file=archive.filename, content_type=_FILE_TYPE, _preload_content=False
        )
        return archive

    def async_upload_archives(self, archives: list[InsightsArchiveInMemory]) -> None:
        """Create multiple new hosts by uploading insights archives to ingress asynchronously.

        :param list[InsightsArchiveInMemory] archives: (Required) List of archives to be uploaded.
        :return None
        """
        logger.info("Creating/Updating hosts via Ingress/Puptoo")
        with self.async_ingress():
            threads = []
            for archive in archives:
                thread = self._ingress_api.upload_post(
                    file=archive.filename,
                    content_type=_FILE_TYPE,
                    _preload_content=False,
                    async_req=True,
                )
                threads.append(thread)

            for thread in threads:
                thread.get()

    def create_host(
        self,
        *,
        display_name: str | None = None,
        display_name_prefix: str = "hbiqe",
        insights_id: str | None = None,
        subscription_manager_id: str | None = None,
        mac_address: str | None = None,
        tags: list[TagDict] | None = None,
        operating_system: OperatingSystem | None = None,
        base_archive: str | None = None,
        archive_repo: str = "ingress",
        core_collect: bool = True,
        register_for_cleanup: bool = True,
        cleanup_scope: str = "function",
    ) -> HostOut:
        """Create a new host by uploading an insights archive to ingress and wait for the host to
            be retrievable via API.

        :param str display_name: This will update the FQDN in the insights archive. When a host
            is created via puptoo, the display name is always set to match the FQDN, so you can
            set the display name via this parameter.
            Default: random string
        :param str display_name_prefix: If 'display_name' parameter is not set, the host's FQDN
            will use this prefix + random string.
            Default: "hbiqe"
        :param str insights_id: Set the host's Insights ID.
            Default: random UUID
        :param str subscription_manager_id: Set the host's Subscription Manager ID.
            Default: random UUID
        :param str mac_address: Set the host's MAC address.
            Default: random MAC address
        :param list[TagDict] tags: Set the host's tags.
            Default: 5 random tags
        :param OperatingSystem operating_system: Set the host's operating system.
            Default: RHEL 8.7
        :param str base_archive: Name of the pre-collected insights archive file to be used as a
            base for the new host.
            Default: "rhel87_core_collect.tar.gz"
        :param str archive_repo: IQE plugin where we can find the 'base_archive' file
            Default: "ingress" (iqe-ingress-plugin)
        :param bool core_collect: Whether the archive structure should follow the newer core
            collection style.
            Default: True
        :param bool register_for_cleanup: If True, the new host will be registered for a cleanup.
            Default: True
        :param str cleanup_scope: The scope to use for cleanup.
            Possible values: "function", "class", "module", "package", "session"
            Default: "function"
        :return HostOut: Created host (extracted from the response from GET /hosts)
        """
        archive = self.upload_archive(
            display_name=display_name,
            display_name_prefix=display_name_prefix,
            insights_id=insights_id,
            subscription_manager_id=subscription_manager_id,
            mac_address=mac_address,
            tags=tags,
            operating_system=operating_system,
            base_archive=base_archive,
            archive_repo=archive_repo,
            core_collect=core_collect,
        )
        delete_files([archive])

        # REVISIT: This is currently needed for Kessel
        logger.info("Waiting for the host to be retrievable via REST API: GET /host_exists")
        host_ids = self._hosts_api.wait_for_host_exists([archive.insights_id])
        assert len(host_ids) == 1, (
            f"Expected exactly one host to be created, got {len(host_ids)}: {host_ids}"
        )

        logger.info("Waiting for the host to be retrievable via REST API: GET /hosts")
        hosts = self._host_inventory.apis.hosts.wait_for_created_by_filters(
            insights_id=archive.insights_id
        )
        assert len(hosts) == 1, (
            f"Expected exactly one host to be created, got {len(hosts)}: {hosts}"
        )

        logger.info("Waiting for the host to be retrievable via REST API: GET /hosts/<host_id>")
        self._hosts_api.wait_for_created(hosts)

        if register_for_cleanup:
            self._host_inventory.cleanup.add_hosts(hosts, scope=cleanup_scope)

        return hosts[0]

    def create_hosts(
        self,
        n: int | None = None,
        *,
        hosts_data: list[HostData] | None = None,
        register_for_cleanup: bool = True,
        cleanup_scope: str = "function",
    ) -> list[HostOut]:
        """Create multiple new hosts by uploading insights archives to ingress asynchronously and
            wait for the hosts to be retrievable via API. At least one of 'n' or 'hosts_data' must
            be provided. If both are provided, then length of 'hosts_data' must be equal to 'n'.

        :param int n: Number of hosts to create. If 'hosts_data' is not provided, then the hosts
            will have random data.
        :param list[HostData] hosts_data: List of host data to be used for hosts creation.
        :param bool register_for_cleanup: If True, the new host will be registered for a cleanup.
            Default: True
        :param str cleanup_scope: The scope to use for cleanup.
            Possible values: "function", "class", "module", "package", "session"
            Default: "function"
        :return list[HostOut]: Created hosts (extracted from the response from GET /hosts)
        """
        if n is None and hosts_data is None:
            raise ValueError("At least one of 'n' or 'hosts_data' must be provided")

        if hosts_data is not None:
            if n is not None and len(hosts_data) != n:
                raise ValueError(
                    f"Requested number of hosts doesn't match hosts_data: {n} != {len(hosts_data)}"
                )
            archives = _build_archives_from_data(hosts_data)
        else:
            archives = [build_host_archive() for _ in range(n)]  # type: ignore[arg-type]

        self.async_upload_archives(archives)

        insights_ids = [archive.insights_id for archive in archives]

        # REVISIT: This is currently needed for Kessel
        logger.info("Waiting for the hosts to be retrievable via REST API: GET /host_exists")
        response_host_ids = self._hosts_api.wait_for_host_exists(insights_ids)
        if len(response_host_ids) != len(insights_ids):
            raise HOSTS_NOT_CREATED_ERROR

        logger.info("Waiting for the hosts to be retrievable via REST API: GET /hosts")
        response_hosts = self._hosts_api.async_wait_for_created_by_insights_ids(insights_ids)
        delete_files(archives)
        if len(response_hosts) != len(insights_ids):
            raise HOSTS_NOT_CREATED_ERROR

        logger.info("Waiting for the hosts to be retrievable via REST API: GET /hosts/<host_id>")
        self._hosts_api.wait_for_created(response_hosts)

        if register_for_cleanup:
            self._host_inventory.cleanup.add_hosts(response_hosts, scope=cleanup_scope)

        return _sort_hosts_by_insights_ids(insights_ids, response_hosts)
