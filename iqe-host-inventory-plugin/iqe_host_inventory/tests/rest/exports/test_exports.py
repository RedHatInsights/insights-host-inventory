# mypy: disallow-untyped-defs

import logging
from time import sleep

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.fixtures.exports_fixtures import ExportResources
from iqe_host_inventory.modeling.uploads import HostData
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.staleness_utils import create_hosts_fresh_stale_stalewarning_culled
from iqe_host_inventory.utils.upload_utils import get_archive_and_collect_method

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


@pytest.mark.ephemeral
class TestExports:
    def test_export_hosts_json_format(
        self, host_inventory: ApplicationHostInventory, exports_setup_resources: ExportResources
    ) -> None:
        """
        Perform an export specifying json format

        metadata:
          requirements: inv-export-hosts
          assignee: msager
          importance: high
          title: Export hosts to json
        """
        hosts = exports_setup_resources.hosts
        report = host_inventory.apis.exports.export_hosts()
        host_inventory.apis.exports.validate_export_report(hosts, report)

    def test_export_hosts_csv_format(
        self, host_inventory: ApplicationHostInventory, exports_setup_resources: ExportResources
    ) -> None:
        """
        Perform an export specifying csv format

        metadata:
          requirements: inv-export-hosts
          assignee: msager
          importance: high
          title: Export hosts to csv
        """
        format = "csv"
        hosts = exports_setup_resources.hosts
        report = host_inventory.apis.exports.export_hosts(format=format)
        host_inventory.apis.exports.validate_export_report(hosts, report, format=format)

    def test_export_hosts_add_reexport(
        self, host_inventory: ApplicationHostInventory, exports_setup_resources: ExportResources
    ) -> None:
        """
        Perform an export, add some hosts, re-export, and verify that the new
        hosts are included

        metadata:
          requirements: inv-export-hosts
          assignee: msager
          importance: high
          title: Export, then add hosts, then export again
        """
        hosts = exports_setup_resources.hosts
        report = host_inventory.apis.exports.export_hosts()
        host_inventory.apis.exports.validate_export_report(hosts, report)

        new_hosts = host_inventory.kafka.create_random_hosts(10)
        expected_host_ids = [host.id for host in hosts + new_hosts]
        # Get the HostOut objects from the API to avoid using HostWrapper objects
        new_hosts_from_api = host_inventory.apis.hosts.get_hosts_by_id(new_hosts)

        report = host_inventory.apis.exports.export_hosts()
        host_ids = host_inventory.apis.exports.validate_export_report(
            hosts + new_hosts_from_api,
            report,
        ).keys()

        assert sorted(host_ids) == sorted(expected_host_ids)

    def test_export_hosts_delete_reexport(
        self, host_inventory: ApplicationHostInventory, exports_setup_resources: ExportResources
    ) -> None:
        """
        Perform an export, delete some hosts, re-export, and verify that the deleted
        hosts are not included

        metadata:
          requirements: inv-export-hosts
          assignee: msager
          importance: high
          title: Export hosts, then delete hosts, then export again
        """
        hosts = exports_setup_resources.hosts
        expected_host_ids = [host.id for host in hosts]

        new_hosts = host_inventory.kafka.create_random_hosts(10)
        # Get the HostOut objects from the API to avoid using HostWrapper objects
        new_hosts_from_api = host_inventory.apis.hosts.get_hosts_by_id(new_hosts)

        report = host_inventory.apis.exports.export_hosts()
        host_inventory.apis.exports.validate_export_report(hosts + new_hosts_from_api, report)

        host_inventory.apis.hosts.delete_by_id(new_hosts)

        report = host_inventory.apis.exports.export_hosts()
        host_ids = host_inventory.apis.exports.validate_export_report(hosts, report).keys()

        assert sorted(host_ids) == sorted(expected_host_ids)

    def test_export_hosts_proper_account(
        self,
        host_inventory: ApplicationHostInventory,
        host_inventory_secondary: ApplicationHostInventory,
        exports_setup_resources: ExportResources,
    ) -> None:
        """
        Verify that only hosts from the proper account are exported.

        metadata:
          requirements: inv-export-hosts
          assignee: msager
          importance: critical
          title: Verify exported hosts are from the proper account
        """
        hosts = exports_setup_resources.hosts

        secondary_hosts = host_inventory_secondary.kafka.create_random_hosts(10, timeout=30)
        secondary_host_ids = [host.id for host in secondary_hosts]

        report = host_inventory.apis.exports.export_hosts()
        assert len(report) == len(hosts)

        host_ids = host_inventory.apis.exports.convert_export_report(report).keys()
        assert set(host_ids) & set(secondary_host_ids) == set()


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_export_hosts_mixed_states(host_inventory: ApplicationHostInventory) -> None:
    """
    Perform an export in which hosts are in various states of staleness

    metadata:
      requirements: inv-export-hosts
      assignee: msager
      importance: high
      title: Export hosts that are in various staleness states
    """
    fresh_hosts_data = host_inventory.datagen.create_n_hosts_data(2)
    stale_hosts_data = host_inventory.datagen.create_n_hosts_data(2)
    stale_warning_hosts_data = host_inventory.datagen.create_n_hosts_data(2)
    culled_hosts_data = host_inventory.datagen.create_n_hosts_data(2)

    hosts = create_hosts_fresh_stale_stalewarning_culled(
        host_inventory,
        fresh_hosts_data,
        stale_hosts_data,
        stale_warning_hosts_data,
        culled_hosts_data,
        deltas=(30, 60, 90),
    )

    fresh_hosts_ids = {host.id for host in hosts["fresh"]}
    stale_hosts_ids = {host.id for host in hosts["stale"]}
    stale_warning_hosts_ids = {host.id for host in hosts["stale_warning"]}
    culled_hosts_ids = {host.id for host in hosts["culled"]}

    sleep(3)  # Probably not needed, but just in case...

    # Verify the culled hosts are no longer available
    with raises_apierror(404):
        host_inventory.apis.hosts.get_hosts_by_id(culled_hosts_ids)

    report = host_inventory.apis.exports.export_hosts()
    processed_report = host_inventory.apis.exports.convert_export_report(report)

    assert all(processed_report[host_id]["state"] == "fresh" for host_id in fresh_hosts_ids)

    assert all(processed_report[host_id]["state"] == "stale" for host_id in stale_hosts_ids)

    assert all(
        processed_report[host_id]["state"] == "stale warning"
        for host_id in stale_warning_hosts_ids
    )

    assert all(host_id not in processed_report for host_id in culled_hosts_ids)


