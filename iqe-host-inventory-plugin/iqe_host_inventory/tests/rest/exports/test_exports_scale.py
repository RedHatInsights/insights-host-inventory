# mypy: disallow-untyped-defs

import logging
from time import sleep

import pytest

from iqe_host_inventory import ApplicationHostInventory

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


def test_export_hosts_large_inventory(host_inventory_secondary: ApplicationHostInventory) -> None:
    """
    Perform an export on an account known to have a large inventory like
    insights-qa

    We're mainly concerned about a successful completion of an export here.
    We can't reliably compare the host count with the exported count since
    it's a shared account and host counts might fluctuate between the GET /hosts
    and export processing. We'll log the counts for informational purposes.

    Jira: https://issues.redhat.com/browse/RHINENG-11833

    metadata:
      requirements: inv-export-hosts
      assignee: msager
      importance: high
      title: Export a large inventory
    """
    host_cnt = host_inventory_secondary.apis.hosts.get_hosts_response().total
    logger.info(f"There are currently {host_cnt} hosts in this account")

    # For the insights-qa account (currently ~5k hosts), an export has been
    # taking about 15-20 seconds.  The account size and load will fluctuate,
    # but let's see if a 1 minute cap will be reliable.
    export_id = host_inventory_secondary.apis.exports.create_export(
        wait_for_completion=True, retries=60, delay=1
    )

    status = host_inventory_secondary.apis.exports.get_export_status(export_id)
    logger.info(
        f"The export took {(status.completed_at - status.created_at).total_seconds()} seconds to complete"  # noqa
    )

    path = host_inventory_secondary.apis.exports.download_export(export_id)
    report = host_inventory_secondary.apis.exports.fetch_export_data(path)

    logger.info(f"Successfully exported {len(report)} hosts")

    # For now, let's allow a 5% discrepancy.  I'm guessing we'll be able to
    # reduce this to a much smaller margin, but let's see how things go.
    assert abs(host_cnt - len(report)) / host_cnt < 0.05


def test_export_hosts_add_hosts_during_export(
    host_inventory_secondary: ApplicationHostInventory,
) -> None:
    """
    Perform an export and then add some hosts while the export is in-progress.
    The added hosts should not be part of the export.  Use a large account so
    that the export takes enough time for us to add hosts.

    metadata:
      requirements: inv-export-hosts
      assignee: msager
      importance: medium
      title: Add some hosts with an export in-progress
    """
    export_id = host_inventory_secondary.apis.exports.create_export(wait_for_completion=False)

    status = host_inventory_secondary.apis.exports.get_export_status(export_id).status
    assert status in ("pending", "running")

    # With a large enough inventory, we encounter timing issues.  It seems HBI's
    # retrieval of data from the db is still in-progress while the adds occur
    # (adds of these hosts might occur first).  A short delay seems to suffice.
    sleep(3)
    hosts = host_inventory_secondary.upload.create_hosts(3)

    host_inventory_secondary.apis.exports.wait_for_completion(export_id, retries=60, delay=1)

    path = host_inventory_secondary.apis.exports.download_export(export_id)
    report = host_inventory_secondary.apis.exports.fetch_export_data(path)
    converted_report = host_inventory_secondary.apis.exports.convert_export_report(report)

    assert all(host.id not in converted_report for host in hosts)


def test_export_hosts_delete_hosts_during_export(
    host_inventory_secondary: ApplicationHostInventory,
) -> None:
    """
    Perform an export and then delete some hosts while the export is in-progress.
    The deleted hosts should be part of the export.  Use a large account so that
    the export takes enough time for us to delete hosts.

    metadata:
      requirements: inv-export-hosts
      assignee: msager
      importance: medium
      title: Delete some hosts with an export in-progress
    """
    hosts = host_inventory_secondary.upload.create_hosts(3)

    export_id = host_inventory_secondary.apis.exports.create_export(wait_for_completion=False)

    status = host_inventory_secondary.apis.exports.get_export_status(export_id).status
    assert status in ("pending", "running")

    # With a large enough inventory, we encounter timing issues.  It seems HBI's
    # retrieval of data from the db is still in-progress while the deletes occur
    # (deletes of these hosts might occur first).  A short delay seems to suffice.
    sleep(3)
    host_inventory_secondary.apis.hosts.delete_by_id(hosts)

    host_inventory_secondary.apis.exports.wait_for_completion(export_id, retries=60, delay=1)

    path = host_inventory_secondary.apis.exports.download_export(export_id)
    report = host_inventory_secondary.apis.exports.fetch_export_data(path)
    converted_report = host_inventory_secondary.apis.exports.convert_export_report(report)

    assert all(host.id in converted_report for host in hosts)
