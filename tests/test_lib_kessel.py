"""
Unit tests for lib/kessel.py Kessel class.

Tests focus on the bulk resource check functionality and the feature flag
that forces single-resource checks instead of bulk checks.
"""

from unittest.mock import Mock

import pytest
from kessel.inventory.v1beta2 import allowed_pb2
from kessel.inventory.v1beta2 import reporter_reference_pb2
from kessel.inventory.v1beta2 import resource_reference_pb2
from kessel.inventory.v1beta2 import subject_reference_pb2
from kessel.inventory.v1beta2.check_bulk_response_pb2 import CheckBulkResponse

from app.auth.identity import Identity
from app.auth.rbac import KesselPermission
from app.auth.rbac import KesselResourceTypes
from app.auth.rbac import RbacPermission
from lib.kessel import Kessel
from tests.helpers.test_utils import USER_IDENTITY


@pytest.fixture
def kessel_client(mocker) -> Kessel:
    """Create a Kessel client with mocked gRPC connection."""
    # Mock the ClientBuilder to avoid actual gRPC connection
    mock_inventory_svc = Mock()
    mock_channel = Mock()

    mocker.patch("lib.kessel.ClientBuilder")
    mocker.patch.object(Kessel, "__init__", lambda _self, _config: None)

    client = Kessel(None)  # type: ignore[arg-type]
    client.inventory_svc = mock_inventory_svc
    client.channel = mock_channel
    client.timeout = 10.0

    return client


@pytest.fixture
def test_identity() -> Identity:
    """Create a test identity for Kessel checks."""
    return Identity(USER_IDENTITY)


@pytest.fixture
def test_permission() -> KesselPermission:
    """Create a test permission for host resources."""
    return KesselPermission(
        resource_type=KesselResourceTypes.HOST,
        workspace_permission="inventory_host_view",
        resource_permission="view",
        v1_permission=RbacPermission.READ,
    )


@pytest.fixture
def mock_subject_ref() -> subject_reference_pb2.SubjectReference:
    """Create a real SubjectReference protobuf object for testing."""
    resource_ref = resource_reference_pb2.ResourceReference(
        resource_type="principal",
        resource_id="redhat/test_user_id",
        reporter=reporter_reference_pb2.ReporterReference(type="rbac"),
    )
    return subject_reference_pb2.SubjectReference(resource=resource_ref)


