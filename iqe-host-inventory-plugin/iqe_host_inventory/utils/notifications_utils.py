from __future__ import annotations

import logging
from json import loads
from uuid import UUID

import pytest
from iqe.base.application import Application
from iqe.base.datafiles import get_data_path_for_plugin
from iqe_notifications_api import EventLogEntry
from ocdeployer.utils import oc

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import BaseNotificationWrapper
from iqe_host_inventory.modeling.wrappers import DeleteNotificationWrapper
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.modeling.wrappers import RegisteredNotificationWrapper
from iqe_host_inventory.modeling.wrappers import StaleNotificationWrapper
from iqe_host_inventory.utils.datagen_utils import TagDict
from iqe_host_inventory.utils.datagen_utils import generate_operating_system
from iqe_host_inventory.utils.datagen_utils import generate_provider_type
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.tag_utils import assert_tags_found
from iqe_host_inventory.utils.tag_utils import convert_tag_from_nested_to_structured
from iqe_host_inventory_api import GroupOutWithHostCount
from iqe_host_inventory_api import HostOut
from iqe_host_inventory_api import SystemProfile

logger = logging.getLogger(__name__)


def check_notifications_headers(
    headers: dict[str, str], event_type: str, request_id: str | None = None
) -> None:
    assert headers
    assert isinstance(headers, dict)
    expected_keys = {"event_type", "producer", "rh-message-id"}
    if request_id is not None:
        expected_keys.add("request_id")
    assert set(headers.keys()) == expected_keys, set(headers.keys())
    assert headers["event_type"] == event_type, f"{headers['event_type']} != {event_type}"
    if request_id is not None:
        assert headers["request_id"] == request_id, f"{headers['request_id']} != {request_id}"
    assert headers["producer"].startswith("host-inventory"), f"{headers['producer']}"

    try:
        assert UUID(headers["rh-message-id"])
    except ValueError:
        pytest.fail(f"rh-message-id is not in correct format: {headers['rh-message-id']}")


def check_notifications_data(msg: BaseNotificationWrapper, event_type: str, org_id: str) -> None:
    # message root
    assert set(msg.value.keys()) == {
        "org_id",
        "application",
        "bundle",
        "context",
        "events",
        "event_type",
        "timestamp",
    }, set(msg.value.keys())
    assert msg.org_id == org_id, f"{msg.org_id} != {org_id}"
    assert msg.application == "inventory", f"{msg.application} != inventory"
    assert msg.bundle == "rhel", f"{msg.bundle} != rhel"
    assert msg.event_type == event_type, f"{msg.event_type} != {event_type}"
    try:
        assert msg.timestamp
    except ValueError:
        raw = msg.value.get("timestamp")
        pytest.fail(f"Timestamp is not in correct format: {raw}")

    # context
    assert type(msg.context) is dict

    # events
    assert type(msg.events) is list
    assert len(msg.events) == 1
    assert type(msg.events[0]) is dict
    assert set(msg.events[0].keys()) == {"metadata", "payload"}

    # events[0].metadata
    assert msg.metadata == {}

    # events[0].payload
    assert type(msg.payload) is dict