@pytest.mark.parametrize("operating_system", ["RHEL", "CentOS Linux"])
@pytest.mark.parametrize("export_format", ["json", "csv"])
def test_export_uploaded_hosts(
    host_inventory: ApplicationHostInventory, operating_system: str, export_format: str
) -> None:
    """
    Almost all export tests will run in the ephemeral environment.  This test
    is an exception so that we have some basic coverage in Stage and Prod
    environments.

    IMPORTANT: This test deletes all hosts in the account and shouldn't be run
    locally when one of the pipelines is running or it will impact the pipeline
    results.  It could also lead to unexpected results locally if a pipeline
    test creates hosts in-between the delete_all and the export.

    metadata:
      requirements: inv-export-hosts
      assignee: msager
      importance: high
      title: Upload hosts and export them via POST /exports request
    """
    host_inventory.apis.hosts.confirm_delete_all()

    group = host_inventory.apis.groups.create_group(generate_display_name())

    base_archive, core_collect = get_archive_and_collect_method(operating_system)
    hosts_data = [HostData(base_archive=base_archive, core_collect=core_collect) for _ in range(3)]
    hosts = host_inventory.upload.create_hosts(hosts_data=hosts_data)
    host_inventory.apis.groups.add_hosts_to_group(group=group, hosts=hosts)

    # Need to retrieve the hosts again since host.updated will change after
    # hosts are added to a group:
    #     https://issues.redhat.com/browse/RHINENG-11171
    hosts = host_inventory.apis.hosts.get_hosts_by_id(hosts)

    report = host_inventory.apis.exports.export_hosts(format=export_format)
    host_inventory.apis.exports.validate_export_report(hosts, report, format=export_format)


@pytest.mark.parametrize("export_format", ["json", "csv"])
@pytest.mark.ephemeral
def test_export_hosts_unicode_char(
    host_inventory: ApplicationHostInventory, export_format: str
) -> None:
    """
    Perform an export when a host has special unicode characters.

    This test is in direct response to a bug, in which a csv export failed due to
    character \u201c (left double quote) in the host data.

    Jira: https://issues.redhat.com/browse/RHINENG-15180

    metadata:
      requirements: inv-export-hosts
      assignee: msager
      importance: low
      title: Export host with special unicode characters
    """
    host_data = host_inventory.datagen.create_host_data()
    host_data["display_name"] = "\u201c" + generate_display_name() + "\u201d"
    host_id = host_inventory.kafka.create_host(host_data=host_data).id

    host = host_inventory.apis.hosts.get_host_by_id(host_id)
    report = host_inventory.apis.exports.export_hosts(format=export_format)
    host_inventory.apis.exports.validate_export_report([host], report, format=export_format)
