import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.staleness_utils import TIME_TO_DELETE
from iqe_host_inventory.utils.staleness_utils import TIME_TO_STALE
from iqe_host_inventory.utils.staleness_utils import TIME_TO_STALE_WARNING
from iqe_host_inventory.utils.staleness_utils import gen_staleness_settings
from iqe_host_inventory.utils.staleness_utils import validate_staleness_response

pytestmark = [pytest.mark.backend, pytest.mark.usefixtures("hbi_staleness_cleanup")]
logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "field,value",
    [
        (TIME_TO_STALE, 432000),
        (TIME_TO_STALE_WARNING, 864000),
        (TIME_TO_DELETE, 31536000),
    ],
)
def test_staleness_create_single_field(
    host_inventory: ApplicationHostInventory,
    hbi_staleness_defaults: dict[str, int],
    field: str,
    value: int,
) -> None:
    """
    metadata:
      assignee: msager
      importance: high
      title: Create staleness settings for a single field
    """

    test_data = {field: value}
    logger.info(f"Creating account record with:\n{test_data}")
    response = host_inventory.apis.account_staleness.create_staleness(**test_data).json()
    validate_staleness_response(response, hbi_staleness_defaults, test_data)

    response = host_inventory.apis.account_staleness.get_staleness()
    validate_staleness_response(response, hbi_staleness_defaults, test_data)


def test_staleness_create_all_fields(
    host_inventory: ApplicationHostInventory, hbi_staleness_defaults: dict[str, int]
) -> None:
    """
    metadata:
      assignee: msager
      importance: high
      title: Create staleness settings for all fields
    """

    test_data = gen_staleness_settings(want_sample=False)
    logger.info(f"Creating account record with:\n{test_data}")
    response = host_inventory.apis.account_staleness.create_staleness(**test_data).json()
    validate_staleness_response(response, hbi_staleness_defaults, test_data)

    response = host_inventory.apis.account_staleness.get_staleness()
    validate_staleness_response(response, hbi_staleness_defaults, test_data)


def test_staleness_create_proper_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    hbi_staleness_defaults: dict[str, int],
) -> None:
    """
    metadata:
      assignee: msager
      importance: high
      title: Verify that creating a staleness record in one account doesn't affect another account
    """

    # Save values from secondary account
    secondary = host_inventory_secondary.apis.account_staleness.get_staleness()
    logger.info(f"Initial secondary account data:\n{secondary}")

    # Create primary account record
    test_data = gen_staleness_settings()
    logger.info(f"Creating primary account record with:\n{test_data}")
    response = host_inventory.apis.account_staleness.create_staleness(**test_data).json()
    validate_staleness_response(response, hbi_staleness_defaults, test_data)

    response = host_inventory.apis.account_staleness.get_staleness()
    logger.info(f"Primary account data:\n{response}")
    validate_staleness_response(response, hbi_staleness_defaults, test_data)

    # Verify that secondary account is unchanged
    response = host_inventory_secondary.apis.account_staleness.get_staleness()
    logger.info(f"Verifying secondary account data is unchanged:\n{secondary}")
    validate_staleness_response(response, secondary)


# Any trivial unordered set is fine.  Could add some additional permutations,
# but this is probably sufficient enough to validate correctness.
