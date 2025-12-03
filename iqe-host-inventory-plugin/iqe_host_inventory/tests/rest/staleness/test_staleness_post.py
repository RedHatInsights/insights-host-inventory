import logging
from random import randint
from typing import Any

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.api_utils import api_disabled_validation
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.staleness_utils import DAY_SECS
from iqe_host_inventory.utils.staleness_utils import MIN_DELTA
from iqe_host_inventory.utils.staleness_utils import STALENESS_DEFAULTS
from iqe_host_inventory.utils.staleness_utils import STALENESS_LIMITS
from iqe_host_inventory.utils.staleness_utils import TIME_TO_DELETE
from iqe_host_inventory.utils.staleness_utils import TIME_TO_STALE
from iqe_host_inventory.utils.staleness_utils import TIME_TO_STALE_WARNING
from iqe_host_inventory.utils.staleness_utils import gen_staleness_settings
from iqe_host_inventory.utils.staleness_utils import validate_staleness_response
from iqe_host_inventory_api_v7 import StalenessIn

pytestmark = [pytest.mark.backend, pytest.mark.usefixtures("hbi_staleness_cleanup")]
logger = logging.getLogger(__name__)


def test_staleness_create_random_data(
    host_inventory: ApplicationHostInventory, hbi_staleness_defaults: dict[str, int]
) -> None:
    """
    metadata:
      requirements: inv-staleness-post
      assignee: msager
      importance: high
      title: Create staleness settings via POST /account/staleness request
    """

    test_data = gen_staleness_settings()
    logger.info(f"Creating account record with:\n{test_data}")
    response = host_inventory.apis.account_staleness.create_staleness(**test_data).to_dict()
    validate_staleness_response(response, hbi_staleness_defaults, test_data)

    response = host_inventory.apis.account_staleness.get_staleness()
    validate_staleness_response(response, hbi_staleness_defaults, test_data)