def check_inventory_notifications_data(
    msg: DeleteNotificationWrapper | RegisteredNotificationWrapper | StaleNotificationWrapper,
    event_type: str,
    host: HostWrapper,
    group: GroupOutWithHostCount | None = None,
) -> None:
    check_notifications_data(msg, event_type=event_type, org_id=host.org_id)

    # context
    assert msg.inventory_id == host.id, f"{msg.inventory_id} != {host.id}"
    assert msg.hostname == (host.fqdn or ""), f"{msg.hostname} != {host.fqdn or ''}"
    assert msg.display_name == host.display_name, f"{msg.display_name} != {host.display_name}"

    os = host.system_profile.get("operating_system")
    if os and os["name"].lower() == "rhel":
        assert msg.rhel_version == f"{os['major']}.{os['minor']}", (
            f"{msg.rhel_version} != {os['major']}.{os['minor']}"
        )
    else:
        assert msg.rhel_version == "", f"{msg.rhel_version} != ''"

    # Message tags can have different ordering than host tags
    structured_tags = convert_tag_from_nested_to_structured(msg.tags)
    assert len(structured_tags) == len(host.tags)
    assert_tags_found(
        expected_tags=host.tags, response_tags=structured_tags, check_api_response_count=False
    )

    # events[0].payload
    assert msg.insights_id == (host.insights_id or ""), (
        f"{msg.insights_id} != {host.insights_id or ''}"
    )
    assert msg.subscription_manager_id == (host.subscription_manager_id or ""), (
        f"{msg.subscription_manager_id} != {host.subscription_manager_id or ''}"
    )
    assert msg.satellite_id == (host.satellite_id or ""), (
        f"{msg.satellite_id} != {host.satellite_id or ''}"
    )
    # REVISIT: In the ungrouped case, to use the ungrouped_host_groups() util,
    # we'd need to pass host_inventory and kessel_enabled thru the stack of helpers.
    # Simplify for now by just checking the length (1 with kessel, 0 without).
    # Once kessel is released, we should validate the group attributes, although
    # we'll still need to figure out how to get the ungrouped group id.
    if group is None:
        assert len(msg.groups) <= 1
    else:
        # Update 6/3/25: Kessel is still turned off in the EE, so we don't
        # have group.ungrouped yet.  Use the commented out line below once
        # it's turned on.
        # expected_groups = [{"id": group.id, "name": group.name, "ungrouped": group.ungrouped}]
        expected_groups = [{"id": group.id, "name": group.name}]
        assert msg.groups == expected_groups, f"{msg.groups} != {expected_groups}"


def check_delete_notifications_headers(headers: dict[str, str], request_id: str | None) -> None:
    check_notifications_headers(headers, event_type="system-deleted", request_id=request_id)


def check_delete_notifications_data(
    msg: DeleteNotificationWrapper, host: HostWrapper, group: GroupOutWithHostCount | None = None
) -> None:
    check_inventory_notifications_data(msg, event_type="system-deleted", host=host, group=group)

    # context
    assert set(msg.context.keys()) == {
        "inventory_id",
        "hostname",
        "display_name",
        "rhel_version",
        "tags",
    }, set(msg.context.keys())

    # events[0].payload
    assert set(msg.payload.keys()) == {
        "insights_id",
        "subscription_manager_id",
        "satellite_id",
        "groups",
    }, set(msg.payload.keys())


def check_registered_notifications_headers(
    headers: dict[str, str], request_id: str | None
) -> None:
    check_notifications_headers(headers, event_type="new-system-registered", request_id=request_id)


def check_registered_notifications_data(
    msg: RegisteredNotificationWrapper, host: HostWrapper, base_url: str
) -> None:
    check_inventory_notifications_data(msg, event_type="new-system-registered", host=host)

    # context
    assert set(msg.context.keys()) == {
        "inventory_id",
        "hostname",
        "display_name",
        "rhel_version",
        "tags",
        "host_url",
    }, set(msg.context.keys())

    expected_url = f"{base_url}/insights/inventory/{host.id}"
    assert msg.host_url == expected_url, f"{msg.host_url} != {expected_url}"

    # events[0].payload
    assert set(msg.payload.keys()) == {
        "insights_id",
        "subscription_manager_id",
        "satellite_id",
        "groups",
        "reporter",
        "system_check_in",
    }, set(msg.payload.keys())
    assert msg.reporter == host.reporter, f"{msg.reporter} != {host.reporter}"
    assert msg.system_check_in == host.created.isoformat(), (
        f"{msg.system_check_in} != {host.created.isoformat()}"
    )


