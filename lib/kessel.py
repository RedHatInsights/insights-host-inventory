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
    representation_metadata_pb2,
    resource_representations_pb2,
    inventory_service_pb2_grpc,
    report_resource_request_pb2,
    delete_resource_request_pb2,
    resource_reference_pb2,
    reporter_reference_pb2,
    streamed_list_objects_request_pb2,
    representation_type_pb2,
    subject_reference_pb2
)
from google.protobuf import struct_pb2

def after_flush(session: Session, flush_context):
    if "kessel_items" not in session.info:
        session.info["kessel_items"] = {
            "upsert": {},
            "remove": {}
        }
    
    items = session.info["kessel_items"]
    upsert = items["upsert"]
    remove = items["remove"]

    for obj in session.new:
        if isinstance(obj, Host):
            host: Host = obj
            upsert[host.id] = host

    for obj in session.dirty:
        if isinstance(obj, Host):
            host: Host = obj
            upsert[host.id] = host

    for obj in session.deleted:
        if isinstance(obj, Host):
            host: Host = obj
            remove[host.id] = host

def before_commit(session: Session):
    if "kessel_items" in session.info:
        client = get_kessel_client(current_app)
        items = session.info["kessel_items"]

        upsert = items["upsert"]
        for to_upsert in upsert.values():
            client.ReportHost(to_upsert)
        upsert.clear()

        remove = items["remove"]
        for to_remove in remove.values():
            client.DeleteHost(to_remove)
        remove.clear()

class Kessel:
    def __init__(self, config: Config):
        channel = grpc.insecure_channel(config.kessel_target_url)
        self.inventory_svc = inventory_service_pb2_grpc.KesselInventoryServiceStub(channel)

    def ListAllowedWorkspaces(self, current_identity: Identity, relation) -> list[str]:
            object_type = representation_type_pb2.RepresentationType(
                resource_type="workspace",
                reporter_type="rbac",
            )

            resource_ref = resource_reference_pb2.ResourceReference(
                resource_type="principal",
                resource_id=f"redhat/{current_identity.user['user_id']}", #Platform/IdP/whatever 'redhat' is, probably needs to be parameterized
                reporter=reporter_reference_pb2.ReporterReference(
                    type="rbac"
                ),
            )

            subject = subject_reference_pb2.SubjectReference(
                resource=resource_ref,
            )

            request = streamed_list_objects_request_pb2.StreamedListObjectsRequest(
                object_type=object_type,
                relation=relation,
                subject=subject,
            )

            workspaces = list()
            stream = self.inventory_svc.StreamedListObjects(request)
            for workspace in stream:
                workspaces.append(workspace.object.resource_id)

            return workspaces


    def ReportHost(self, host: Host):
        common_struct = struct_pb2.Struct()
        if host.groups:
            group = host.groups[0]
            common_struct.update({
                "workspace_id": str(group["id"])
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

        request = report_resource_request_pb2.ReportResourceRequest(
            type="host",
            reporter_type="hbi",
            reporter_instance_id="3c4e2382-26c1-11f0-8e5c-ce0194e9e144",
            representations=representations
        )

        self.inventory_svc.ReportResource(request)

    def DeleteHost(self, id: str):
        request = delete_resource_request_pb2.DeleteResourceRequest(
            reference=resource_reference_pb2.ResourceReference(
                resource_type="host",
                resource_id=id,
                reporter=reporter_reference_pb2.ReporterReference(
                    type="hbi"
                )
            )
        )

        self.resource_svc.DeleteResource(request)

def init_kessel(config: Config, app):
    kessel_client = Kessel(config)
    app.extensions["Kessel"] = kessel_client

    event.listen(Session, "after_flush", after_flush)
    event.listen(Session, "before_commit", before_commit)

def get_kessel_client(app) -> Kessel:
    return app.extensions["Kessel"]
