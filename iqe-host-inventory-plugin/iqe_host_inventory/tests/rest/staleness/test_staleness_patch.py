import logging
from random import randint
from typing import Any

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.api_utils import api_disabled_validation
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.staleness_utils import DAY_SECS
from iqe_host_inventory.utils.staleness_utils import MIN_DELTA
from iqe_host_inventory.utils.staleness_utils import STALENESS_LIMITS
from iqe_host_inventory.utils.staleness_utils import TIME_TO_DELETE
from iqe_host_inventory.utils.staleness_utils import TIME_TO_STALE
from iqe_host_inventory.utils.staleness_utils import TIME_TO_STALE_WARNING
from iqe_host_inventory.utils.staleness_utils import gen_staleness_settings
from iqe_host_inventory.utils.staleness_utils import get_staleness_fields
from iqe_host_inventory.utils.staleness_utils import validate_staleness_response
from iqe_host_inventory_api_v7 import StalenessIn

pytestmark = [pytest.mark.backend, pytest.mark.usefixtures("hbi_staleness_cleanup")]
logger = logging.getLogger(__name__)


def test_staleness_update_random_data(host_inventory: ApplicationHostInventory) -> None:
    """
    metadata:
      requirements: inv-staleness-patch
      assignee: msager
      importance: high
      title: Update staleness settings via PATCH /account/staleness request
    """
    test_data = gen_staleness_settings()
    logger.info(f"Creating account record with:\n{test_data}")
    original = host_inventory.apis.account_staleness.create_staleness(**test_data).to_dict()

    test_data = gen_staleness_settings()
    logger.info(f"Updating account record with:\n{test_data}")
    response = host_inventory.apis.account_staleness.update_staleness(**test_data).to_dict()
    validate_staleness_response(response, original, test_data)

    response = host_inventory.apis.account_staleness.get_staleness()
    validate_staleness_response(response, original, test_data)


@pytest.mark.parametrize("field", get_staleness_fields())
def test_staleness_update_single_field(
    host_inventory: ApplicationHostInventory, field: str
) -> None:
    """
    metadata:
      requirements: inv-staleness-patch
      assignee: msager
      importance: high
      title: Update staleness settings for a single field
    """
    test_data = gen_staleness_settings(want_sample=False)
    logger.info(f"Creating account record with:\n{test_data}")
    original = host_inventory.apis.account_staleness.create_staleness(**test_data).to_dict()

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
    response = host_inventory.apis.account_staleness.update_staleness(**test_data).to_dict()
    validate_staleness_response(response, original, test_data)

    response = host_inventory.apis.account_staleness.get_staleness()
    validate_staleness_response(response, original, test_data)


def test_staleness_update_all_fields(host_inventory: ApplicationHostInventory) -> None:
    """
    metadata:
      requirements: inv-staleness-patch
      assignee: msager
      importance: high
      title: Update staleness settings for all fields
    """
    test_data = gen_staleness_settings()
    logger.info(f"Creating account record with:\n{test_data}")
    original = host_inventory.apis.account_staleness.create_staleness(**test_data).to_dict()

    test_data = gen_staleness_settings(want_sample=False)
    logger.info(f"Updating account record with:\n{test_data}")
    response = host_inventory.apis.account_staleness.update_staleness(**test_data).to_dict()
    validate_staleness_response(response, original, test_data)

    response = host_inventory.apis.account_staleness.get_staleness()
    validate_staleness_response(response, original, test_data)


@pytest.mark.parametrize(
    "field,value",
    [
        (TIME_TO_STALE, MIN_DELTA),
        (TIME_TO_DELETE, STALENESS_LIMITS[TIME_TO_DELETE]),
    ],
)
def test_staleness_update_min_max(
    host_inventory: ApplicationHostInventory, field: str, value: int
) -> None:
    """
    metadata:
      requirements: inv-staleness-patch
      assignee: msager
      importance: low
      title: Update staleness settings using min and max allowed deltas
    """
    test_data = gen_staleness_settings()
    logger.info(f"Creating account record with:\n{test_data}")
    original = host_inventory.apis.account_staleness.create_staleness(**test_data).to_dict()

    test_data = {field: value}
    logger.info(f"Updating account record with:\n{test_data}")
    response = host_inventory.apis.account_staleness.update_staleness(**test_data).to_dict()
    validate_staleness_response(response, original, test_data)

    response = host_inventory.apis.account_staleness.get_staleness()
    validate_staleness_response(response, original, test_data)


def test_staleness_update_nonexistent(host_inventory: ApplicationHostInventory) -> None:
    """
    metadata:
      requirements: inv-staleness-patch
      assignee: msager
      importance: low
      negative: true
      title: Attempt to update a non-existent staleness record
    """
    test_data = gen_staleness_settings()

    with raises_apierror(404, match_message="does not exist"):
        host_inventory.apis.account_staleness.update_staleness(**test_data)


