# mypy: disallow-untyped-defs

from __future__ import annotations

import csv
import json
import logging
import os
import re
import shutil
import zipfile
from functools import cached_property
from typing import Any

import attr
from iqe.base.modeling import BaseEntity
from iqe_export_service import ApplicationExportService
from iqe_export_service_api import ApiException
from iqe_export_service_api.api.default_api import DefaultApi
from iqe_export_service_api.models.export_list import ExportList
from iqe_export_service_api.models.export_request import ExportRequest
from iqe_export_service_api.models.export_request_resource import ExportRequestResource
from iqe_export_service_api.models.export_status import ExportStatus

import iqe_host_inventory
from iqe_host_inventory.utils.api_utils import accept_when
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory_api.models.host_out import HostOut

logger = logging.getLogger(__name__)

HBI_EXPORT_APPLICATION = "urn:redhat:application:inventory"
HBI_EXPORT_RESOURCE = "urn:redhat:application:inventory:export:systems"

# Map host record names to export report field names.  Right now, only id
# gets mapped to a different name.
HBI_EXPORT_FIELD_MAP = {
    "id": "host_id",
    "fqdn": "fqdn",
    "display_name": "display_name",
    "group_id": "group_id",
    "group_name": "group_name",
    "host_type": "host_type",
    "os_release": "os_release",
    "satellite_id": "satellite_id",
    "state": "state",
    "subscription_manager_id": "subscription_manager_id",
    "tags": "tags",
    "updated": "updated",
}


def _process_json_report(report: list[Any]) -> dict:
    """
    Convert json report into a host_id keyed dict for easier host-to-export
    validation later.

    Note: Not much processing to do here at this point, but keeping it as a
    separate function in case more arises.

    :param list[dict] report: list of json exported host records
    :return dict: processed report, in which the keys are host ids and the
        values point to their respective exported records
    """
    processed_report = {}
    for data in report:
        assert data["host_id"] not in processed_report, (
            f"This report contains a single host multiple times: {data['host_id']}"
        )
        processed_report[data["host_id"]] = data

    return processed_report


def _process_csv_report(report: list[Any]) -> dict:
    """
    Convert csv-styled tuple report into a host_id keyed dict for easier
    host-to-export validation later.

    Validate and convert csv-specific items such as:
        Empty values -> None

    :param list[dict] report: list of csv exported host records
    :return dict: processed report, in which the keys are host ids and the
        values point to their respective exported records
    """
    processed_report = {}

    def _convert_tags(tags: str) -> list[dict]:
        converted_tags = []
        tags_re = re.compile(r"(\w+)/(\w+):(\w+)")
        for tag in tags.split(";"):
            match = tags_re.search(tag)
            assert match is not None
            converted_tag = {
                "namespace": None if match.group(1) == "None" else match.group(1),
                "key": match.group(2),
                "value": None if match.group(3) == "None" else match.group(3),
            }
            converted_tags.append(converted_tag)

        return converted_tags

    # Form a dict from header/value tuples
    converted_data = [dict(zip(report[0], values_row, strict=False)) for values_row in report[1:]]

    # Process each row of the exported data
    for data in converted_data:
        assert data["host_id"] not in processed_report, (
            f"This report contains a single host multiple times: {data['host_id']}"
        )
        for field in data.keys():
            # Validate empty fields, then convert to None
            if not data[field]:
                assert data[field] == "", (
                    f"Unset csv field {field} has unexpected value {data[field]}"
                )
                data[field] = None
            elif field == "tags":
                data[field] = _convert_tags(data[field])

        processed_report[data["host_id"]] = data

    return processed_report


