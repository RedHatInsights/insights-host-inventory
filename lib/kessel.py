import grpc
from kessel.inventory.v1beta2 import allowed_pb2
from kessel.inventory.v1beta2 import check_request_pb2
from kessel.inventory.v1beta2 import inventory_service_pb2_grpc
from kessel.inventory.v1beta2 import reporter_reference_pb2
from kessel.inventory.v1beta2 import representation_type_pb2
from kessel.inventory.v1beta2 import resource_reference_pb2
from kessel.inventory.v1beta2 import streamed_list_objects_request_pb2
from kessel.inventory.v1beta2 import subject_reference_pb2

from app.auth.identity import Identity
from app.auth.rbac import KesselPermission
from app.config import Config
from app.logging import get_logger

logger = get_logger(__name__)

# Constants
PLATFORM_PREFIX = "redhat"
REPORTER_TYPE_RBAC = "rbac"


class Kessel:
    def __init__(self, config: Config):
        # Configure gRPC channel with timeout
        self.channel = grpc.insecure_channel(config.kessel_target_url)
        self.inventory_svc = inventory_service_pb2_grpc.KesselInventoryServiceStub(self.channel)
        self.timeout = getattr(config, "kessel_timeout", 10.0)  # Default 10 second timeout

    def check(self, current_identity: Identity, permission: KesselPermission, ids: list[str]) -> bool:
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
            logger.error(f"Kessel Check gRPC error: {e.code()} - {e.details()}")
            return False
        except Exception as e:
            logger.error(f"Kessel Check failed: {str(e)}", exc_info=True)
            return False

    def check_for_update(self, current_identity: Identity, permission: KesselPermission, ids: list[str]) -> bool:
        """
        Check if the current user has permission to update the specified resources.
        Automatically handles single or bulk checks based on the number of IDs provided.
        """
        try:
            # Build the subject reference (the user making the request)
            subject_ref = self._build_subject_reference(current_identity)

            if len(ids) == 1:
                # Single resource update check
                return self._check_single_resource_for_update(subject_ref, permission, ids[0])
            elif len(ids) > 1:
                # Bulk update check - all resources must be updatable
                return self._check_bulk_resources_for_update(subject_ref, permission, ids)
            else:
                # No specific IDs - this shouldn't happen in normal check_for_update flow
                logger.warning("check_for_update called with empty ID list")
                return False

        except grpc.RpcError as e:
            logger.error(f"Kessel check_for_update gRPC error: {e.code()} - {e.details()}")
            return False
        except Exception as e:
            logger.error(f"Kessel check_for_update failed: {str(e)}", exc_info=True)
            return False

    def _get_user_id_from_identity(self, current_identity: Identity) -> str:
        """Extract user ID from identity with proper fallback logic."""
        if not current_identity.user:
            raise ValueError("No user information available in identity")

        # Prefer user_id if available, fallback to username
        user_id = current_identity.user.get("user_id") or current_identity.user.get("username")

        if not user_id:
            raise ValueError("Unable to determine user ID from identity - neither user_id nor username available")

        return str(user_id)

    def _build_subject_reference(self, current_identity: Identity) -> subject_reference_pb2.SubjectReference:
        """Build a subject reference for the current user."""
        user_id = self._get_user_id_from_identity(current_identity)

        subject_ref = resource_reference_pb2.ResourceReference(
            resource_type="principal",
            resource_id=f"{PLATFORM_PREFIX}/{user_id}",
            reporter=reporter_reference_pb2.ReporterReference(type=REPORTER_TYPE_RBAC),
        )

        return subject_reference_pb2.SubjectReference(resource=subject_ref)

    def _check_single_resource(
        self, subject_ref: subject_reference_pb2.SubjectReference, permission: KesselPermission, resource_id: str
    ) -> bool:
        """Check permission for a single resource."""
        object_ref = resource_reference_pb2.ResourceReference(
            resource_type=permission.resource_type.name,  # e.g., "host"
            resource_id=resource_id,
            reporter=reporter_reference_pb2.ReporterReference(
                type=permission.resource_type.namespace,  # e.g., "hbi"
                instance_id=PLATFORM_PREFIX,
            ),
        )

        request = check_request_pb2.CheckRequest(
            subject=subject_ref,
            relation=permission.resource_permission,  # e.g., "view"
            object=object_ref,
        )

        response = self.inventory_svc.Check(request, timeout=self.timeout)
        return response.allowed == allowed_pb2.Allowed.ALLOWED_TRUE

    def _check_bulk_resources(
        self,
        subject_ref: subject_reference_pb2.SubjectReference,
        permission: KesselPermission,
        resource_ids: list[str],
    ) -> bool:
        """Check permissions for multiple resources. All must be accessible."""
        return all(self._check_single_resource(subject_ref, permission, resource_id) for resource_id in resource_ids)

    def _check_single_resource_for_update(
        self, subject_ref: subject_reference_pb2.SubjectReference, permission: KesselPermission, resource_id: str
    ) -> bool:
        """Check update permission for a single resource."""
        # For updates, we might need a different relation like "edit" or "write"
        # This depends on how permissions are modeled in Kessel
        update_permission = permission.resource_permission.replace("view", "edit")

        object_ref = resource_reference_pb2.ResourceReference(
            resource_type=permission.resource_type.name,
            resource_id=resource_id,
            reporter=reporter_reference_pb2.ReporterReference(
                type=permission.resource_type.namespace, instance_id=PLATFORM_PREFIX
            ),
        )

        request = check_request_pb2.CheckRequest(
            subject=subject_ref,
            relation=update_permission,
            object=object_ref,
        )

        response = self.inventory_svc.CheckForUpdate(request, timeout=self.timeout)
        return response.allowed == allowed_pb2.Allowed.ALLOWED_TRUE

    def _check_bulk_resources_for_update(
        self,
        subject_ref: subject_reference_pb2.SubjectReference,
        permission: KesselPermission,
        resource_ids: list[str],
    ) -> bool:
        """Check update permissions for multiple resources. All must be updatable."""
        for resource_id in resource_ids:
            if not self._check_single_resource_for_update(subject_ref, permission, resource_id):
                return False
        return True

    def list_allowed_workspaces(self, current_identity: Identity, relation: str) -> list[str]:
        """
        List all workspaces the current user has the specified relation to.

        Args:
            current_identity: The identity of the user making the request
            relation: The relation to check (e.g., "view", "edit")

        Returns:
            List of workspace IDs the user has access to
        """
        try:
            object_type = representation_type_pb2.RepresentationType(
                resource_type="workspace",
                reporter_type=REPORTER_TYPE_RBAC,
            )

            # Use the shared subject reference builder
            subject = self._build_subject_reference(current_identity)

            request = streamed_list_objects_request_pb2.StreamedListObjectsRequest(
                object_type=object_type,
                relation=relation,
                subject=subject,
            )

            workspaces = []
            stream = self.inventory_svc.StreamedListObjects(request, timeout=self.timeout)
            for workspace in stream:
                workspaces.append(workspace.object.resource_id)

            return workspaces

        except grpc.RpcError as e:
            logger.error(f"Kessel list_allowed_workspaces gRPC error: {e.code()} - {e.details()}")
            return []
        except Exception as e:
            logger.error(f"Kessel list_allowed_workspaces failed: {str(e)}", exc_info=True)
            return []

    def close(self):
        """Close the gRPC channel."""
        if hasattr(self, "channel"):
            self.channel.close()
            logger.info("Kessel gRPC channel closed")


def init_kessel(config: Config, app):
    kessel_client = Kessel(config)
    app.extensions["Kessel"] = kessel_client


def get_kessel_client(app) -> Kessel:
    return app.extensions["Kessel"]