def check_stale_notifications_headers(headers: dict[str, str]) -> None:
    check_notifications_headers(headers, event_type="system-became-stale")


def check_stale_notifications_data(
    msg: StaleNotificationWrapper,
    host: HostWrapper,
    group: GroupOutWithHostCount | None,
    base_url: str,
) -> None:
    check_inventory_notifications_data(
        msg, event_type="system-became-stale", host=host, group=group
    )

    # context
    assert set(msg.context.keys()) == {
        "inventory_id",
        "hostname",
        "display_name",
        "rhel_version",
        "tags",
        "host_url",
    }, set(msg.context.keys())

    expected_url = f"{base_url}/insights/inventory/{host.id}"
    assert msg.host_url == expected_url, f"{msg.host_url} != {expected_url}"

    # events[0].payload
    assert set(msg.payload.keys()) == {
        "insights_id",
        "subscription_manager_id",
        "satellite_id",
        "groups",
    }, set(msg.payload.keys())


def get_events(
    application: Application,
    *,
    event_type: str | None = None,
    include_actions: bool = True,
    include_details: bool = False,
    include_payload: bool = True,
    **api_kwargs,
) -> list[EventLogEntry]:
    """
    Propagation of events is occasionally slow in Stage and Prod for some services. I didn't notice
    it with Inventory, but we may need to add polling if it becomes an issue.
    """
    return application.notifications.rest_client_notifications.default_api.event_resource_v1_get_events(  # noqa: E501
        event_type_display_name=event_type,
        include_actions=include_actions,
        include_details=include_details,
        include_payload=include_payload,
        **api_kwargs,
    ).data


def filter_events_by_inventory_id(
    events: list[EventLogEntry], inventory_id: str
) -> list[EventLogEntry]:
    filtered_events = []
    for event in events:
        payload = loads(event.payload)
        if payload["context"]["inventory_id"] == inventory_id:
            filtered_events.append(event)
    return filtered_events


def check_event_log(
    application: Application,
    *,
    inventory_id: str,
    event_type: str,
) -> EventLogEntry:
    """
    Example event from the event log:
    {
      "id": "aa96b5c0-43f7-4e5b-9abc-759cd1da3241",
      "created": "2024-08-21T09:28:23.328446",
      "bundle": "Red Hat Enterprise Linux",
      "application": "Inventory",
      "event_type": "System deleted",
      "payload": <The entire notification kafka message sent by HBI, formatted as a string>,
      "actions": [
        {
          "id": "4a73eaaf-8bd9-419d-b20b-d67a4abbc412",
          "endpoint_type": "email_subscription",
          "endpoint_sub_type": null,
          "invocation_result": true,
          "status": "SUCCESS",
          "endpoint_id": "85c44e24-271d-484b-8376-473500d5bfd6",
          "details": {
            "type": "com.redhat.console.notification.toCamel.email_subscription",
            "target": null,
            "outcome": "Event 4a73eaaf-8bd9-419d-b20b-d67a4abbc412 sent successfully"
          }
        }
      ]
    }
    """
    all_events = get_events(application, event_type=event_type)
    filtered_events = filter_events_by_inventory_id(all_events, inventory_id)
    assert len(filtered_events) == 1
    my_event = filtered_events[0]

    assert my_event.bundle == "Red Hat Enterprise Linux"
    assert my_event.application == "Inventory"
    assert my_event.event_type == event_type

    # In Stage there is a mandatory behavior group called "Drawer" which pushes all events to a
    # drawer as well. Drawer is a component which shows the notifications in UI in red bell icon.
    # TODO: Always check for exactly 2 actions once the "Drawer" is deployed to Prod
    assert len(my_event.actions) <= 2
    endpoint_types: set[str] = set()
    for action in my_event.actions:
        assert action.status == "SUCCESS"
        endpoint_types.add(action.endpoint_type)

    if len(my_event.actions) == 1:
        assert endpoint_types == {"email_subscription"}
    else:
        assert endpoint_types == {"email_subscription", "drawer"}

    return my_event


