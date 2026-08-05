from __future__ import annotations

from collections.abc import Callable
from collections.abc import Generator
from typing import Any

import pytest
from connexion import FlaskApp
from starlette.testclient import TestClient

from tests.helpers.api_utils import do_request
from tests.helpers.test_utils import USER_IDENTITY


@pytest.fixture(scope="function")
def v2_flask_app(flask_app: FlaskApp) -> Generator[FlaskApp]:
    yield flask_app


@pytest.fixture(scope="function")
def v2_flask_client(v2_flask_app: FlaskApp) -> TestClient:
    return v2_flask_app.test_client()


@pytest.fixture(scope="function")
def v2_api_get(v2_flask_client: TestClient) -> Callable[..., tuple[int, dict]]:
    def _v2_api_get(
        url: str,
        identity: dict[str, Any] = USER_IDENTITY,
        query_parameters: dict[str, Any] | None = None,
        extra_headers: dict[str, Any] | None = None,
    ) -> tuple[int, dict]:
        return do_request(
            v2_flask_client.get, url, identity, query_parameters=query_parameters, extra_headers=extra_headers
        )

    return _v2_api_get
