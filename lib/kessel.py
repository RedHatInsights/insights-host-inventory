import time

import grpc
from grpc import StatusCode
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


class Kessel:
    def __init__(self, config: Config):
        # Configure gRPC channel with proper timeout and retry settings
        self.channel = grpc.insecure_channel(config.kessel_target_url)
        self.inventory_svc = inventory_service_pb2_grpc.KesselInventoryServiceStub(self.channel)
        self.timeout = getattr(config, "kessel_timeout", 10.0)  # Default 10 second timeout
        self.max_retries = getattr(config, "kessel_max_retries", 3)  # Default 3 retries
        self.retry_delay = getattr(config, "kessel_retry_delay", 1.0)  # Default 1 second delay

    def _is_retryable_error(self, e: grpc.RpcError) -> bool:
        """Determine if a gRPC error is retryable."""
        retryable_codes = {
            StatusCode.UNAVAILABLE,
            StatusCode.DEADLINE_EXCEEDED,
            StatusCode.INTERNAL,
            StatusCode.UNKNOWN,
        }
        return e.code() in retryable_codes

    def _handle_grpc_error(self, e: grpc.RpcError, operation: str) -> bool:
        """Handle gRPC errors with appropriate logging and fallback behavior."""
        if e.code() == StatusCode.UNAVAILABLE:
            logger.error(f"Kessel service unavailable for {operation}: {e.details()}")
        elif e.code() == StatusCode.DEADLINE_EXCEEDED:
            logger.error(f"Kessel timeout for {operation}: {e.details()}")
        elif e.code() == StatusCode.PERMISSION_DENIED:
            logger.warning(f"Kessel permission denied for {operation}: {e.details()}")
            return False  # Explicit denial - not retryable
        elif e.code() == StatusCode.UNAUTHENTICATED:
            logger.error(f"Kessel authentication failed for {operation}: {e.details()}")
            return False  # Authentication errors are not retryable
        else:
            logger.error(f"Kessel gRPC error for {operation}: {e.code()} - {e.details()}")

        return False  # Fail closed by default

    def _retry_grpc_call(self, operation_name: str, operation_func, *args, **kwargs):
        """Execute a gRPC operation with retry logic."""
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return operation_func(*args, **kwargs)
            except grpc.RpcError as e:
                last_exception = e

                if not self._is_retryable_error(e):
                    # Non-retryable error, fail immediately
                    return self._handle_grpc_error(e, operation_name)

                if attempt < self.max_retries:
                    # Retryable error, wait and retry
                    wait_time = self.retry_delay * (2**attempt)  # Exponential backoff
                    logger.warning(
                        f"Kessel {operation_name} failed (attempt {attempt + 1}/{self.max_retries + 1}): "
                        f"{e.details()}. Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    # Max retries exceeded
                    logger.error(f"Kessel {operation_name} failed after {self.max_retries + 1} attempts")
                    return self._handle_grpc_error(e, operation_name)
            except Exception as e:
                logger.error(f"Kessel {operation_name} failed with unexpected error: {str(e)}", exc_info=True)
                return False

        # This should never be reached, but just in case
        if last_exception:
            return self._handle_grpc_error(last_exception, operation_name)
        return False

    def check(self, current_identity: Identity, permission: KesselPermission, ids: list[str]) -> bool:
        """
        Check if the current user has permission to access the specified resources.
        Automatically handles single or bulk checks based on the number of IDs provided.
        """
        try:
            # Build the subject reference (the user making the request)
            subject_ref = self._build_subject_reference(current_identity)

            if len(ids) == 1:
                # Single resource check with retry
                return self._retry_grpc_call(
                    "Check", self._check_single_resource, subject_ref, permission, str(ids[0])
                )
            elif len(ids) > 1:
                # Bulk check - all resources must be accessible
                return self._check_bulk_resources(subject_ref, permission, [str(id) for id in ids])
            else:
                # No specific IDs - this shouldn't happen in normal Check flow
                logger.warning("Check called with empty ID list")
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
            resource_id=f"redhat/{user_id}",  # Platform/IdP prefix
            reporter=reporter_reference_pb2.ReporterReference(type="rbac"),
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
                instance_id="redhat",
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
                type=permission.resource_type.namespace, instance_id="redhat"
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

    def ListAllowedWorkspaces(self, current_identity: Identity, relation) -> list[str]:
        object_type = representation_type_pb2.RepresentationType(
            resource_type="workspace",
            reporter_type="rbac",
        )

        # Get user ID with proper fallback logic
        user_id = self._get_user_id_from_identity(current_identity)

        subject_ref = resource_reference_pb2.ResourceReference(
            resource_type="principal",
            resource_id=f"redhat/{user_id}",  # Platform/IdP prefix - should be configurable
            reporter=reporter_reference_pb2.ReporterReference(type="rbac"),
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
