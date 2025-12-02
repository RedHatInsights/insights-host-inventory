import logging

import pytest
from iqe.base.application import Application

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.uploads import HostData
from iqe_host_inventory.utils.datagen_utils import generate_display_name

logger = logging.getLogger(__name__)


CATCHPOINT_RHEL_ARCHIVE = "rhel-82-vuln-patch-advisor.tar.gz"


@pytest.fixture(scope="session", autouse=True)
def setup_ui_hosts_for_catchpoint(
    application: Application,
    host_inventory_frontend: ApplicationHostInventory,
) -> None:
    """Catchpoint tests (outage tests for Frontend integrated with Status page)
    run via Catchpoint monitoring tool:
    - if account without required hosts - this fixture uploads them with
    'register_for_cleanup=False' param to keep them in the account
    - if account has required hosts - it updates them to keep their staleness "fresh"
    to avoid deletion.

    https://issues.redhat.com/browse/RHINENG-16391
    """
    if application.config.current_env != "prod":
        logger.info(
            "Hosts for Catchpoint required only for prod environment, "
            "skipping hosts update/upload."
        )
        return

    unique_id = "_catchpoint"
    hosts_data: list = []
    hosts = host_inventory_frontend.apis.hosts.get_hosts(display_name=unique_id)
    if len(hosts) != 0:
        for host in hosts:
            hosts_data.append(
                HostData(
                    display_name=host.display_name,
                    subscription_manager_id=host.subscription_manager_id,
                    tags=[],
                    base_archive=CATCHPOINT_RHEL_ARCHIVE,
                )
            )
    else:
        # if no Catchpoint hosts in the account - create new host_data to upload
        for _ in range(3):
            hosts_data.append(
                HostData(
                    display_name=generate_display_name() + unique_id,
                    tags=[],
                    base_archive=CATCHPOINT_RHEL_ARCHIVE,
                )
            )

    host_inventory_frontend.upload.create_hosts(hosts_data=hosts_data, register_for_cleanup=False)
