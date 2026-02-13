"""
==============================================================================
KESSEL-SPECIFIC CONFTEST
==============================================================================

This conftest.py provides fixtures ONLY for Kessel/RBAC v2 workspace tests.
It is separate from the root conftest.py and only affects tests in this directory.

Location: iqe_host_inventory/tests/rest/kessel/conftest.py
Scope: Kessel workspace tests only (test_kessel_*.py files)

==============================================================================
"""

import logging
import time

import pytest
from iqe_rbac_v2_api import ApiException as rbac_v2_exception

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.rbac_utils import RBACInventoryPermission

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session", autouse=True)
def ensure_kessel_workspace_permissions(host_inventory: ApplicationHostInventory) -> None:
    """
    Ensure the default user has RBAC permissions to read/write workspaces.

    This fixture runs once per test session for all Kessel tests and prevents
    random 403 errors when RBAC v2 workspace API requires permissions that
    haven't been initialized yet.

    Background:
    - In stage_proxy and other non-ephemeral environments, the default user
      may not have workspace permissions on first test run
    - This causes intermittent 403 Forbidden errors instead of expected behavior
    - In ephemeral environments, the default user is org admin and already has all permissions

    Solution:
    - Check if user can already access workspaces
    - If 403 error, set up RBAC permissions using existing infrastructure
    - Wait for Kessel sync to propagate permissions
    - Verify permissions work before continuing

    Scope:
    - session: Runs once for all Kessel tests (most efficient)
    - autouse: Automatically runs before any Kessel test

    Related Issues:
    - test_kessel_delete_group was failing with 403 on first run
    - test_kessel_create_group and other tests had similar intermittent failures
    """
    logger.info("=" * 80)
    logger.info("Kessel Tests: Checking workspace RBAC permissions...")

    # Step 1: Check if permissions already exist
    try:
        workspace = host_inventory.apis.workspaces.get_default_workspace()
        logger.info(
            f"✅ User already has workspace permissions (default workspace: {workspace.id})"
        )
        logger.info("=" * 80)
        return
    except rbac_v2_exception as e:
        # Check if this is a permissions error
        is_permission_error = e.status == 403 or "403" in str(e) or "Forbidden" in str(e.body)

        if not is_permission_error:
            # Different error (500, network, etc.) - re-raise
            logger.error(f"❌ Unexpected error accessing workspace API: {e}")
            raise

        logger.warning(f"⚠️  User lacks workspace permissions (HTTP {e.status})")
        logger.info("Setting up RBAC permissions for workspace operations...")

    except Exception as e:
        # Non-API exception (network, etc.)
        logger.error(f"❌ Unexpected error checking workspace permissions: {e}")
        raise

    # Step 2: Set up RBAC permissions
    try:
        logger.info("Creating RBAC group and roles for workspace operations...")

        # Setup groups and hosts permissions (workspace operations are part of groups)
        rbac_group, roles = host_inventory.apis.rbac.setup_rbac_user(
            username=host_inventory.apis.rbac.raw_api.username,
            permissions=[
                # Includes workspace create/read/update via inventory API
                RBACInventoryPermission.GROUPS_ALL,
                # Includes host operations in workspaces
                RBACInventoryPermission.HOSTS_ALL,
                # Allows direct RBAC v2 workspace deletion
                RBACInventoryPermission.RBAC_ADMIN,
            ],
        )

        logger.info(f"✅ Created RBAC group: {rbac_group.uuid}")
        logger.info(f"✅ Created {len(roles)} roles: {[role.uuid for role in roles]}")

    except Exception as e:
        logger.error(f"❌ Failed to create RBAC permissions: {e}")
        pytest.skip(f"Cannot set up workspace permissions for Kessel tests: {e}")

    # Step 3: Wait for Kessel sync (permissions need time to propagate)
    logger.info("Waiting for Kessel to sync permissions...")
    time.sleep(3)  # Give Kessel time to propagate

    # Step 4: Verify permissions work
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            workspace = host_inventory.apis.workspaces.get_default_workspace()
            logger.info(f"✅ Workspace permissions verified (attempt {attempt}/{max_retries})")
            logger.info(f"✅ Default workspace accessible: {workspace.id}")
            logger.info("=" * 80)
            return

        except rbac_v2_exception as e:
            if e.status == 403:
                if attempt < max_retries:
                    logger.warning(
                        f"⚠️  Attempt {attempt}/{max_retries}: Permissions not yet propagated, "
                        f"retrying in 2 seconds..."
                    )
                    time.sleep(2)
                else:
                    logger.error(f"❌ Permissions still not working after {max_retries} attempts")
                    pytest.skip(
                        f"Workspace permissions did not propagate after {max_retries} attempts. "
                        f"RBAC or Kessel may be having sync issues. "
                        f"All Kessel tests will be skipped."
                    )
            else:
                # Different error code
                logger.error(f"❌ Unexpected error verifying permissions: HTTP {e.status}")
                raise

        except Exception as e:
            logger.error(f"❌ Unexpected error verifying permissions: {e}")
            raise

    # Should not reach here due to pytest.skip above, but just in case
    logger.error("❌ Failed to verify workspace permissions")
    pytest.skip("Could not verify workspace permissions for Kessel tests")
