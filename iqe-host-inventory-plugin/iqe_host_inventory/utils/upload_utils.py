from __future__ import annotations

import json
import logging
import multiprocessing
import os
import warnings
from collections.abc import Sequence
from os import getenv
from os import remove
from os.path import isfile

from iqe.utils.archive import InsightsArchive
from iqe.utils.archive import get_insights_archive
from iqe.utils.archive_memory import InsightsArchiveInMemory
from iqe.utils.plugins import plugin_path

from iqe_host_inventory.deprecations import DEPRECATE_ASYNC_MULTIPLE_UPLOADS
from iqe_host_inventory.deprecations import DEPRECATE_UPLOAD
from iqe_host_inventory.utils.datagen_utils import OperatingSystem
from iqe_host_inventory.utils.datagen_utils import TagDict
from iqe_host_inventory.utils.datagen_utils import gen_tag
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.datagen_utils import get_default_operating_system
from iqe_host_inventory.utils.datagen_utils import get_operating_system_string

logger = logging.getLogger(__name__)


EDGE_STAGE_INVENTORY_ACCOUNT_ARCHIVE = "edge_stage_inventory_rhel95.tar.gz"
EDGE_PROD_INVENTORY_ACCOUNT_ARCHIVE = "edge_prod_inventory_rhel95.tar.gz"
EDGE_STAGE_INSIGHTS_QA_ARCHIVE = "new_edge_device_85.tar.gz"
IMAGE_MODE_ARCHIVE = "image-mode-rhel94.tar.gz"

TAGS_METADATA = {
    "name": "insights.specs.Specs.tags",
    "exec_time": 1,
    "errors": [],
    "results": {
        "type": "insights.core.spec_factory.DatasourceProvider",
        "object": {"relative_path": "tags.json", "save_as": None},
    },
    "ser_time": 1,
}


def get_default_rhel_archive() -> str:
    return "rhel94_core_collect.tar.gz"


def get_default_centos_archive() -> str:
    return "centos79.tar.gz"


def get_edge_inventory_account_archive() -> str:
    if "prod" in getenv("ENV_FOR_DYNACONF", "").lower():
        return EDGE_PROD_INVENTORY_ACCOUNT_ARCHIVE
    return EDGE_STAGE_INVENTORY_ACCOUNT_ARCHIVE


def get_edge_insights_qa_archive() -> str:
    return EDGE_STAGE_INSIGHTS_QA_ARCHIVE


def get_archive_and_collect_method(os_name: str = "RHEL") -> tuple[str, bool]:
    """Returns base_archive name and core_collect flag, based on operating_system"""
    if "centos" in os_name.lower():
        base_archive = get_default_centos_archive()
        core_collect = False
    else:
        base_archive = get_default_rhel_archive()
        core_collect = True
    return base_archive, core_collect


def async_multiple_uploads(ingress_openapi_client, files: list[InsightsArchiveInMemory]):
    warnings.warn(DEPRECATE_ASYNC_MULTIPLE_UPLOADS, stacklevel=2)

    file_type = "application/vnd.redhat.advisor.payload+tgz"

    ingress_openapi_client.api_client.pool_threads = multiprocessing.cpu_count()

    threads = []
    for file in files:
        thread = ingress_openapi_client.upload_post(
            file=file.filename, content_type=file_type, async_req=True, _preload_content=False
        )
        threads.append(thread)

    for thread in threads:
        thread.get()

    ingress_openapi_client.api_client.pool_threads = 1


def upload(ingress_openapi_client, filename):
    warnings.warn(DEPRECATE_UPLOAD, stacklevel=2)

    file_type = "application/vnd.redhat.advisor.payload+tgz"

    return ingress_openapi_client.upload_post(
        file=filename,
        content_type=file_type,
        _preload_content=False,
    )


