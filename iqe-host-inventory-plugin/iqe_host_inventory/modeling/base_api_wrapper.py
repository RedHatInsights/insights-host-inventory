# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from typing import Any

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
        # In clowder_smoke the gateway is the direct service, so we use the
        # per-plugin main config; everywhere else the central gateway config
        # lives in app.config.main (scheme/hostname/port per environment).
        if app.config.current_env == "clowder_smoke":
            cfg = app.host_inventory.config.main
        else:
            cfg = app.config.main
        self._base_url = f"{cfg.scheme}://{cfg.hostname}:{cfg.port}/api/inventory/{api_version}"
        logger.debug("BaseAPIWrapper base URL: %s", self._base_url)

    @property
    def client(self) -> RobustSession:
        return self._app.http_client

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.client.get(f"{self._base_url}{path}", **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.client.post(f"{self._base_url}{path}", **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Any:
        return self.client.patch(f"{self._base_url}{path}", **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        return self.client.put(f"{self._base_url}{path}", **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self.client.delete(f"{self._base_url}{path}", **kwargs)
