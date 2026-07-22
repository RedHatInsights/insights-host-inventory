import json
from types import SimpleNamespace
from typing import cast

import pytest
import requests

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.api_utils import assert_response_org_id_matches


def _application_with_org_id(org_id: str) -> ApplicationHostInventory:
    return cast(
        ApplicationHostInventory,
        SimpleNamespace(user=SimpleNamespace(attributes=SimpleNamespace(org_id=org_id))),
    )


def _json_response(payload: object, *, status_code: int = 200) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response._content = b"" if payload is None else json.dumps(payload).encode()
    response.headers["Content-Type"] = "application/json"
    return response


def test_assert_response_org_id_matches_returns_response_for_matching_org_id() -> None:
    application = _application_with_org_id("12345")
    response = _json_response({"org_id": "12345"})

    assert assert_response_org_id_matches(application, response) is response


def test_assert_response_org_id_matches_raises_for_mismatched_org_id() -> None:
    application = _application_with_org_id("12345")
    response = _json_response({"org_id": "67890"})

    with pytest.raises(AssertionError, match="Critical data leak!"):
        assert_response_org_id_matches(application, response)


def test_assert_response_org_id_matches_ignores_unsuccessful_response() -> None:
    application = _application_with_org_id("12345")
    response = _json_response({"org_id": "67890"}, status_code=403)

    assert assert_response_org_id_matches(application, response) is response
