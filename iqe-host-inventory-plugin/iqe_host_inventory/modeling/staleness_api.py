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
from iqe.base.modeling import BaseEntity

from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.api_utils import check_org_id
from iqe_host_inventory.utils.staleness_utils import extract_staleness_fields
from iqe_host_inventory_api_v7 import AccountsStalenessApi
from iqe_host_inventory_api_v7 import ApiException
from iqe_host_inventory_api_v7 import StalenessIn
from iqe_host_inventory_api_v7 import StalenessOutput

if TYPE_CHECKING:
    from iqe_host_inventory import ApplicationHostInventory

logger = logging.getLogger(__name__)


@attr.s
class AccountStalenessAPIWrapper(BaseEntity):
    @cached_property
    def _host_inventory(self) -> ApplicationHostInventory:
        return self.application.host_inventory

    @cached_property
    def raw_api(self) -> AccountsStalenessApi:
        """
        Raw auto-generated OpenAPI client.
        Use high level API wrapper methods instead of this raw API client.
        Outside this class this should be used only for negative validation testing.
        """
        return self._host_inventory.api_v7.accounts_staleness_api

    @check_org_id
    def get_default_staleness_response(self, **api_kwargs: Any) -> StalenessOutput:
        """Retrieve the default staleness settings from GET /account/staleness/defaults

        :return StalenessOutput: Default staleness (response from GET /account/staleness/defaults)
        """
        return self.raw_api.api_staleness_get_default_staleness(**api_kwargs)

    def get_default_staleness(self, **api_kwargs: Any) -> dict[str, int]:
        """Retrieve the default staleness settings and extract staleness fields from the response.

        :return dict[str, int]: Extracted staleness fields from the retrieved default staleness
        """
        return extract_staleness_fields(self.get_default_staleness_response(**api_kwargs))

    @check_org_id
    def get_staleness_response(self, **api_kwargs: Any) -> StalenessOutput:
        """Retrieve the current staleness settings from GET /account/staleness

        :return StalenessOutput: Current staleness (response from GET /account/staleness)
        """
        return self.raw_api.api_staleness_get_staleness(**api_kwargs)

    def get_staleness(self, **api_kwargs: Any) -> dict[str, int]:
        """Retrieve the current staleness settings and extract staleness fields from the response.

        :return dict[str, int]: Extracted staleness fields from the retrieved current staleness
        """
        return extract_staleness_fields(self.get_staleness_response(**api_kwargs))

    @check_org_id
    def create_staleness(
        self,
        *,
        conventional_time_to_stale: int | None = None,
        conventional_time_to_stale_warning: int | None = None,
        conventional_time_to_delete: int | None = None,
        immutable_time_to_stale: int | None = None,
        immutable_time_to_stale_warning: int | None = None,
        immutable_time_to_delete: int | None = None,
        wait_for_host_events: bool = True,
        **api_kwargs: Any,
    ) -> StalenessOutput:
        """Create a staleness record. Currently, these values can only be set at the account level.

        :param int conventional_time_to_stale: host state fresh->stale in seconds
        :param int conventional_time_to_stale_warning: host state stale->stale warning in seconds
        :param int conventional_time_to_delete: host state stale warning->culled in seconds
        :param int immutable_time_to_stale: host state fresh->stale in seconds
        :param int immutable_time_to_stale_warning: host state stale->stale warning in seconds
        :param int immutable_time_to_delete: host state stale warning->culled in seconds
        :param bool wait_for_host_events: whether to wait for kafka host events
            Updates to staleness will generate host events with updated staleness timestamps for
            all hosts. If you don't read these events now (by using this parameter), it is possible
            that subsequent `kafka.create_hosts` will return these staleness events instead of the
            new updated events.
            Default: True, but the waiting will happen only if we are in an ephemeral environment
        :return StalenessOutput: Created staleness (response from POST /account/staleness)
        """
        staleness_in = StalenessIn(
            conventional_time_to_stale=conventional_time_to_stale,
            conventional_time_to_stale_warning=conventional_time_to_stale_warning,
            conventional_time_to_delete=conventional_time_to_delete,
            immutable_time_to_stale=immutable_time_to_stale,
            immutable_time_to_stale_warning=immutable_time_to_stale_warning,
            immutable_time_to_delete=immutable_time_to_delete,
        )
        if wait_for_host_events:
            with self.wait_for_host_events():
                return self.raw_api.api_staleness_create_staleness(staleness_in, **api_kwargs)
        return self.raw_api.api_staleness_create_staleness(staleness_in, **api_kwargs)

    @check_org_id
    def update_staleness(
        self,
        *,
        conventional_time_to_stale: int | None = None,
        conventional_time_to_stale_warning: int | None = None,
        conventional_time_to_delete: int | None = None,
        immutable_time_to_stale: int | None = None,
        immutable_time_to_stale_warning: int | None = None,
        immutable_time_to_delete: int | None = None,
        wait_for_host_events: bool = True,
        **api_kwargs: Any,
    ) -> StalenessOutput:
        """Update the staleness record.

        :param int conventional_time_to_stale: host state fresh->stale in seconds
        :param int conventional_time_to_stale_warning: host state stale->stale warning in seconds
        :param int conventional_time_to_delete: host state stale warning->culled in seconds
        :param int immutable_time_to_stale: host state fresh->stale in seconds
        :param int immutable_time_to_stale_warning: host state stale->stale warning in seconds
        :param int immutable_time_to_delete: host state stale warning->culled in seconds
        :param bool wait_for_host_events: whether to wait for kafka host events
            Updates to staleness will generate host events with updated staleness timestamps for
            all hosts. If you don't read these events now (by using this parameter), it is possible
            that subsequent `kafka.create_hosts` will return these staleness events instead of the
            new updated events.
            Default: True, but the waiting will happen only if we are in an ephemeral environment
        :return StalenessOutput: Updated staleness (response from PATCH /account/staleness)
        """
        staleness_in = StalenessIn(
            conventional_time_to_stale=conventional_time_to_stale,
            conventional_time_to_stale_warning=conventional_time_to_stale_warning,
            conventional_time_to_delete=conventional_time_to_delete,
            immutable_time_to_stale=immutable_time_to_stale,
            immutable_time_to_stale_warning=immutable_time_to_stale_warning,
            immutable_time_to_delete=immutable_time_to_delete,
        )

        if wait_for_host_events:
            with self.wait_for_host_events():
                return self.raw_api.api_staleness_update_staleness(staleness_in, **api_kwargs)
        return self.raw_api.api_staleness_update_staleness(staleness_in, **api_kwargs)

    @check_org_id
    def delete_staleness(self, wait_for_host_events: bool = True, **api_kwargs: Any) -> None:
        """Delete the staleness record.

        :param bool wait_for_host_events: whether to wait for kafka host events
            Updates to staleness will generate host events with updated staleness timestamps for
            all hosts. If you don't read these events now (by using this parameter), it is possible
            that subsequent `kafka.create_hosts` will return these staleness events instead of the
            new updated events.
            Default: True, but the waiting will happen only if we are in an ephemeral environment
        :return None:
        """
        if wait_for_host_events:
            with self.wait_for_host_events():
                return self.raw_api.api_staleness_delete_staleness(**api_kwargs)
        return self.raw_api.api_staleness_delete_staleness(**api_kwargs)

    @contextmanager
    def cleanup_before_and_after(self) -> Generator[None]:
        with suppress(ApiException):
            self.delete_staleness()

        yield

        with suppress(ApiException):
            self.delete_staleness()

    @contextmanager
    def wait_for_host_events(self) -> Generator[None]:
        if not self.application.user_provider_keycloak:
            # Skip if we are not in an ephemeral environment
            yield
            return

        # Go through all kafka messages to prevent conflicts when waiting for host events
        # Unfortunately, this doesn't work: https://issues.redhat.com/browse/IQE-3555
        self._host_inventory.kafka._consumer.mini_drain()

        hosts = self._host_inventory.apis.hosts.get_all_hosts()
        values = [host.insights_id for host in hosts]

        yield

        if values:
            self._host_inventory.kafka.wait_for_filtered_host_messages(
                HostWrapper.insights_id, values
            )