@pytest.mark.parametrize(
    "field",
    [
        TIME_TO_STALE,
        TIME_TO_STALE_WARNING,
        TIME_TO_DELETE,
    ],
)
def test_staleness_update_value_too_big(
    host_inventory: ApplicationHostInventory, field: str
) -> None:
    """
    Jira: https://issues.redhat.com/browse/ESSNTL-5521

    metadata:
      requirements: inv-staleness-patch
      assignee: msager
      importance: low
      negative: true
      title: Attempt to update a staleness record with a value that's too big
    """
    test_data = {field: STALENESS_LIMITS[field] + 1}
    logger.info(f"Updating account record with:\n{test_data}")

    with raises_apierror(400, match_message=f"less than or equal to {STALENESS_LIMITS[field]}"):
        host_inventory.apis.account_staleness.update_staleness(**test_data)


def test_staleness_update_invalid_field(host_inventory: ApplicationHostInventory) -> None:
    """
    Jira: https://issues.redhat.com/browse/ESSNTL-5406

    metadata:
      requirements: inv-staleness-patch
      assignee: msager
      importance: low
      negative: true
      title: Attempt to update a new staleness record with an invalid field
    """
    host_inventory.apis.account_staleness.create_staleness()

    test_data = {TIME_TO_STALE: DAY_SECS, "bad_field": DAY_SECS}
    logger.info(f"Updating account record with:\n{test_data}")

    with api_disabled_validation(host_inventory.apis.account_staleness.raw_api) as api:
        # TODO: Uncomment this when https://issues.redhat.com/browse/RHINENG-14003 is done
        # with raises_apierror(400, match_message="Unknown field"):
        #    api.api_staleness_update_staleness(test_data)
        # TODO: And delete these 3 lines (temporary replacement for above)
        api.api_staleness_update_staleness(test_data)
        settings = host_inventory.apis.account_staleness.get_staleness()
        assert "bad_field" not in settings


@pytest.mark.parametrize(
    "field",
    [
        TIME_TO_STALE,
        TIME_TO_STALE_WARNING,
        TIME_TO_DELETE,
    ],
)
@pytest.mark.parametrize(
    "value",
    [0, "abc", -1, 3.5, [], {}],
    ids=["zero", "string", "negative", "float", "list", "dict"],
)
def test_staleness_update_invalid_value(
    host_inventory: ApplicationHostInventory, field: str, value: Any
) -> None:
    """
    metadata:
      requirements: inv-staleness-patch
      assignee: msager
      importance: low
      negative: true
      title: Attempt to update a new staleness record with an invalid value
    """
    staleness_in = StalenessIn.model_construct(**{field: value})
    logger.info(f"Updating account record with:\n{staleness_in}")

    match_message = ""
    if not isinstance(value, int):
        match_message = "is not of type 'integer'"
    elif value <= 0:
        match_message = "less than the minimum"

    with api_disabled_validation(host_inventory.apis.account_staleness.raw_api) as api:
        with raises_apierror(400, match_message=match_message):
            # todo: figure mypy confusion, maybe create intentionally invalid instance directly
            api.api_staleness_update_staleness(staleness_in)


@pytest.mark.usefixtures("hbi_staleness_secondary_cleanup")
def test_staleness_update_proper_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
) -> None:
    """
    metadata:
      requirements: inv-staleness-patch
      assignee: msager
      importance: high
      title: Verify that updating a staleness record in one account doesn't affect another account
    """
    # Set and stash values from secondary account
    test_data = gen_staleness_settings()
    logger.info(f"Creating secondary account record with:\n{test_data}")
    secondary = host_inventory_secondary.apis.account_staleness.create_staleness(
        **test_data
    ).to_dict()
    logger.info(f"Initial secondary account data:\n{secondary}")

    test_data = gen_staleness_settings()
    logger.info(f"Creating primary account record with:\n{test_data}")
    primary = host_inventory.apis.account_staleness.create_staleness(**test_data).to_dict()

    test_data = gen_staleness_settings()
    logger.info(f"Updating primary account record with:\n{test_data}")
    response = host_inventory.apis.account_staleness.update_staleness(**test_data).to_dict()
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
@pytest.mark.parametrize(
    "settings",
    [
        ({
            TIME_TO_STALE: STALENESS_LIMITS[TIME_TO_STALE],
            TIME_TO_STALE_WARNING: 1,
        }),
        ({TIME_TO_DELETE: 1}),
        ({
            TIME_TO_STALE: 1,
            TIME_TO_STALE_WARNING: 3,
            TIME_TO_DELETE: 2,
        }),
        ({
            TIME_TO_STALE: 2,
            TIME_TO_STALE_WARNING: 1,
            TIME_TO_DELETE: 3,
        }),
        ({
            TIME_TO_STALE: 2,
            TIME_TO_STALE_WARNING: 3,
            TIME_TO_DELETE: 1,
        }),
    ],
)
def test_staleness_update_invalid_ordering(
    host_inventory: ApplicationHostInventory, settings: dict[str, int]
) -> None:
    """
    Jira: https://issues.redhat.com/browse/ESSNTL-5541

    metadata:
      requirements: inv-staleness-patch
      assignee: msager
      importance: low
      negative: true
      title: Attempt to update a staleness record with an invalid sequence of settings
    """
    logger.info(f"Attempting to update account record with unordered settings:\n{settings}")

    with raises_apierror(400, match_message="must be lower than"):
        host_inventory.apis.account_staleness.update_staleness(**settings)
