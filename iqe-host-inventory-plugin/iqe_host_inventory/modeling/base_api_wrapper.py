# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from typing import Any

import requests
from iqe.base.http import RobustSession

if TYPE_CHECKING:
    from iqe.base.application import Application

logger = logging.getLogger(__name__)


class BaseAPIWrapper:
    """HTTP client wrapper for HBI API endpoints that bypasses the apigen layer.

    Uses IQE's ``app.http_client`` (a ``RobustSession``) directly, which already
    handles authentication, retries, and environment configuration.  A URL helper
    prepends the versioned base path so callers only need to supply the path
    relative to ``/api/inventory/{api_version}``.

    This class is version-aware: pass ``api_version="v2"`` for V2 endpoints.
    The default is ``"v1"`` for the V1 API.

    Usage::

        wrapper = BaseAPIWrapper(application)
        response = wrapper.post("/hosts/checkin", json={"insights_id": "..."})
        response.raise_for_status()
        data = response.json()
    """

    def __init__(self, app: Application, api_version: str = "v1") -> None:
        self._app = app
        # Build the base URL from IQE config rather than the apigen client.
        # In clowder_smoke the gateway is the direct service (port required);
        # in Stage/Prod the central gateway has no port in the URL.
        if app.config.current_env == "clowder_smoke":
            cfg = app.host_inventory.config.main
            self._base_url = (
                f"{cfg.scheme}://{cfg.hostname}:{cfg.port}/api/inventory/{api_version}"
            )
        else:
            cfg = app.config.main
            self._base_url = f"{cfg.scheme}://{cfg.hostname}/api/inventory/{api_version}"
        logger.debug("BaseAPIWrapper base URL: %s", self._base_url)

    @property
    def client(self) -> RobustSession:
        return self._app.http_client

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{self._base_url}{path}"
        response = getattr(self.client, method)(url, **kwargs)
        body = kwargs.get("json") or kwargs.get("data")
        request_id = response.headers.get("x-rh-insights-request-id")
        logger.info(
            "REST: %s %s with request body %s and x-rh-insights-request-id=%s",
            method.upper(),
            url,
            body,
            request_id,
        )
        return response

    def get(self, path: str, **kwargs: Any) -> requests.Response:
        return self._request("get", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        return self._request("post", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> requests.Response:
        return self._request("patch", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> requests.Response:
        return self._request("put", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> requests.Response:
        return self._request("delete", path, **kwargs)
