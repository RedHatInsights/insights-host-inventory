from typing import Optional
from app.models import (
    Host,
    HostGroupAssoc
)
from app import Config
from flask import current_app
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.auth.identity import Identity

import grpc
from kessel.inventory.v1beta2 import (
    resource_pb2,
    representation_metadata_pb2,
    resource_representations_pb2,
    inventory_service_pb2_grpc,
    report_resource_request_pb2,
    streamed_list_objects_request_pb2,
)
from google.protobuf import struct_pb2

def after_flush(session, flush_context):
    # Add feature flag here- skip if not set
    client: Kessel = get_kessel_client(current_app)
    for obj in session.new:
        if isinstance(obj, Host):
            host: Host = obj
            client.ReportHost(host)
        elif isinstance(obj, HostGroupAssoc):
            assoc: HostGroupAssoc = obj
            client.ReportHostMoved(assoc.host_id, assoc.group_id)

    for obj in session.deleted:
        if isinstance(obj, Host):
            host: Host = obj
            client.DeleteHost(host.id)

class Kessel:
    def __init__(self, config: Config):
        channel = grpc.insecure_channel(config.kessel_target_url)
        self.inventory_svc = inventory_service_pb2_grpc.KesselInventoryServiceStub(channel)

    def ListAllowedWorkspaces(self, current_identity: Identity, relation) -> list[str]:
        pass

    def ReportHost(self, host: Host):
        common_struct = struct_pb2.Struct()
        if host.groups:
            common_struct.update({
                "workspace_id": str(host.groups[0])
            })

        reporter_struct = struct_pb2.Struct()
        reporter_struct.update({
            "insights_inventory_id": str(host.id), #Actually, should probably come from canonical_facts
        })

        metadata = representation_metadata_pb2.RepresentationMetadata(
            local_resource_id=str(host.id),
            api_href="https://apiHref.com/",
            console_href="https://www.consoleHref.com/",
            reporter_version="0.1"
        )

        representations = resource_representations_pb2.ResourceRepresentations(
            metadata=metadata,
            common=common_struct,
            reporter=reporter_struct
        )

        resource = resource_pb2.Resource(
            type="host",
            reporter_type="HBI",
            reporter_instance_id="3c4e2382-26c1-11f0-8e5c-ce0194e9e144",
            representations=representations
        )

        request = report_resource_request_pb2.ReportResourceRequest(
            resource=resource
        )

        self.inventory_svc.ReportResource(request)

    def ReportHostMoved(self, hostId, workspaceId):
        common_struct = struct_pb2.Struct()
        common_struct.update({
            "workspace_id": workspaceId
        })


        metadata = representation_metadata_pb2.RepresentationMetadata(
            local_resource_id=hostId,
            api_href="https://apiHref.com/",
            console_href="https://www.consoleHref.com/",
            reporter_version="0.1"
        )

        representations = resource_representations_pb2.ResourceRepresentations(
            metadata=metadata,
            common=common_struct
        )

        resource = resource_pb2.Resource(
            type="host",
            reporter_type="HBI",
            reporter_instance_id="3c4e2382-26c1-11f0-8e5c-ce0194e9e144",
            representations=representations
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

def init_kessel(config: Config, app):
    kessel_client = Kessel(config)
    app.extensions["Kessel"] = kessel_client

    event.listen(Session, "after_flush", after_flush)

def get_kessel_client(app) -> Kessel:
    return app.extensions["Kessel"]