def check_event_log_delete(
    application: Application, host: HostOut, tags: list[TagDict], system_profile: SystemProfile
) -> None:
    event = check_event_log(application, inventory_id=host.id, event_type="System deleted")

    event_payload = loads(event.payload)
    notification_wrapper = DeleteNotificationWrapper.from_json_event(event_payload)

    host_wrapper = HostWrapper(host.to_dict())
    host_wrapper.tags = tags
    host_wrapper.system_profile = system_profile.to_dict()

    check_delete_notifications_data(notification_wrapper, host_wrapper)


def check_event_log_registered(
    application: Application,
    host: HostOut,
    tags: list[TagDict],
    system_profile: SystemProfile,
    base_url: str,
) -> None:
    event = check_event_log(application, inventory_id=host.id, event_type="New system registered")

    event_payload = loads(event.payload)
    notification_wrapper = RegisteredNotificationWrapper.from_json_event(event_payload)

    host_wrapper = HostWrapper(host.to_dict())
    host_wrapper.tags = tags
    host_wrapper.system_profile = system_profile.to_dict()

    check_registered_notifications_data(notification_wrapper, host_wrapper, base_url=base_url)


def check_event_log_stale(
    application: Application,
    host: HostOut,
    tags: list[TagDict],
    system_profile: SystemProfile,
    base_url: str,
) -> None:
    event = check_event_log(application, inventory_id=host.id, event_type="System became stale")

    event_payload = loads(event.payload)
    notification_wrapper = StaleNotificationWrapper.from_json_event(event_payload)

    host_wrapper = HostWrapper(host.to_dict())
    host_wrapper.tags = tags
    host_wrapper.system_profile = system_profile.to_dict()

    check_stale_notifications_data(
        notification_wrapper, host_wrapper, group=None, base_url=base_url
    )


def create_host_data_for_notification_tests(
    host_inventory: ApplicationHostInventory,
    host_type: str,
    os_name: str,
) -> dict:
    """
    Creates host_data for testing delete or register notifications based on the parameters.

    :param ApplicationHostInventory host_inventory: host_inventory object
    :param str host_type: 'minimal' or 'complete'
    :param str os_name: 'rhel' or 'centos'
    :return: dict
    """
    if host_type == "minimal":
        host_data = host_inventory.datagen.create_minimal_host_data(
            provider_id=generate_uuid(), provider_type=generate_provider_type()
        )
    else:
        host_data = host_inventory.datagen.create_complete_host_data()
        if os_name == "rhel":
            host_data["system_profile"]["operating_system"] = generate_operating_system("RHEL")
        else:
            host_data["system_profile"]["operating_system"] = generate_operating_system(
                "CentOS Linux"
            )
    return host_data


def execute_stale_host_notification():
    yaml_file = str(
        get_data_path_for_plugin("host_inventory").joinpath("start-stale-host-notification.yaml")
    )

    logger.info("Executing the stale host notification job...")
    job_invocation = oc("apply", "-f", yaml_file, "-o", "name").stdout.decode("utf-8").strip()

    logger.info("Getting the stale host notification job name")
    jobs = oc("get", "job", "-o", "name").stdout.decode("utf-8").split("\n")
    job = next(job for job in jobs if "host-inventory-stale-host-notification" in job)

    logger.info("Waiting for the stale host notification job to finish")
    oc("wait", "--for=condition=complete", "--timeout=3m", job)

    logger.info("Deleting the stale host notification job")
    oc("delete", job)
    oc("delete", job_invocation)


def get_email_recipient(application: Application, digest: bool = False) -> str:
    recipient_token = "insights-qe+insights-inventory-qe-notifications"

    if digest:
        recipient_token += "-digest"

    if "stage" in application.config.current_env.lower():
        recipient_token += "+stage"

    return recipient_token + "@redhat.com"
