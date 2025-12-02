# mypy: disallow-untyped-defs

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.staleness_utils import extract_staleness_fields
from iqe_host_inventory.utils.staleness_utils import gen_staleness_settings
from iqe_host_inventory.utils.staleness_utils import get_staleness_defaults
from iqe_host_inventory.utils.staleness_utils import validate_staleness_response

pytestmark = [pytest.mark.backend, pytest.mark.usefixtures("hbi_staleness_cleanup")]
logger = logging.getLogger(__name__)


def test_staleness_defaults(hbi_staleness_defaults: dict[str, int]) -> None:
    """
    metadata:
      requirements: inv-staleness-get-defaults
      assignee: msager
      importance: low
      title: Verify staleness default settings via a GET /account/staleness/defaults request
    """
    expected_defaults = get_staleness_defaults()
    response = hbi_staleness_defaults
    validate_staleness_response(response, expected_defaults)


def test_staleness_get_when_unset(
    host_inventory: ApplicationHostInventory, hbi_staleness_defaults: dict[str, int]
) -> None:
    """
    metadata:
      requirements: inv-staleness-get
      assignee: msager
      importance: high
      title: Get staleness settings (defaults) via a GET /account/staleness request when staleness is unset
    """  # NOQA: E501

    logger.info("Retrieving account record with staleness unset")
    response = host_inventory.apis.account_staleness.get_staleness_response()
    assert response.id.actual_instance == "system_default"
    validate_staleness_response(extract_staleness_fields(response), hbi_staleness_defaults)


def test_staleness_get_when_set(host_inventory: ApplicationHostInventory) -> None:
    """
    metadata:
      requirements: inv-staleness-get
      assignee: msager
      importance: high
      title: Get staleness settings via a GET /account/staleness request when staleness is set
    """
    test_data = gen_staleness_settings()
    logger.info(f"Creating account record with:\n{test_data}")
    settings = host_inventory.apis.account_staleness.create_staleness(**test_data)

    response = host_inventory.apis.account_staleness.get_staleness_response()
    assert response.id.actual_instance != "system_default"
    validate_staleness_response(
        extract_staleness_fields(response), extract_staleness_fields(settings), test_data
    )
