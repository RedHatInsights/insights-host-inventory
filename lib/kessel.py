import grpc
from grpc import StatusCode
from kessel.auth import OAuth2ClientCredentials
from kessel.auth import fetch_oidc_discovery
from kessel.inventory.v1beta2 import ClientBuilder
from kessel.inventory.v1beta2 import allowed_pb2
from kessel.inventory.v1beta2 import check_bulk_request_pb2
from kessel.inventory.v1beta2 import check_request_pb2
from kessel.inventory.v1beta2 import reporter_reference_pb2
from kessel.inventory.v1beta2 import resource_reference_pb2
from kessel.inventory.v1beta2 import subject_reference_pb2
from kessel.inventory.v1beta2.check_bulk_response_pb2 import CheckBulkResponse
from kessel.inventory.v1beta2.check_for_update_response_pb2 import CheckForUpdateResponse
from kessel.inventory.v1beta2.check_response_pb2 import CheckResponse
from kessel.rbac.v2 import list_workspaces

from app.auth.identity import Identity
from app.auth.rbac import KesselPermission
from app.config import Config
from app.logging import get_logger

logger = get_logger(__name__)


class Kessel:
    def __init__(self, config: Config):
        client_builder = ClientBuilder(config.kessel_inventory_api_endpoint)

        if config.kessel_auth_enabled:
            # Configure Kessel Oauth2 credentials
            discovery = fetch_oidc_discovery(config.kessel_auth_oidc_issuer)
            auth_credentials = OAuth2ClientCredentials(
                client_id=config.kessel_auth_client_id,
                client_secret=config.kessel_auth_client_secret,
                token_endpoint=discovery.token_endpoint,
            )

            client_builder = client_builder.oauth2_client_authenticated(auth_credentials)

        if config.kessel_insecure:
            client_builder = client_builder.insecure()

        self.inventory_svc, self.channel = client_builder.build()
        self.timeout = getattr(config, "kessel_timeout", 10.0)  # Default 10 second timeout

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
            return self._handle_grpc_error(e, "Check")
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
            return self._handle_grpc_error(e, "check_for_update")
        except Exception as e:
            logger.error(f"Kessel check_for_update failed: {str(e)}", exc_info=True)
            return False

    def _build_subject_reference(self, current_identity: Identity) -> subject_reference_pb2.SubjectReference:
        """Build a subject reference for the current user."""
        # Get user ID, falling back to username if user_id not available
        user_id = current_identity.user.get("user_id") if current_identity.user else None
        if not user_id:
            user_id = current_identity.user.get("username") if current_identity.user else None

        if not user_id:
            raise ValueError("Unable to determine user ID from identity")

        subject_ref = resource_reference_pb2.ResourceReference(
            resource_type="principal",
            resource_id=f"redhat/{user_id}",  # Platform/IdP prefix
            reporter=reporter_reference_pb2.ReporterReference(type="rbac"),
        )

        return subject_reference_pb2.SubjectReference(resource=subject_ref)

    def _build_object_reference(
        self, permission: KesselPermission, resource_id: str
    ) -> resource_reference_pb2.ResourceReference:
        """Build an object reference for a resource."""
        return resource_reference_pb2.ResourceReference(
            resource_type=permission.resource_type.name,  # e.g., "host"
            resource_id=resource_id,
            reporter=reporter_reference_pb2.ReporterReference(
                type=permission.resource_type.namespace,  # e.g., "hbi"
                instance_id="redhat",
            ),
        )

    def _check_single_resource(
        self, subject_ref: subject_reference_pb2.SubjectReference, permission: KesselPermission, resource_id: str
    ) -> bool:
        """Check permission for a single resource."""
        request = check_request_pb2.CheckRequest(
            subject=subject_ref,
            relation=permission.resource_permission,  # e.g., "view"
            object=self._build_object_reference(permission, resource_id),
        )

        response: CheckResponse = self.inventory_svc.Check(request, timeout=self.timeout)
        return response.allowed == allowed_pb2.Allowed.ALLOWED_TRUE

    def _check_bulk_resources(
        self,
        subject_ref: subject_reference_pb2.SubjectReference,
        permission: KesselPermission,
        resource_ids: list[str],
    ) -> bool:
        """Check permissions for multiple resources. All must be accessible."""
        if not resource_ids:
            raise ValueError("resource_ids can't be empty")

        # Build bulk request items for all resources
        items = [
            check_bulk_request_pb2.CheckBulkRequestItem(
                subject=subject_ref,
                relation=permission.resource_permission,
                object=self._build_object_reference(permission, resource_id),
            )
            for resource_id in resource_ids
        ]

        bulk_request = check_bulk_request_pb2.CheckBulkRequest(items=items)
        response: CheckBulkResponse = self.inventory_svc.CheckBulk(bulk_request, timeout=self.timeout)

        # Check that all resources are present in the response
        if len(response.pairs) != len(resource_ids):
            logger.warning(
                "Kessel CheckBulk response is missing some resources: "
                f"{len(response.pairs)} of {len(resource_ids)} resources are present in the response"
            )
            logger.warning(
                f"Expected resource IDs: {resource_ids}\n"
                f"Response resource IDs: {[pair.request.object.resource_id for pair in response.pairs]}"
            )
            return False

        # Check that all resources are allowed
        for pair in response.pairs:
            # If there's an error for this item, treat as denied
            if pair.HasField("error"):
                logger.warning(f"Kessel CheckBulk error for resource: {pair.error.message}")
                return False
            if pair.item.allowed != allowed_pb2.Allowed.ALLOWED_TRUE:
                return False

        return True

    def _check_single_resource_for_update(
        self, subject_ref: subject_reference_pb2.SubjectReference, permission: KesselPermission, resource_id: str
    ) -> bool:
        """Check update permission for a single resource."""
        if permission.resource_permission == "view":
            logger.error("_check_single_resource_for_update called with 'view' permission")
            raise ValueError("Update check cannot be performed with 'view' permission")

        request = check_request_pb2.CheckRequest(
            subject=subject_ref,
            relation=permission.resource_permission,
            object=self._build_object_reference(permission, resource_id),
        )

        response: CheckForUpdateResponse = self.inventory_svc.CheckForUpdate(request, timeout=self.timeout)
        return response.allowed == allowed_pb2.Allowed.ALLOWED_TRUE

    def _check_bulk_resources_for_update(
        self,
        subject_ref: subject_reference_pb2.SubjectReference,
        permission: KesselPermission,
        resource_ids: list[str],
    ) -> bool:
        """Check update permissions for multiple resources. All must be updatable."""
        if not resource_ids:
            raise ValueError("resource_ids can't be empty")

        # CheckBulk doesn't support CheckForUpdate, so we iterate over single resource checks
        for resource_id in resource_ids:
            if not self._check_single_resource_for_update(subject_ref, permission, resource_id):
                return False
        return True

    def ListAllowedWorkspaces(self, current_identity: Identity, relation) -> list[str]:
        # logger.info(f"user identity that reached the kessel lib: {current_identity.user}")
        user_id = (
            current_identity.user.get("user_id")
            if current_identity.user
            else (
                current_identity.service_account.get("client_id") or current_identity.service_account.get("username")
            )
        )
        # logger.info(f"user_id resolved from the identity: {user_id}")
        subject_ref = resource_reference_pb2.ResourceReference(
            resource_type="principal",
            resource_id=f"redhat/{user_id}",  # Platform/IdP/whatever 'redhat' is, probably needs to be parameterized
            reporter=reporter_reference_pb2.ReporterReference(type="rbac"),
        )

        subject = subject_reference_pb2.SubjectReference(
            resource=subject_ref,
        )

        stream = list_workspaces(self.inventory_svc, subject=subject, relation=relation)
        return [workspace.object.resource_id for workspace in stream]

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
