from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

from iqe_bindings.v7.integrations_v1.exceptions import ApiException as IntegrationsApiException
from iqe_bindings.v7.notifications_v1.exceptions import ApiException as NotificationsApiException
from iqe_bindings.v7.notifications_v1.models.create_behavior_group_request import (
    CreateBehaviorGroupRequest,
)

from iqe_host_inventory.utils.email_utils import Email

if TYPE_CHECKING:
    from iqe_host_inventory import ApplicationHostInventory

log = logging.getLogger(__name__)


class NotificationsEmailAlert:
    """Sets up and tears down a Notifications behavior group + email integration
    for a given event type and bundle, using direct iqe-bindings API calls."""

    def __init__(
        self,
        host_inventory: ApplicationHostInventory,
        *,
        event_name: str,
        bundle_name: str = "rhel",
    ):
        self._host_inventory = host_inventory
        self._notifications_api = host_inventory.v7_notifications_v1.default_api

        try:
            self.bundle = self._notifications_api.notification_resource_v1_get_bundle_by_name(
                bundle_name
            )
        except NotificationsApiException:
            log.error(f"Notifications bundle '{bundle_name}' could not be fetched.")
            raise

        event_page = self._notifications_api.notification_resource_v1_get_event_types(
            limit=100, event_type_name=event_name, bundle_id=self.bundle.id
        )
        if not event_page.data:
            raise ValueError(f"Event Type '{event_name}' not found.")
        self.event = event_page.data[0]

        bg_name = f"IQE_BG_{datetime.datetime.now(tz=datetime.UTC).strftime('%m-%dT%H:%M:%S.%f')}"
        self._behavior_group = (
            self._notifications_api.notification_resource_v1_create_behavior_group(
                create_behavior_group_request=CreateBehaviorGroupRequest(
                    bundle_id=self.bundle.id, display_name=bg_name
                )
            )
        )

        email = Email(host_inventory)
        self._integration = email.create_sample_integration()

    def notification_setup_before_trigger_event(self):
        self._notifications_api.notification_resource_v1_update_behavior_group_actions(
            self._behavior_group.id, request_body=[self._integration.id]
        )

        existing_bgs = self._notifications_api.notification_resource_v1_get_linked_behavior_groups(
            event_type_id=self.event.id
        )
        bg_ids = [bg.id for bg in existing_bgs] + [self._behavior_group.id]

        self._notifications_api.notification_resource_v1_update_event_type_behaviors(
            event_type_id=self.event.id, request_body=bg_ids
        )

    def clean_up(self):
        try:
            existing_bgs = (
                self._notifications_api.notification_resource_v1_get_linked_behavior_groups(
                    event_type_id=self.event.id
                )
            )
            remaining = [bg.id for bg in existing_bgs if bg.id != self._behavior_group.id]
            self._notifications_api.notification_resource_v1_update_event_type_behaviors(
                event_type_id=self.event.id, request_body=remaining
            )
        except NotificationsApiException as e:
            log.warning(f"Failed to unlink behavior group from event type: {e.status}: {e.body}")

        try:
            self._notifications_api.notification_resource_v1_delete_behavior_group(
                id=self._behavior_group.id
            )
        except NotificationsApiException as e:
            log.warning(f"Failed to delete behavior group: {e.status}: {e.body}")

        if self._integration:
            try:
                integrations_api = self._host_inventory.v7_integrations_v1.default_api
                integrations_api.endpoint_resource_v1_delete_endpoint(id=self._integration.id)
            except IntegrationsApiException as e:
                log.warning(f"Failed to delete integration: {e.status}: {e.body}")
