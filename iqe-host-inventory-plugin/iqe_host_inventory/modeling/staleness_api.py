# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from contextlib import suppress
from functools import cached_property
from typing import TYPE_CHECKING
from typing import Any

import attr
import requests
from iqe.base.modeling import BaseEntity

from iqe_host_inventory.modeling.base_api_wrapper import BaseAPIWrapper
from iqe_host_inventory.utils.staleness_utils import extract_staleness_fields

if TYPE_CHECKING:
    from iqe_host_inventory import ApplicationHostInventory

logger = logging.getLogger(__name__)


@attr.s
class AccountStalenessAPIWrapper(BaseEntity):
    @cached_property
    def _host_inventory(self) -> ApplicationHostInventory:
        return self.application.host_inventory

    @cached_property
    def _base_wrapper(self) -> BaseAPIWrapper:
        return BaseAPIWrapper(self.application)

    def _build_staleness_body(
        self,
        conventional_time_to_stale: int | None,
        conventional_time_to_stale_warning: int | None,
        conventional_time_to_delete: int | None,
        immutable_time_to_stale: int | None,
        immutable_time_to_stale_warning: int | None,
        immutable_time_to_delete: int | None,
    ) -> dict[str, int]:
        return {
            k: v
            for k, v in {
                "conventional_time_to_stale": conventional_time_to_stale,
                "conventional_time_to_stale_warning": conventional_time_to_stale_warning,
                "conventional_time_to_delete": conventional_time_to_delete,
                "immutable_time_to_stale": immutable_time_to_stale,
                "immutable_time_to_stale_warning": immutable_time_to_stale_warning,
                "immutable_time_to_delete": immutable_time_to_delete,
            }.items()
            if v is not None
        }

    def get_default_staleness_response(self, **api_kwargs: Any) -> requests.Response:
        with self._host_inventory.apis.measure_time("GET /account/staleness/defaults"):
            return self._base_wrapper.get("/account/staleness/defaults", **api_kwargs)

    def get_default_staleness(self, **api_kwargs: Any) -> dict[str, int]:
        response = self.get_default_staleness_response(**api_kwargs)
        response.raise_for_status()
        return extract_staleness_fields(response.json())

    def get_staleness_response(self, **api_kwargs: Any) -> requests.Response:
        with self._host_inventory.apis.measure_time("GET /account/staleness"):
            return self._base_wrapper.get("/account/staleness", **api_kwargs)

    def get_staleness(self, **api_kwargs: Any) -> dict[str, int]:
        response = self.get_staleness_response(**api_kwargs)
        response.raise_for_status()
        return extract_staleness_fields(response.json())

    def create_staleness(
        self,
        *,
        conventional_time_to_stale: int | None = None,
        conventional_time_to_stale_warning: int | None = None,
        conventional_time_to_delete: int | None = None,
        immutable_time_to_stale: int | None = None,
        immutable_time_to_stale_warning: int | None = None,
        immutable_time_to_delete: int | None = None,
        **api_kwargs: Any,
    ) -> requests.Response:
        body = self._build_staleness_body(
            conventional_time_to_stale,
            conventional_time_to_stale_warning,
            conventional_time_to_delete,
            immutable_time_to_stale,
            immutable_time_to_stale_warning,
            immutable_time_to_delete,
        )
        with self._host_inventory.apis.measure_time("POST /account/staleness"):
            return self._base_wrapper.post("/account/staleness", json=body, **api_kwargs)

    def update_staleness(
        self,
        *,
        conventional_time_to_stale: int | None = None,
        conventional_time_to_stale_warning: int | None = None,
        conventional_time_to_delete: int | None = None,
        immutable_time_to_stale: int | None = None,
        immutable_time_to_stale_warning: int | None = None,
        immutable_time_to_delete: int | None = None,
        **api_kwargs: Any,
    ) -> requests.Response:
        body = self._build_staleness_body(
            conventional_time_to_stale,
            conventional_time_to_stale_warning,
            conventional_time_to_delete,
            immutable_time_to_stale,
            immutable_time_to_stale_warning,
            immutable_time_to_delete,
        )
        with self._host_inventory.apis.measure_time("PATCH /account/staleness"):
            return self._base_wrapper.patch("/account/staleness", json=body, **api_kwargs)

    def delete_staleness(self, **api_kwargs: Any) -> requests.Response:
        with self._host_inventory.apis.measure_time("DELETE /account/staleness"):
            return self._base_wrapper.delete("/account/staleness", **api_kwargs)

    def raw_post_request(self, body: dict[str, Any], **api_kwargs: Any) -> requests.Response:
        """POST an arbitrary, untyped body to /account/staleness.

        For negative-validation tests that need to send malformed or unknown
        fields that the typed ``create_staleness`` signature can't express.
        """
        with self._host_inventory.apis.measure_time("POST /account/staleness"):
            return self._base_wrapper.post("/account/staleness", json=body, **api_kwargs)

    def raw_patch_request(self, body: dict[str, Any], **api_kwargs: Any) -> requests.Response:
        """PATCH an arbitrary, untyped body to /account/staleness.

        For negative-validation tests that need to send malformed or unknown
        fields that the typed ``update_staleness`` signature can't express.
        """
        with self._host_inventory.apis.measure_time("PATCH /account/staleness"):
            return self._base_wrapper.patch("/account/staleness", json=body, **api_kwargs)

    @contextmanager
    def cleanup_before_and_after(self) -> Generator[None]:
        with suppress(requests.RequestException):
            self.delete_staleness()

        try:
            yield
        finally:
            with suppress(requests.RequestException):
                self.delete_staleness()
