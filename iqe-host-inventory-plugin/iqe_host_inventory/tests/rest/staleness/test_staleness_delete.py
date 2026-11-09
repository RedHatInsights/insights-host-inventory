from __future__ import annotations

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.staleness_utils import extract_staleness_fields
from iqe_host_inventory.utils.staleness_utils import gen_staleness_settings
from iqe_host_inventory.utils.staleness_utils import validate_staleness_response

pytestmark = [pytest.mark.backend, pytest.mark.usefixtures("hbi_staleness_cleanup")]
logger = logging.getLogger(__name__)


def test_staleness_delete(host_inventory: ApplicationHostInventory) -> None:
    """
    metadata:
      assignee: msager
      importance: high
      title: Delete staleness settings via DELETE /account/staleness request
    """
    test_data = gen_staleness_settings()
    logger.info(f"Creating account record with:\n{test_data}")
    host_inventory.apis.account_staleness.create_staleness(**test_data)

    response = host_inventory.apis.account_staleness.get_staleness_response()
    assert response.json()["id"] != "system_default"

    logger.info("Deleting account record")
    host_inventory.apis.account_staleness.delete_staleness()

    response = host_inventory.apis.account_staleness.get_staleness_response()
    assert response.json()["id"] == "system_default"


@pytest.mark.usefixtures("hbi_staleness_secondary_cleanup")
def test_staleness_delete_proper_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
) -> None:
    """
    metadata:
      assignee: msager
      importance: high
      title: Verify that updating a staleness record in one account doesn't affect another account

    """
    # Create primary and verify existence
    test_data = gen_staleness_settings()
    logger.info(f"Creating primary account record with:\n{test_data}")
    host_inventory.apis.account_staleness.create_staleness(**test_data)

    response = host_inventory.apis.account_staleness.get_staleness_response()
    assert response.json()["id"] != "system_default"

    # Create secondary and verify existence
    test_data = gen_staleness_settings()
    logger.info(f"Creating secondary account record with:\n{test_data}")
    host_inventory_secondary.apis.account_staleness.create_staleness(**test_data)

    secondary = host_inventory_secondary.apis.account_staleness.get_staleness_response()
    assert secondary.json()["id"] != "system_default"

    # Delete primary and verify it doesn't exist
    logger.info("Deleting primary account record")
    host_inventory.apis.account_staleness.delete_staleness()

    response = host_inventory.apis.account_staleness.get_staleness_response()
    assert response.json()["id"] == "system_default"

    # Verify secondary still exists
    logger.info("Verifying secondary account record still exists")
    response = host_inventory_secondary.apis.account_staleness.get_staleness_response()
    assert response.json()["id"] != "system_default"
    validate_staleness_response(
        extract_staleness_fields(response.json()), extract_staleness_fields(secondary.json())
    )
