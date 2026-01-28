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
        logger.debug(
            "Kessel.check called",
            extra={
                "identity_type": current_identity.identity_type,
                "org_id": current_identity.org_id,
                "permission_resource_type": permission.resource_type.name if permission.resource_type else None,
                "permission_resource_permission": permission.resource_permission,
                "ids_count": len(ids),
                "ids": ids[:10] if ids else [],
            },
        )
        try:
            # Build the subject reference (the user making the request)
            subject_ref = self._build_subject_reference(current_identity)

            if len(ids) == 1:
                # Single resource check
                result = self._check_single_resource(subject_ref, permission, str(ids[0]))
                logger.debug(f"Kessel.check: single resource check result={result}", extra={"resource_id": ids[0]})
                return result
            elif len(ids) > 1:
                # Bulk check - all resources must be accessible
                result = self._check_bulk_resources(subject_ref, permission, [str(id) for id in ids])
                logger.debug(f"Kessel.check: bulk resource check result={result}", extra={"ids_count": len(ids)})
                return result
            else:
                # No specific IDs - this shouldn't happen in normal Check flow
                logger.warning("Kessel.check called with empty ID list")
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
        logger.debug(
            "Kessel.check_for_update called",
            extra={
                "identity_type": current_identity.identity_type,
                "org_id": current_identity.org_id,
                "permission_resource_type": permission.resource_type.name if permission.resource_type else None,
                "permission_resource_permission": permission.resource_permission,
                "ids_count": len(ids),
                "ids": ids[:10] if ids else [],
            },
        )
        try:
            # Build the subject reference (the user making the request)
            subject_ref = self._build_subject_reference(current_identity)

            if len(ids) == 1:
                # Single resource update check
                result = self._check_single_resource_for_update(subject_ref, permission, ids[0])
                logger.debug(
                    f"Kessel.check_for_update: single resource check result={result}", extra={"resource_id": ids[0]}
                )
                return result
            elif len(ids) > 1:
                # Bulk update check - all resources must be updatable
                result = self._check_bulk_resources_for_update(subject_ref, permission, ids)
                logger.debug(
                    f"Kessel.check_for_update: bulk resource check result={result}", extra={"ids_count": len(ids)}
                )
                return result
            else:
                # No specific IDs - this shouldn't happen in normal check_for_update flow
                logger.warning("Kessel.check_for_update called with empty ID list")
                return False

        except grpc.RpcError as e:
            return self._handle_grpc_error(e, "check_for_update")
        except Exception as e:
            logger.error(f"Kessel check_for_update failed: {str(e)}", exc_info=True)
            return False

    def _build_subject_reference(self, current_identity: Identity) -> subject_reference_pb2.SubjectReference:
        """Build a subject reference for the current user or service account."""
        user_id = None

        # Try to get user_id from user identity
        if getattr(current_identity, "user", None):
            user_id = current_identity.user.get("user_id")
            if not user_id:
                user_id = current_identity.user.get("username")
            logger.debug(
                "_build_subject_reference: resolved user_id from user identity",
                extra={"user_id": user_id, "identity_type": current_identity.identity_type},
            )

        # Fall back to service_account client_id if user_id not found
        if not user_id and getattr(current_identity, "service_account", None):
            user_id = current_identity.service_account.get("client_id")
            logger.debug(
                "_build_subject_reference: resolved user_id from service_account identity",
                extra={"user_id": user_id, "identity_type": current_identity.identity_type},
            )

        if not user_id:
            logger.error(
                "_build_subject_reference: unable to determine user ID from identity",
                extra={
                    "identity_type": current_identity.identity_type,
                    "has_user": hasattr(current_identity, "user"),
                    "has_service_account": hasattr(current_identity, "service_account"),
                },
            )
            raise ValueError("Unable to determine user ID from identity")

        logger.debug(
            "_build_subject_reference: building subject reference",
            extra={"user_id": user_id, "resource_id": f"redhat/{user_id}"},
        )

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
        logger.debug(
            "ListAllowedWorkspaces called",
            extra={
                "identity_type": current_identity.identity_type,
                "org_id": current_identity.org_id,
                "relation": relation,
                "has_user": hasattr(current_identity, "user") and current_identity.user is not None,
                "has_service_account": hasattr(current_identity, "service_account")
                and getattr(current_identity, "service_account", None) is not None,
            },
        )

        # Resolve user_id based on identity type
        user_id = None
        if getattr(current_identity, "user", None):
            user_id = current_identity.user.get("user_id")
            logger.debug(
                "ListAllowedWorkspaces: resolved user_id from user identity",
                extra={"user_id": user_id},
            )
        elif getattr(current_identity, "service_account", None):
            user_id = current_identity.service_account.get("client_id")
            logger.debug(
                "ListAllowedWorkspaces: resolved user_id from service_account identity",
                extra={"user_id": user_id, "service_account": current_identity.service_account},
            )
        else:
            logger.error(
                "ListAllowedWorkspaces: unable to resolve user_id - no user or service_account in identity",
                extra={
                    "identity_type": current_identity.identity_type,
                    "identity_dict": current_identity._asdict() if hasattr(current_identity, "_asdict") else None,
                },
            )

        if not user_id:
            logger.error(
                "ListAllowedWorkspaces: user_id is None or empty, returning empty workspace list",
                extra={"identity_type": current_identity.identity_type},
            )
            return []

        resource_id = f"redhat/{user_id}"
        logger.debug(
            "ListAllowedWorkspaces: building subject reference",
            extra={"resource_id": resource_id, "relation": relation},
        )

        subject_ref = resource_reference_pb2.ResourceReference(
            resource_type="principal",
            resource_id=resource_id,
            reporter=reporter_reference_pb2.ReporterReference(type="rbac"),
        )

        subject = subject_reference_pb2.SubjectReference(
            resource=subject_ref,
        )

        try:
            stream = list_workspaces(self.inventory_svc, subject=subject, relation=relation)
            workspaces = [workspace.object.resource_id for workspace in stream]
            logger.debug(
                "ListAllowedWorkspaces: successfully retrieved workspaces",
                extra={"workspace_count": len(workspaces), "workspaces": workspaces[:10] if workspaces else []},
            )
            return workspaces
        except grpc.RpcError as e:
            logger.error(
                "ListAllowedWorkspaces: gRPC error",
                extra={
                    "error_code": e.code().name if hasattr(e, "code") else None,
                    "error_details": e.details() if hasattr(e, "details") else str(e),
                    "user_id": user_id,
                    "relation": relation,
                },
            )
            return []
        except Exception as e:
            logger.error(
                f"ListAllowedWorkspaces: unexpected error: {str(e)}",
                extra={"user_id": user_id, "relation": relation},
                exc_info=True,
            )
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