@pytest.mark.parametrize(
    "field,value",
    [
        (
            TIME_TO_STALE,
            randint(MIN_DELTA, STALENESS_DEFAULTS[TIME_TO_STALE]),
        ),
        (
            TIME_TO_STALE_WARNING,
            randint(
                STALENESS_DEFAULTS[TIME_TO_STALE] + 1,
                STALENESS_DEFAULTS[TIME_TO_STALE_WARNING],
            ),
        ),
        (
            TIME_TO_DELETE,
            randint(
                STALENESS_DEFAULTS[TIME_TO_STALE_WARNING] + 1,
                STALENESS_LIMITS[TIME_TO_DELETE],
            ),
        ),
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
      requirements: inv-staleness-post
      assignee: msager
      importance: high
      title: Create staleness settings for a single field
    """

    test_data = {field: value}
    logger.info(f"Creating account record with:\n{test_data}")
    response = host_inventory.apis.account_staleness.create_staleness(**test_data).to_dict()
    validate_staleness_response(response, hbi_staleness_defaults, test_data)

    response = host_inventory.apis.account_staleness.get_staleness()
    validate_staleness_response(response, hbi_staleness_defaults, test_data)


def test_staleness_create_all_fields(
    host_inventory: ApplicationHostInventory, hbi_staleness_defaults: dict[str, int]
) -> None:
    """
    metadata:
      requirements: inv-staleness-post
      assignee: msager
      importance: high
      title: Create staleness settings for all fields
    """

    test_data = gen_staleness_settings(want_sample=False)
    logger.info(f"Creating account record with:\n{test_data}")
    response = host_inventory.apis.account_staleness.create_staleness(**test_data).to_dict()
    validate_staleness_response(response, hbi_staleness_defaults, test_data)

    response = host_inventory.apis.account_staleness.get_staleness()
    validate_staleness_response(response, hbi_staleness_defaults, test_data)


@pytest.mark.parametrize(
    "field,value",
    [
        (TIME_TO_STALE, MIN_DELTA),
        (TIME_TO_DELETE, STALENESS_LIMITS[TIME_TO_DELETE]),
    ],
)
def test_staleness_create_min_max(
    host_inventory: ApplicationHostInventory,
    hbi_staleness_defaults: dict[str, int],
    field: str,
    value: int,
) -> None:
    """
    metadata:
      requirements: inv-staleness-post
      assignee: msager
      importance: low
      title: Create staleness settings using min and max allowed deltas
    """

    test_data = {field: value}
    logger.info(f"Creating account record with:\n{test_data}")
    response = host_inventory.apis.account_staleness.create_staleness(**test_data).to_dict()
    validate_staleness_response(response, hbi_staleness_defaults, test_data)

    response = host_inventory.apis.account_staleness.get_staleness()
    validate_staleness_response(response, hbi_staleness_defaults, test_data)


def test_staleness_create_existing_record(host_inventory: ApplicationHostInventory) -> None:
    """
    metadata:
      requirements: inv-staleness-post
      assignee: msager
      importance: low
      negative: true
      title: Attempt to create a new staleness record when one already exists
    """
    test_data = gen_staleness_settings()
    logger.info("Creating account record")
    host_inventory.apis.account_staleness.create_staleness(**test_data)

    with raises_apierror(400, match_message="already exists"):
        host_inventory.apis.account_staleness.create_staleness(**test_data)


@pytest.mark.parametrize(
    "field",
    [
        TIME_TO_STALE,
        TIME_TO_STALE_WARNING,
        TIME_TO_DELETE,
    ],
)
def test_staleness_create_value_too_big(
    host_inventory: ApplicationHostInventory, field: str
) -> None:
    """
    metadata:
      requirements: inv-staleness-post
      assignee: msager
      importance: low
      negative: true
      title: Attempt to create a new staleness record with a value that's too big
    """
    test_data = {field: STALENESS_LIMITS[field] + 1}
    logger.info(f"Creating account record with:\n{test_data}")

    with raises_apierror(400, match_message=f"less than or equal to {STALENESS_LIMITS[field]}"):
        host_inventory.apis.account_staleness.create_staleness(**test_data)


def test_staleness_create_invalid_field(host_inventory: ApplicationHostInventory) -> None:
    """
    metadata:
      requirements: inv-staleness-post
      assignee: msager
      importance: low
      negative: true
      title: Attempt to create a new staleness record with an invalid field
    """
    test_data = {TIME_TO_STALE: DAY_SECS, "bad_field": DAY_SECS}
    logger.info(f"Creating account record with:\n{test_data}")

    with api_disabled_validation(host_inventory.apis.account_staleness.raw_api) as api:
        # TODO: Uncomment this when https://issues.redhat.com/browse/RHINENG-14003 is done
        # with raises_apierror(400, match_message="Unknown field"):
        #    api.api_staleness_create_staleness(test_data)  # type: ignore[arg-type]

        # TODO: And delete these 3 lines (temporary replacement for above)
        api.api_staleness_create_staleness(test_data)  # type: ignore[arg-type]
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
def test_staleness_create_invalid_value(
    host_inventory: ApplicationHostInventory, field: str, value: Any
) -> None:
    """
    metadata:
      requirements: inv-staleness-post
      assignee: str
      importance: low
      negative: true
      title: Attempt to create a new staleness record with an invalid value
    """
    staleness_in = StalenessIn.model_construct(**{field: value})
    logger.info(f"Creating account record with:\n{staleness_in}")

    match_message = ""
    if not isinstance(value, int):
        match_message = "is not of type 'integer'"
    elif value <= 0:
        match_message = "less than the minimum"

    with api_disabled_validation(host_inventory.apis.account_staleness.raw_api) as api:
        with raises_apierror(400, match_message=match_message):
            api.api_staleness_create_staleness(staleness_in)  # type: ignore[arg-type]


def test_staleness_create_proper_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    hbi_staleness_defaults: dict[str, int],
) -> None:
    """
    metadata:
      requirements: inv-staleness-post
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
    response = host_inventory.apis.account_staleness.create_staleness(**test_data).to_dict()
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
def test_staleness_create_invalid_ordering(
    host_inventory: ApplicationHostInventory, settings: dict[str, int]
) -> None:
    """
    Jira: https://issues.redhat.com/browse/ESSNTL-5541

    metadata:
      requirements: inv-staleness-post
      assignee: msager
      importance: low
      negative: true
      title: Attempt to create a staleness record with an invalid sequence of settings
    """
    logger.info(f"Attempting to create account record with unordered settings:\n{settings}")

    with raises_apierror(400, match_message="must be lower than"):
        host_inventory.apis.account_staleness.create_staleness(**settings)