@attr.s
class ExportsAPIWrapper(BaseEntity):
    @cached_property
    def _host_inventory(self) -> iqe_host_inventory.ApplicationHostInventory:
        return self.application.host_inventory

    @cached_property
    def _exports(self) -> ApplicationExportService:
        return self.application.export_service

    @cached_property
    def raw_api(self) -> DefaultApi:
        """
        Raw auto-generated OpenAPI client.
        Use high level API wrapper methods instead of this raw API client.
        Outside this class this should be used only for negative validation testing.
        """
        return self._exports.rest_client.default_api

    def wait_for_completion(
        self,
        export_id: str,
        *,
        retries: int = 20,
        delay: float = 0.5,
    ) -> str:
        """Wait for an export to complete, return its status

        :param str export_id: export id
        :param int retries: number of retries
        :param int delay: delay between retries
        :return: str
        """

        def get_status() -> str:
            status = self.get_export_status(export_id).status
            logger.info(f"Export status is {status}")
            return status

        def is_valid(status: str) -> bool:
            return status == "complete" or status == "failed"

        return accept_when(get_status, is_valid=is_valid, retries=retries, delay=delay)

    def create_export(
        self,
        *,
        name: str | None = generate_uuid(),
        format: str | None = "json",
        filters: dict | None = None,
        wait_for_completion: bool | None = True,
        register_for_cleanup: bool | None = True,
        cleanup_scope: str = "function",
        **kwargs: Any,
    ) -> str:
        """Initiate an export request, return the export id

        :param str name: optional name assigned to the export
        :param str format: output format
            Valid options: json, csv
            Default: json
        :param dict filters: AND'ed group of filters applied to the export
            Example:
                {"status": "fresh", "operating_system": "rhel"}
            NOTE: Not yet supported for inventory
        :param bool wait_for_completion: wait for the export to complete
            Default: True
        :param bool register_for_cleanup: delete the export at session end
            Default: True
        :param str cleanup_scope: The scope to use for cleanup.
            Possible values: "function", "class", "module", "package", "session"
            Default: "function"
        :return: str
        """
        # Even though filters aren't yet supported and the Export Service openapi
        # spec makes the parameter optional, the code expects it.  See:
        #
        #      https://issues.redhat.com/browse/RHCLOUD-34219
        if not filters:
            filters = {}

        source = ExportRequestResource(
            application=HBI_EXPORT_APPLICATION, resource=HBI_EXPORT_RESOURCE, filters=filters
        )
        request = ExportRequest(name=name, format=format, sources=[source])

        export_id = self.raw_api.create_export(export_request=request).id

        if register_for_cleanup:
            self._host_inventory.cleanup.add_exports({export_id}, scope=cleanup_scope)

        if wait_for_completion:
            status = self.wait_for_completion(export_id, **kwargs)

            # Terminal states are "failed" and "complete".
            assert status == "complete", (
                f"Export request didn't complete successfully, status={status}"
            )

        return export_id

    def get_exports(self, **api_kwargs: Any) -> ExportList:
        """Get a list of inventory-specific exports

        :return: ExportList
        """
        return self.raw_api.get_exports(
            application=HBI_EXPORT_APPLICATION, resource=HBI_EXPORT_RESOURCE, **api_kwargs
        )

    def get_export_status(self, export_id: str) -> ExportStatus:
        """Get the status of an export; ExportStatus.status will be one of:

        'partial'|'pending'|'running'|'complete'|'failed'

        :param str export_id: export id
        :return: ExportStatus
        """
        return self.raw_api.get_export_status(id=export_id)

    def delete_export(self, export_id: str, *, fail_when_not_found: bool = False) -> None:
        """Delete an export

        :param str export_id: export id
        :param bool fail_when_not_found: raise an HTTP 404 exception when the export is not found
            Default: False
        """
        try:
            self.raw_api.delete_export(id=export_id)
        except ApiException as err:
            if err.status == 404 and not fail_when_not_found:
                logger.info(f"Couldn't delete export {export_id}, because it was not found.")
            else:
                raise err

    def delete_exports(self, export_ids: set[str], *, fail_when_not_found: bool = False) -> None:
        """Delete a list of exports

        :param list[str] export_ids: list of export ids
        :param bool fail_when_not_found: raise an HTTP 404 exception when the export is not found
            Default: False
        """
        for export_id in export_ids:
            self.delete_export(export_id, fail_when_not_found=fail_when_not_found)

    def delete_all_exports(self) -> None:
        """Delete all exports"""
        export_data = self.get_exports().data
        for export in export_data:
            self.delete_export(export.id, fail_when_not_found=True)

    def download_export(self, export_id: str) -> str:
        """Download the export data path, return this path

        A fully-qualified path to a zip file will be returned.  The export
        data can then be fetched from this archive.  Assumes the export is
        complete.

        :param str export_id: export id
        :return: str
        """
        path = self.raw_api.download_export(id=export_id)
        assert os.path.isfile(path)

        return path

    def fetch_export_data(self, path: str, delete_zip: bool = True) -> list[dict] | list[tuple]:
        """Fetch export output, return this data.

        If the format is json, a list of dicts is returned.  Here's a two host
        example (with most fields omitted for brevity):

          [
            {'display_name': 'rhiqe.66ff9718-d106-4b0f-951e-b37a5ea9a678',
             'id': '25378dd8-e927-4583-87cb-e92a6248dca3',
             'os_release': '8.7',
             'tags': [
               {'key': 'PjMdDvT', 'namespace': 'sdSdqDTz', 'value': 'xxnmd'}],
             'updated': '2024-07-30T17:36:15.012744+00:00'},
            {'display_name': 'rhiqe.47b8d11a-e9a6-460c-bb50-4a17659482d3',
             'id': 'ddeea4e3-93f9-46e1-9f67-c066c28acf51',
             'os_release': '8.7',
             'tags': [
               {'key': 'TPcJYWBs', 'namespace': 'XWqCx', 'value': 'bzCJc'}],
             'updated': '2024-07-30T17:36:13.080936+00:00'}
          ]

        If the format is csv, a list of tuples is returned.  In this case, the
        first item will be the headers and the rest will be the values.  Two host
        example (again, most fields omitted):

          [
            ('id', 'display_name', 'os_release', 'updated', 'tags'),
            ('07181e43-98c6-4da4-9f3e-a2ec2b987685',
             'rhiqe.f12f34e6-ec04-4a7e-8fe6-f8dd1f729326',
             '8.7',
             '2024-07-30T17:55:14.304127+00:00',
             'RXTyiQ/bGcZMmS:EuUtb;eZYhCVf/ZJQNkXQ:ItdPXlAN;LthMYoVN/WnGtwG:XATGfWyG;pVysyWGAV/RmFEMZgH:TgpaaDQOE;pKbPNYJUyi/VUEfLf:VWrORnEjfu'),
            ('9a8e7da5-cd5d-4377-a833-b72a24768eb2',
             'rhiqe.a30f174d-942b-49d4-9ec8-a463e87e52c5',
             '8.7',
             '2024-07-30T17:55:12.311791+00:00',
             'XcBBPR/nJFvGiCOqe:CPrBQy;ijEqGzEb/tbYIMc:AyrIG;SmpMOMEwN/OEGsjS:UpzCgLYw;imMAwgEpv/gSkJukQW:hOiLkkedUS;qXTVIPbOg/GyZQjOz:GIUUwpC')
          ]

        :param str path: fully-qualified path to export zip file
        :param bool delete_zip: Delete the export zip file?
            Default: True
        :return: list[dict] | list[tuple]
        """
        target_dir = f"{os.path.dirname(path)}/{os.path.basename(path).split('.')[0]}"

        with zipfile.ZipFile(path) as f:
            f.extractall(target_dir)

        # The export payload contains 3 files: README.md, meta.<fmt>, and
        # <filename>.<fmt>.  The latter file contains the export data.

        with open(f"{target_dir}/meta.json") as f:
            meta_data = json.load(f)

        export_file = meta_data["file_meta"][0]["filename"]

        with open(f"{target_dir}/{export_file}") as f:
            if export_file.endswith(".json"):
                data = json.load(f)
            else:
                file_data = csv.reader(f)
                data = [tuple(row) for row in file_data]

        if delete_zip:
            os.remove(path)
        shutil.rmtree(target_dir)

        return data

    def export_hosts(
        self,
        *,
        name: str | None = generate_uuid(),
        format: str | None = "json",
        filters: dict | None = None,
        delete_zip: bool = True,
    ) -> list[dict] | list[tuple]:
        """Export hosts, return the data

        Convenience method that performs the complete export workflow and
        returns the data.

        :param str name: optional name assigned to the export
        :param str format: output format
            Valid options: json, csv
            Default: json
        :param dict filters: AND'ed group of filters applied to the export
            Example: {"status": "fresh", "operating_system": "rhel"}
            NOTE: not yet supported
        :param bool delete_zip: Delete the export zip file?
            Default: True
        :return list[dict] | list[tuple]: If format is json, return dicts, otherwise return tuples
        """
        if not filters:
            filters = {}

        export_id = self.create_export(name=name, format=format, filters=filters)
        path = self.download_export(export_id)
        data = self.fetch_export_data(path, delete_zip=delete_zip)

        return data

    def convert_export_report(
        self,
        report: list[dict] | list[tuple],
        *,
        format: str = "json",
    ) -> dict[str, dict]:
        """Convert an export report.  The returned format will be a dict keyed
        by host id with values being their respective host records.

        :param list[dict] | list[tuple] report: list of exported host records
        :param str format: output format
            Valid options: json, csv
            Default: json
        :return: dict[str, dict]
        """
        if format == "json":
            return _process_json_report(report)
        elif format == "csv":
            return _process_csv_report(report)
        raise ValueError("Report format has to be one of: json, csv")

    def validate_export_report(
        self,
        hosts: list[HostOut],
        report: list[dict] | list[tuple],
        *,
        format: str = "json",
    ) -> dict[str, dict]:
        """Export hosts, return the data

        Validate export output against a group of hosts.  A converted report
        is returned.  Its format is a dict keyed by host id with values being
        their respective host info records.

        :param list hosts: list of hosts
        :param list[dict] | list[tuple] report: list of exported host records
        :param str format: output format
            Valid options: json, csv
            Default: json
        :return: dict[str, dict]
        """
        processed_report: dict = self.convert_export_report(report, format=format)
        assert len(processed_report.keys()) == len(hosts)

        for host in hosts:
            assert host.id in processed_report

            export_entry = processed_report[host.id]
            assert set(export_entry.keys()) == set(HBI_EXPORT_FIELD_MAP.values())

            sp = self._host_inventory.apis.hosts.get_host_system_profile(host)

            assert export_entry[HBI_EXPORT_FIELD_MAP["display_name"]] == host.display_name
            assert export_entry[HBI_EXPORT_FIELD_MAP["fqdn"]] == host.fqdn
            assert export_entry[HBI_EXPORT_FIELD_MAP["satellite_id"]] == host.satellite_id
            assert (
                export_entry[HBI_EXPORT_FIELD_MAP["subscription_manager_id"]]
                == host.subscription_manager_id
            )
            assert export_entry[HBI_EXPORT_FIELD_MAP["updated"]] == host.updated.isoformat()

            if host.openshift_cluster_id:
                assert export_entry[HBI_EXPORT_FIELD_MAP["host_type"]] == "cluster", (
                    f"{export_entry[HBI_EXPORT_FIELD_MAP['host_type']]} != cluster"
                )
            elif sp.system_profile.host_type:
                assert (
                    export_entry[HBI_EXPORT_FIELD_MAP["host_type"]] == sp.system_profile.host_type
                ), (
                    f"{export_entry[HBI_EXPORT_FIELD_MAP['host_type']]} != "
                    f"{sp.system_profile.host_type}"
                )
            else:
                assert export_entry[HBI_EXPORT_FIELD_MAP["host_type"]] == "conventional", (
                    f"{export_entry[HBI_EXPORT_FIELD_MAP['host_type']]} != conventional"
                )

            assert export_entry[HBI_EXPORT_FIELD_MAP["os_release"]] == sp.system_profile.os_release

            if host.groups:
                assert export_entry[HBI_EXPORT_FIELD_MAP["group_id"]] == host.groups[0].id
                assert export_entry[HBI_EXPORT_FIELD_MAP["group_name"]] == host.groups[0].name
            else:
                assert export_entry[HBI_EXPORT_FIELD_MAP["group_id"]] is None
                assert export_entry[HBI_EXPORT_FIELD_MAP["group_name"]] is None

            host_tags = self._host_inventory.apis.hosts.get_host_tags_response(host).results[
                host.id
            ]
            if host_tags:
                assert len(export_entry[HBI_EXPORT_FIELD_MAP["tags"]]) == len(host_tags)
                for i in range(len(host_tags)):
                    assert export_entry[HBI_EXPORT_FIELD_MAP["tags"]][i] == host_tags[i].to_dict()

            # Note: lacking state validation.  Can't directly get this from
            # the host record.  Would need to filter all hosts by state and
            # do a lookup or set some type of mapping.  Maybe revisit or
            # maybe let caller validate this?  TBD.

        return processed_report

    def verify_access_denied(self) -> None:
        """Verify that an export request is denied with a 403 response

        :return: None
        """
        # The create_export() method will error out (maybe revisit this?) if
        # we wait for completion and fail, so need to do the wait directly
        export_id = self.create_export(wait_for_completion=False)
        assert self.wait_for_completion(export_id) == "failed"

        status = self.get_export_status(export_id)

        assert status.status == "failed"
        assert status.sources[0].error == 403
        assert (
            status.sources[0].message
            == "You don't have the permission to access the requested resource."
        )