class TestCheckBulkResourcesFeatureFlag:
    """Tests for _check_bulk_resources with feature flag control."""

    def test_bulk_check_with_flag_disabled_uses_bulk_api(
        self,
        kessel_client: Kessel,
        test_permission: KesselPermission,
        mock_subject_ref: subject_reference_pb2.SubjectReference,
        mocker,
    ) -> None:
        """
        Test that when feature flag is DISABLED (default), the method uses the bulk gRPC API.

        JIRA: RHINENG-24544
        """
        # Mock feature flag as disabled (default)
        mocker.patch("lib.kessel.get_flag_value", return_value=False)

        resource_ids = ["host-1", "host-2", "host-3"]

        # Mock the bulk CheckBulk response
        mock_response = CheckBulkResponse()
        for resource_id in resource_ids:
            pair = mock_response.pairs.add()
            pair.request.object.resource_id = resource_id
            pair.item.allowed = allowed_pb2.Allowed.ALLOWED_TRUE

        kessel_client.inventory_svc.CheckBulk = Mock(return_value=mock_response)

        # Call the method
        result, unauthorized_ids = kessel_client._check_bulk_resources(
            mock_subject_ref, test_permission, resource_ids, "test"
        )

        # Verify bulk API was called once
        assert kessel_client.inventory_svc.CheckBulk.call_count == 1

        # Verify result
        assert result is True
        assert unauthorized_ids == []

    def test_bulk_check_with_flag_enabled_uses_single_checks(
        self,
        kessel_client: Kessel,
        test_permission: KesselPermission,
        mock_subject_ref: subject_reference_pb2.SubjectReference,
        mocker,
    ) -> None:
        """
        Test that when feature flag is ENABLED, the method uses single-resource checks in a loop.

        JIRA: RHINENG-24544
        """
        # Mock feature flag as enabled
        mocker.patch("lib.kessel.get_flag_value", return_value=True)

        # Mock _check_single_resource to return True for all resources
        mock_check_single = mocker.patch.object(kessel_client, "_check_single_resource", return_value=True)

        resource_ids = ["host-1", "host-2", "host-3"]

        # Call the method
        result, unauthorized_ids = kessel_client._check_bulk_resources(
            mock_subject_ref, test_permission, resource_ids, "test"
        )

        # Verify single check was called for each resource
        assert mock_check_single.call_count == len(resource_ids)

        # Verify it was called with correct parameters for each resource
        for resource_id in resource_ids:
            mock_check_single.assert_any_call(mock_subject_ref, test_permission, resource_id)

        # Verify result
        assert result is True
        assert unauthorized_ids == []

    def test_bulk_check_with_flag_enabled_returns_unauthorized_ids(
        self,
        kessel_client: Kessel,
        test_permission: KesselPermission,
        mock_subject_ref: subject_reference_pb2.SubjectReference,
        mocker,
    ) -> None:
        """
        Test that when feature flag is ENABLED and some resources are unauthorized,
        the method returns the correct unauthorized IDs.

        JIRA: RHINENG-24544
        """
        # Mock feature flag as enabled
        mocker.patch("lib.kessel.get_flag_value", return_value=True)

        resource_ids = ["host-1", "host-2", "host-3"]

        # Mock _check_single_resource: host-2 is unauthorized
        def mock_check_single_fn(_subject_ref, _permission, resource_id):
            return resource_id != "host-2"

        mocker.patch.object(kessel_client, "_check_single_resource", side_effect=mock_check_single_fn)

        # Call the method
        result, unauthorized_ids = kessel_client._check_bulk_resources(
            mock_subject_ref, test_permission, resource_ids, "test"
        )

        # Verify result
        assert result is False  # Not all allowed
        assert unauthorized_ids == ["host-2"]

    def test_bulk_check_with_flag_disabled_returns_unauthorized_ids(
        self,
        kessel_client: Kessel,
        test_permission: KesselPermission,
        mock_subject_ref: subject_reference_pb2.SubjectReference,
        mocker,
    ) -> None:
        """
        Test that when feature flag is DISABLED and some resources are unauthorized,
        the bulk API returns the correct unauthorized IDs.

        JIRA: RHINENG-24544
        """
        # Mock feature flag as disabled
        mocker.patch("lib.kessel.get_flag_value", return_value=False)

        resource_ids = ["host-1", "host-2", "host-3"]

        # Mock the bulk CheckBulk response with host-2 denied
        mock_response = CheckBulkResponse()

        for resource_id in resource_ids:
            pair = mock_response.pairs.add()
            pair.request.object.resource_id = resource_id
            # Deny host-2
            if resource_id == "host-2":
                pair.item.allowed = allowed_pb2.Allowed.ALLOWED_FALSE
            else:
                pair.item.allowed = allowed_pb2.Allowed.ALLOWED_TRUE

        kessel_client.inventory_svc.CheckBulk = Mock(return_value=mock_response)

        # Call the method
        result, unauthorized_ids = kessel_client._check_bulk_resources(
            mock_subject_ref, test_permission, resource_ids, "test"
        )

        # Verify bulk API was called
        assert kessel_client.inventory_svc.CheckBulk.call_count == 1

        # Verify result
        assert result is False
        assert unauthorized_ids == ["host-2"]

    def test_bulk_check_with_flag_enabled_all_unauthorized(
        self,
        kessel_client: Kessel,
        test_permission: KesselPermission,
        mock_subject_ref: subject_reference_pb2.SubjectReference,
        mocker,
    ) -> None:
        """
        Test that when feature flag is ENABLED and all resources are unauthorized,
        all IDs are returned.

        JIRA: RHINENG-24544
        """
        # Mock feature flag as enabled
        mocker.patch("lib.kessel.get_flag_value", return_value=True)

        resource_ids = ["host-1", "host-2", "host-3"]

        # Mock _check_single_resource to return False for all resources
        mocker.patch.object(kessel_client, "_check_single_resource", return_value=False)

        # Call the method
        result, unauthorized_ids = kessel_client._check_bulk_resources(
            mock_subject_ref, test_permission, resource_ids, "test"
        )

        # Verify result
        assert result is False
        assert set(unauthorized_ids) == set(resource_ids)

    def test_bulk_check_with_flag_enabled_logging(
        self,
        kessel_client: Kessel,
        test_permission: KesselPermission,
        mock_subject_ref: subject_reference_pb2.SubjectReference,
        mocker,
    ) -> None:
        """
        Test that debug logging is emitted when feature flag forces single checks.

        JIRA: RHINENG-24544
        """
        # Mock feature flag as enabled
        mocker.patch("lib.kessel.get_flag_value", return_value=True)

        # Mock _check_single_resource
        mocker.patch.object(kessel_client, "_check_single_resource", return_value=True)

        # Mock logger
        mock_logger = mocker.patch("lib.kessel.logger")

        resource_ids = ["host-1", "host-2"]

        # Call the method
        kessel_client._check_bulk_resources(mock_subject_ref, test_permission, resource_ids, "test")

        # Verify debug log was called with expected message
        mock_logger.debug.assert_any_call(
            "Using single-resource checks instead of bulk (forced by feature flag)",
            extra={"resource_ids_count": len(resource_ids)},
        )


