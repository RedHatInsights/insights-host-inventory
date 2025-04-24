from app.models import Host
from app import Config

import grpc
from kessel.inventory.v1beta2 import (
    resource_pb2,
    reporter_data_pb2,
    resource_service_pb2_grpc,
    resource_service_pb2
)
from google.protobuf import struct_pb2
from app.common import inventory_config

class Kessel:
    def __init__(self, config: Config):
        channel = grpc.insecure_channel(config.kessel_target_url)
        self.resource_svc = resource_service_pb2_grpc.KesselResourceServiceStub(channel)

    def ReportHost(self, host: Host):
        common_resource_data_struct = struct_pb2.Struct()
        if host.groups:
            common_resource_data_struct.update({
                "workspace_id": str(host.groups[0])
            })

        resource = resource_pb2.Resource(
            resource_type="host",
            reporter_data=reporter_data_pb2.ReporterData(
                reporter_type="HBI",
                reporter_instance_id=None, #TODO: should this be None? Does HBI use instance ids?
                reporter_version=None, #TODO: is this always 0.1?
                local_resource_id=host.id,
                api_href=None, #TODO: need to generate
                console_href=None, #TODO: need to generate
                resource_data=common_resource_data_struct
            ),
            common_resource_data=common_resource_data_struct
        )

        request = resource_service_pb2.ReportResourceRequest(
            resource=resource
        )

        self.resource_svc.ReportResource(request)

    def ReportHostMoved(self, hostId, workspaceId):
        common_resource_data_struct = struct_pb2.Struct()
        common_resource_data_struct.update({
            "workspace_id": workspaceId
        })

        resource = resource_pb2.Resource(
            resource_type="host",
            reporter_data=reporter_data_pb2.ReporterData(
                reporter_type="HBI",
                reporter_instance_id=None, #TODO: should this be None? Does HBI use instance ids?
                reporter_version=None, #TODO: is this always 0.1?
                local_resource_id=hostId,
                api_href=None, #TODO: need to generate
                console_href=None, #TODO: need to generate
                resource_data=common_resource_data_struct
            ),
            common_resource_data=common_resource_data_struct
        )

        request = resource_service_pb2.ReportResourceRequest(
            resource=resource
        )

        self.resource_svc.ReportResource(request)

    def DeleteHost(self, id: str):
        request = resource_service_pb2.DeleteResourceRequest(
            reporter_type="HBI",
            local_resource_id=id,
        )

        self.resource_svc.DeleteResource(request)

kessel_client = Kessel(inventory_config())