def build_host_archive(
    display_name: str | None = None,
    insights_id: str | None = None,
    subscription_manager_id: str | None = None,
    mac_address: str | None = None,
    bios_uuid: str | None = None,  # Doesn't work, see below
    tags: list[TagDict] | None = None,
    omit_data: list[str] | None = None,
    base_archive: str | None = None,
    archive_repo: str | None = None,
    operating_system: OperatingSystem | None = None,
    name_prefix: str | None = None,
    core_collect: bool = True,
) -> InsightsArchiveInMemory:
    omit_data = omit_data or []
    display_name = (
        display_name or generate_display_name(name_prefix or "hbiqe")
        if "display_name" not in omit_data
        else None
    )
    insights_id = insights_id or generate_uuid()
    subscription_manager_id = subscription_manager_id or generate_uuid()
    tags = tags if tags is not None else [gen_tag() for _ in range(5)]
    operating_system = operating_system or get_default_operating_system()
    os_string = get_operating_system_string(operating_system)

    if not base_archive:
        base_archive = get_default_rhel_archive()
    if not archive_repo:
        archive_repo = "ingress"

    base_archive_file_path = get_upload_file_path(base_archive, archive_repo)

    ia: InsightsArchiveInMemory = get_insights_archive(
        filename=base_archive_file_path,
        in_memory=True,
        dump=True,
        hostname=display_name,
        insights_id=insights_id,
        subscription_manager_id=subscription_manager_id,
        mac_address=mac_address,
        machine_id=insights_id,
        operating_system=os_string,
        core_collect_default_structure=core_collect,
    )

    if "subscription_manager_id" not in omit_data:
        subscription_manager_id = f"system identity: {subscription_manager_id}"
        _add_file_to_archive(
            ia, "/insights_commands/subscription-manager_identity", subscription_manager_id
        )

    if "tags" not in omit_data:
        _add_file_to_archive(
            ia, "/meta_data/insights.specs.Specs.tags.json", json.dumps(TAGS_METADATA)
        )
        _add_file_to_archive(ia, "tags.json", json.dumps(tags))

    # WARNING: This doesn't work, because we need to also update different files in the archive.
    # There are 2 places in `insights_commands/dmidecode` which need to be updated:
    # - UUID and Serial Number
    # https://issues.redhat.com/browse/RHINENG-9652
    if "bios_uuid" not in omit_data and bios_uuid:
        logger.warning("Setting bios_uuid doesn't work: RHINENG-9652")
        _add_file_to_archive(ia, "/insights_commands/dmidecode_-s_system-uuid", bios_uuid)

    if "insights_id" in omit_data:
        ia.removefile("/etc/redhat-access-insights/machine-id")
        ia.removefile("/etc/insights-client/machine-id")

    if "display_name" in omit_data:
        ia.removefile("/insights_commands/hostname_-f")
        ia.removefile("/insights_commands/hostname")

    if base_archive == "sap_core_collect.tar.gz":
        ia.add_sids(["HBI"])

    return ia


def delete_files(files_to_delete: Sequence[InsightsArchive | InsightsArchiveInMemory | str]):
    file_names = [ia if isinstance(ia, str) else ia.filename for ia in files_to_delete]
    logger.info(f"Deleting files: {file_names}")
    for file_name in file_names:
        if file_name and isfile(file_name):
            remove(file_name)


def get_upload_file_path(tarball_name, plugin_name="ingress"):
    upload_root_dir = plugin_path(f"iqe_{plugin_name}")

    possible_archives_paths = [
        ("resources", "archives"),
        ("data", "archives"),
        ("archives",),
        ("data", "inventory", "static"),
        ("data",),
    ]
    for path in possible_archives_paths:
        if os.path.exists(os.path.join(upload_root_dir, *path, tarball_name)):
            return os.path.join(upload_root_dir, *path, tarball_name)

    for root, dirs, _ in os.walk(upload_root_dir):
        for dir_name in dirs:
            if dir_name == "archives" and os.path.exists(
                os.path.join(root, dir_name, tarball_name)
            ):
                return os.path.join(root, dir_name, tarball_name)

    raise AttributeError(
        f"Requested base archive '{tarball_name}' wasn't found in '{plugin_name}' plugin"
    )


def _add_file_to_archive(archive, filepath, value):
    if isinstance(archive, InsightsArchive):
        archive.addfile(filepath, contents=value)
    else:
        archive.addfile({filepath: value})