class TestCheckMethodIntegration:
    """Integration tests for the check() method with feature flag."""

    def test_check_with_multiple_ids_flag_enabled(
        self, kessel_client: Kessel, test_identity: Identity, test_permission: KesselPermission, mocker
    ) -> None:
        """
        Test that check() with multiple IDs uses _check_bulk_resources which respects the feature flag.

        JIRA: RHINENG-24544
        """
        # Mock feature flag as enabled
        mocker.patch("lib.kessel.get_flag_value", return_value=True)

        # Mock _build_subject_reference
        mock_subject_ref = Mock()
        mocker.patch.object(kessel_client, "_build_subject_reference", return_value=mock_subject_ref)

        # Mock _check_single_resource to track calls
        mock_check_single = mocker.patch.object(kessel_client, "_check_single_resource", return_value=True)

        # Mock CheckBulk to verify it's NOT called
        mock_check_bulk = mocker.Mock()
        kessel_client.inventory_svc.CheckBulk = mock_check_bulk

        resource_ids = ["host-1", "host-2"]

        # Call check() which should delegate to _check_bulk_resources
        result, unauthorized_ids = kessel_client.check(test_identity, test_permission, resource_ids)

        # Verify single checks were used (not bulk API)
        assert mock_check_single.call_count == len(resource_ids)

        # Verify bulk API was NOT called when flag enabled
        mock_check_bulk.assert_not_called()

        assert result is True
        assert unauthorized_ids == []

    def test_check_with_multiple_ids_flag_disabled(
        self,
        kessel_client: Kessel,
        test_identity: Identity,
        test_permission: KesselPermission,
        mock_subject_ref: subject_reference_pb2.SubjectReference,
        mocker,
    ) -> None:
        """
        Test that check() with multiple IDs uses bulk API when feature flag is disabled.

        JIRA: RHINENG-24544
        """
        # Mock feature flag as disabled
        mocker.patch("lib.kessel.get_flag_value", return_value=False)

        # Mock _build_subject_reference
        mocker.patch.object(kessel_client, "_build_subject_reference", return_value=mock_subject_ref)

        # Mock _check_single_resource to verify it's NOT called
        mock_check_single = mocker.patch.object(kessel_client, "_check_single_resource")

        resource_ids = ["host-1", "host-2"]

        # Mock the bulk CheckBulk response
        mock_response = CheckBulkResponse()
        for resource_id in resource_ids:
            pair = mock_response.pairs.add()
            pair.request.object.resource_id = resource_id
            pair.item.allowed = allowed_pb2.Allowed.ALLOWED_TRUE

        kessel_client.inventory_svc.CheckBulk = Mock(return_value=mock_response)

        # Call check()
        result, unauthorized_ids = kessel_client.check(test_identity, test_permission, resource_ids)

        # Verify bulk API was used
        assert kessel_client.inventory_svc.CheckBulk.call_count == 1

        # Verify single-resource checks were NOT called when flag disabled
        mock_check_single.assert_not_called()

        assert result is True
        assert unauthorized_ids == []


class TestCheckBulkResourcesEdgeCases:
    """Edge case tests for _check_bulk_resources."""

    def test_bulk_check_empty_resource_ids_raises_error(
        self,
        kessel_client: Kessel,
        test_permission: KesselPermission,
        mock_subject_ref: subject_reference_pb2.SubjectReference,
    ) -> None:
        """
        Test that passing empty resource_ids raises ValueError.

        JIRA: RHINENG-24544
        """
        with pytest.raises(ValueError, match="resource_ids can't be empty"):
            kessel_client._check_bulk_resources(mock_subject_ref, test_permission, [], "test")

    def test_bulk_check_single_resource_not_affected_by_flag(
        self, kessel_client: Kessel, test_identity: Identity, test_permission: KesselPermission, mocker
    ) -> None:
        """
        Test that single resource check (len=1) bypasses the bulk logic entirely.
        This is handled by check() method, not _check_bulk_resources.

        JIRA: RHINENG-24544
        """
        # Mock feature flag (shouldn't matter for single resource)
        mocker.patch("lib.kessel.get_flag_value", return_value=True)

        # Mock _check_single_resource
        mock_check_single = mocker.patch.object(kessel_client, "_check_single_resource", return_value=True)

        # Call check() with single ID (bypasses _check_bulk_resources)
        result, unauthorized_ids = kessel_client.check(test_identity, test_permission, ["host-1"])

        # Verify _check_single_resource was called directly (not via bulk)
        assert mock_check_single.call_count == 1
        assert result is True
        assert unauthorized_ids == []
