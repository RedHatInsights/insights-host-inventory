from typing import Optional
from api import resource_type
from app.models import (
    Host,
    HostGroupAssoc
)
from app import Config, KesselPermission
from flask import current_app
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.auth.identity import Identity

from app.logging import get_logger
logger = get_logger(__name__)

import grpc
from grpc import StatusCode
from kessel.inventory.v1beta2 import (
    check_request_pb2,
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
        # Configure gRPC channel with proper timeout and retry settings
        self.channel = grpc.insecure_channel(config.kessel_target_url)
        self.inventory_svc = inventory_service_pb2_grpc.KesselInventoryServiceStub(self.channel)
        self.timeout = getattr(config, 'kessel_timeout', 10.0)  # Default 10 second timeout
        
    def _handle_grpc_error(self, e: grpc.RpcError, operation: str) -> bool:
        """Handle gRPC errors with appropriate logging and fallback behavior."""
        if e.code() == StatusCode.UNAVAILABLE:
            logger.error(f"Kessel service unavailable for {operation}: {e.details()}")
        elif e.code() == StatusCode.DEADLINE_EXCEEDED:
            logger.error(f"Kessel timeout for {operation}: {e.details()}")
        elif e.code() == StatusCode.PERMISSION_DENIED:
            logger.warning(f"Kessel permission denied for {operation}: {e.details()}")
            return False  # Explicit denial
        elif e.code() == StatusCode.UNAUTHENTICATED:
            logger.error(f"Kessel authentication failed for {operation}: {e.details()}")
        else:
            logger.error(f"Kessel gRPC error for {operation}: {e.code()} - {e.details()}")
        
        return False  # Fail closed by default

    def Check(self, current_identity: Identity, permission: KesselPermission, ids: list[int]) -> bool:
        """
        Check if the current user has permission to access the specified resources.
        Automatically handles single or bulk checks based on the number of IDs provided.
        """
        try:
            # Build the subject reference (the user making the request)
            subject_ref = self._build_subject_reference(current_identity)
            
            if len(ids) == 1:
                # Single resource check
                return self._check_single_resource(subject_ref, permission, str(ids[0]))
            elif len(ids) > 1:
                # Bulk check - all resources must be accessible
                return self._check_bulk_resources(subject_ref, permission, [str(id) for id in ids])
            else:
                # No specific IDs - this shouldn't happen in normal Check flow
                logger.warning("Check called with empty ID list")
                return False
                
        except grpc.RpcError as e:
            return self._handle_grpc_error(e, "Check")
        except Exception as e:
            logger.error(f"Kessel Check failed: {str(e)}", exc_info=True)
            return False

    def CheckForUpdate(self, current_identity: Identity, permission: KesselPermission, ids: list[int]) -> bool:
        """
        Check if the current user has permission to update the specified resources.
        Automatically handles single or bulk checks based on the number of IDs provided.
        """
        try:
            # Build the subject reference (the user making the request)
            subject_ref = self._build_subject_reference(current_identity)
            
            if len(ids) == 1:
                # Single resource update check
                return self._check_single_resource_for_update(subject_ref, permission, str(ids[0]))
            elif len(ids) > 1:
                # Bulk update check - all resources must be updatable
                return self._check_bulk_resources_for_update(subject_ref, permission, [str(id) for id in ids])
            else:
                # No specific IDs - this shouldn't happen in normal CheckForUpdate flow
                logger.warning("CheckForUpdate called with empty ID list")
                return False
                
        except grpc.RpcError as e:
            return self._handle_grpc_error(e, "CheckForUpdate")
        except Exception as e:
            logger.error(f"Kessel CheckForUpdate failed: {str(e)}", exc_info=True)
            return False

    def _build_subject_reference(self, current_identity: Identity) -> subject_reference_pb2.SubjectReference:
        """Build a subject reference for the current user."""
        # Get user ID, falling back to username if user_id not available
        user_id = current_identity.user.get('user_id') if current_identity.user else None
        if not user_id:
            user_id = current_identity.user.get('username') if current_identity.user else None
        
        if not user_id:
            raise ValueError("Unable to determine user ID from identity")
            
        subject_ref = resource_reference_pb2.ResourceReference(
            resource_type="principal",
            resource_id=f"redhat/{user_id}",  # Platform/IdP prefix
            reporter=reporter_reference_pb2.ReporterReference(
                type="rbac"
            ),
        )
        
        return subject_reference_pb2.SubjectReference(resource=subject_ref)

    def _check_single_resource(self, subject_ref: subject_reference_pb2.SubjectReference, 
                             permission: KesselPermission, resource_id: str) -> bool:
        """Check permission for a single resource."""
        object_ref = resource_reference_pb2.ResourceReference(
            resource_type=permission.resource_type.name,  # e.g., "host"
            resource_id=resource_id,
            reporter=reporter_reference_pb2.ReporterReference(
                type=permission.resource_type.namespace  # e.g., "hbi"
            ),
        )
        
        request = check_request_pb2.CheckRequest(
            subject=subject_ref,
            relation=permission.resource_permission,  # e.g., "view"
            object=object_ref,
        )
        
        response = self.inventory_svc.Check(request, timeout=self.timeout)
        return response.allowed

    def _check_bulk_resources(self, subject_ref: subject_reference_pb2.SubjectReference,
                            permission: KesselPermission, resource_ids: list[str]) -> bool:
        """Check permissions for multiple resources. All must be accessible."""
        for resource_id in resource_ids:
            if not self._check_single_resource(subject_ref, permission, resource_id):
                return False
        return True

    def _check_single_resource_for_update(self, subject_ref: subject_reference_pb2.SubjectReference,
                                        permission: KesselPermission, resource_id: str) -> bool:
        """Check update permission for a single resource."""
        # For updates, we might need a different relation like "edit" or "write"
        # This depends on how permissions are modeled in Kessel
        update_permission = permission.resource_permission.replace("view", "edit")
        
        object_ref = resource_reference_pb2.ResourceReference(
            resource_type=permission.resource_type.name,
            resource_id=resource_id,
            reporter=reporter_reference_pb2.ReporterReference(
                type=permission.resource_type.namespace
            ),
        )
        
        request = check_request_pb2.CheckRequest(
            subject=subject_ref,
            relation=update_permission,
            object=object_ref,
        )
        
        response = self.inventory_svc.CheckForUpdate(request, timeout=self.timeout)
        return response.allowed

    def _check_bulk_resources_for_update(self, subject_ref: subject_reference_pb2.SubjectReference,
                                       permission: KesselPermission, resource_ids: list[str]) -> bool:
        """Check update permissions for multiple resources. All must be updatable."""
        for resource_id in resource_ids:
            if not self._check_single_resource_for_update(subject_ref, permission, resource_id):
                return False
        return True

    def ListAllowedWorkspaces(self, current_identity: Identity, relation) -> list[str]:
            object_type = representation_type_pb2.RepresentationType(
                resource_type="workspace",
                reporter_type="rbac",
            )

            #logger.info(f"user identity that reached the kessel lib: {current_identity.user}")
            user_id = current_identity.user['user_id'] if current_identity.user['user_id'] else current_identity.user['username'] #HACK: this is ONLY to continue testing while waiting for the user_id bits to start working
            #logger.info(f"user_id resolved from the identity: {user_id}")
            subject_ref = resource_reference_pb2.ResourceReference(
                resource_type="principal",
                resource_id=f"redhat/{user_id}", #Platform/IdP/whatever 'redhat' is, probably needs to be parameterized
                reporter=reporter_reference_pb2.ReporterReference(
                    type="rbac"
                ),
            )

            subject = subject_reference_pb2.SubjectReference(
                resource=subject_ref,
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

        self.inventory_svc.DeleteResource(request)

    def close(self):
        """Close the gRPC channel."""
        if hasattr(self, 'channel'):
            self.channel.close()
            logger.info("Kessel gRPC channel closed")

def init_kessel(config: Config, app):
    kessel_client = Kessel(config)
    app.extensions["Kessel"] = kessel_client

    event.listen(Session, "after_flush", after_flush)
    event.listen(Session, "before_commit", before_commit)

def get_kessel_client(app) -> Kessel:
    return app.extensions["Kessel"]
