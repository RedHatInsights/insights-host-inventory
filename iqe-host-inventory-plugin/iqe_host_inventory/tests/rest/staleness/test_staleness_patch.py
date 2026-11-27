from __future__ import annotations

import logging
from random import randint

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.staleness_utils import MIN_DELTA
from iqe_host_inventory.utils.staleness_utils import STALENESS_LIMITS
from iqe_host_inventory.utils.staleness_utils import gen_staleness_settings
from iqe_host_inventory.utils.staleness_utils import get_staleness_fields
from iqe_host_inventory.utils.staleness_utils import validate_staleness_response

pytestmark = [pytest.mark.backend, pytest.mark.usefixtures("hbi_staleness_cleanup")]
logger = logging.getLogger(__name__)


@pytest.mark.parametrize("field", get_staleness_fields())
def test_staleness_update_single_field(
    host_inventory: ApplicationHostInventory, field: str
) -> None:
    """
    metadata:
      assignee: msager
      importance: high
      title: Update staleness settings for a single field
    """
    test_data = gen_staleness_settings(want_sample=False)
    logger.info(f"Creating account record with:\n{test_data}")
    original = host_inventory.apis.account_staleness.create_staleness(**test_data).json()

    fields = get_staleness_fields()
    index = fields.index(field)
    if index in (0, 3):  # TIME_TO_STALE
        value = randint(
            MIN_DELTA, min(test_data[fields[index + 1]] - 1, STALENESS_LIMITS[fields[index]])
        )
    elif index in (1, 4):  # TIME_TO_STALE_WARNING
        value = randint(
            test_data[fields[index - 1]] + 1,
            min(test_data[fields[index + 1]] - 1, STALENESS_LIMITS[fields[index]]),
        )
    else:  # TIME_TO_DELETE
        value = randint(test_data[fields[index - 1]] + 1, STALENESS_LIMITS[fields[index]])

    test_data = {field: value}
    logger.info(f"Updating account record with:\n{test_data}")
    response = host_inventory.apis.account_staleness.update_staleness(**test_data).json()
    validate_staleness_response(response, original, test_data)

    response = host_inventory.apis.account_staleness.get_staleness()
    validate_staleness_response(response, original, test_data)


def test_staleness_update_all_fields(host_inventory: ApplicationHostInventory) -> None:
    """
    metadata:
      assignee: msager
      importance: high
      title: Update staleness settings for all fields
    """
    test_data = gen_staleness_settings()
    logger.info(f"Creating account record with:\n{test_data}")
    original = host_inventory.apis.account_staleness.create_staleness(**test_data).json()

    test_data = gen_staleness_settings(want_sample=False)
    logger.info(f"Updating account record with:\n{test_data}")
    response = host_inventory.apis.account_staleness.update_staleness(**test_data).json()
    validate_staleness_response(response, original, test_data)

    response = host_inventory.apis.account_staleness.get_staleness()
    validate_staleness_response(response, original, test_data)


@pytest.mark.usefixtures("hbi_staleness_secondary_cleanup")
def test_staleness_update_proper_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
) -> None:
    """
    metadata:
      assignee: msager
      importance: high
      title: Verify that updating a staleness record in one account doesn't affect another account
    """
    # Set and stash values from secondary account
    test_data = gen_staleness_settings()
    logger.info(f"Creating secondary account record with:\n{test_data}")
    secondary = host_inventory_secondary.apis.account_staleness.create_staleness(
        **test_data
    ).json()
    logger.info(f"Initial secondary account data:\n{secondary}")

    test_data = gen_staleness_settings()
    logger.info(f"Creating primary account record with:\n{test_data}")
    primary = host_inventory.apis.account_staleness.create_staleness(**test_data).json()

    test_data = gen_staleness_settings()
    logger.info(f"Updating primary account record with:\n{test_data}")
    response = host_inventory.apis.account_staleness.update_staleness(**test_data).json()
    validate_staleness_response(response, primary, test_data)

    response = host_inventory.apis.account_staleness.get_staleness()
    logger.info(f"Primary account data:\n{response}")
    validate_staleness_response(response, primary, test_data)

    # Verify that secondary account is unchanged
    response = host_inventory_secondary.apis.account_staleness.get_staleness()
    logger.info(f"Verifying secondary account data is unchanged:\n{secondary}")
    validate_staleness_response(response, secondary)


# Any trivial unordered set is fine.  Could add some additional permutations,
# but this is probably sufficient enough to validate correctness.
