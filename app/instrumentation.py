from __future__ import annotations

import json
from logging import Logger

from flask import g

from app.auth.identity import Identity
from app.queue import metrics
from app.queue.metrics import event_producer_failure
from app.queue.metrics import event_producer_success
from app.queue.metrics import notification_event_producer_failure
from app.queue.metrics import notification_event_producer_success
from app.queue.metrics import rbac_access_denied
from app.queue.metrics import rbac_fetching_failure
from lib.metrics import pendo_fetching_failure


def message_produced(logger, message, headers):
    value = message.value().decode("utf-8")
    message_dict = json.loads(value)

    # create and update hosts has host
    if "host" in message_dict.keys():
        key = message_dict["host"]["id"]
    # delete host provides has "id" only
    elif "id" in message_dict.keys():
        key = message_dict["id"]
    else:
        key = "Not provided by the caller"

    status = "PRODUCED"
    offset = message.offset()
    partition = message.partition()
    topic = message.topic()

    timestamp = message_dict["timestamp"]

    extra = {
        "status": status,
        "partition": partition,
        "offset": offset,
        "timestamp": timestamp,
        "topic": topic,
        "key": key,
    }

    info_extra = {**extra, "headers": headers}
    info_message = (
        f"Message status={status}, partition={partition}, "
        f"offset={offset}, timestamp={timestamp}, topic={topic}, key={key}"
    )
    logger.info(f"{info_message}, extra={info_extra}")

    debug_message = (
        f"Message partition= {partition} offset={offset} timestamp={timestamp} topic={topic} key={key} value={value}"
    )
    debug_extra = {**extra, "value": value}
    logger.debug(debug_message, extra=debug_extra)

    if "notification" in topic:
        notification_event_producer_success.labels(
            notification_type=dict(headers)["event_type"].decode("utf-8"), topic=topic
        ).inc()
    else:
        event_producer_success.labels(event_type=dict(headers)["event_type"].decode("utf-8"), topic=topic).inc()


def message_not_produced(logger, error, topic, event, key, headers, message=None):
    status = "NOT PRODUCED"
    msg = f"Message status={status}, topic={topic}, key={key}, headers={headers}, error={str(error)}, event={event}"
    if message:
        msg += f", message={message}"

    logger.error(msg)
    if "notification" in topic:
        notification_event_producer_failure.labels(
            notification_type=dict(headers)["event_type"].decode("utf-8"), topic=topic
        ).inc()
    else:
        event_producer_failure.labels(event_type=dict(headers)["event_type"].decode("utf-8"), topic=topic).inc()


def get_control_rule() -> str:
    if hasattr(g, "access_control_rule"):
        return g.access_control_rule
    else:
        return "None"


# delete host
def log_host_delete_succeeded(logger: Logger, host_id: str, control_rule: str | None, sp_fields_to_log: dict) -> None:
    logger.info(
        "Deleted host: %s",
        host_id,
        extra={"access_rule": control_rule, "system_profile": json.dumps(sp_fields_to_log)},
    )


def log_host_delete_failed(logger, host_id, control_rule):
    logger.info(
        "Hostidentity %s already deleted. Delete event not emitted.", host_id, extra={"access_rule": control_rule}
    )


# get host
def log_get_host_list_succeeded(logger, results_list):
    logger.debug("Found hosts: %s", results_list, extra={"access_rule": get_control_rule()})


def log_get_host_list_failed(logger):
    logger.debug("hosts not found", extra={"access_rule": get_control_rule()})


# get single host by insights ID
def log_get_host_exists_succeeded(logger, host_id):
    logger.debug("Found host by insights_id: %s", host_id, extra={"access_rule": get_control_rule()})


# get group
def log_get_group_list_succeeded(logger, results_list):
    logger.info("Found groups: %s", results_list, extra={"access_rule": get_control_rule()})


def log_get_group_list_failed(logger):
    logger.info("Groups not found", extra={"access_rule": get_control_rule()})


# create group
def log_create_group_succeeded(logger, group_id):
    logger.info("Created group: %s", group_id, extra={"access_rule": get_control_rule()})


def log_create_group_failed(logger, group_name):
    logger.info("Error adding group '%s'.", group_name, extra={"access_rule": get_control_rule()})


def log_create_group_not_allowed(logger):
    logger.info("Error adding group due to filtered inventory:groups:write RBAC permission.")


# create host_group_assoc
def log_host_group_add_succeeded(logger, host_id_list, group_id):
    logger.info(
        "Added association between host list %s and group %s",
        host_id_list,
        group_id,
        extra={"access_rule": get_control_rule()},
    )


def log_host_group_add_failed(logger, host_id_list, group_id):
    logger.info(
        "Failed to add association between host list %s and group %s",
        host_id_list,
        group_id,
        extra={"access_rule": get_control_rule()},
    )


# delete group
def log_group_delete_succeeded(logger, group_id, control_rule):
    logger.info("Deleted group: %s", group_id, extra={"access_rule": control_rule})


def log_group_delete_failed(logger, group_id, control_rule):
    logger.info("Group %s already deleted. Delete event not emitted.", group_id, extra={"access_rule": control_rule})


# delete host_group_assoc
def log_host_group_delete_succeeded(logger, host_id, group_id, control_rule):
    logger.info(
        f"Removed association between host {host_id} and group {group_id}", extra={"access_rule": control_rule}
    )


def log_host_group_delete_failed(logger, host_id, group_id, control_rule):
    logger.info(
        f"Failed to remove association between host {host_id} and group {group_id}",
        extra={"access_rule": control_rule},
    )


def log_delete_hosts_from_group_failed(logger):
    logger.info("Failed to remove hosts from group.")


# get tags
def log_get_tags_succeeded(logger, data):
    logger.debug("Found tags: %s", data, extra={"access_rule": get_control_rule()})


def log_get_tags_failed(logger):
    logger.debug("tags not found", extra={"access_rule": get_control_rule()})


# get sap_system
def log_get_sap_system_succeeded(logger, data):
    logger.debug("Found sap_system: %s", data, extra={"access_rule": get_control_rule()})


# get sap_sids
def log_get_sap_sids_succeeded(logger, data):
    logger.debug("Found sap_sids: %s", data, extra={"access_rule": get_control_rule()})


# get operating_system
def log_get_operating_system_succeeded(logger, data):
    logger.debug("Found operating_system: %s", data, extra={"access_rule": get_control_rule()})


# sparse system_profile
def log_get_sparse_system_profile_succeeded(logger, data):
    logger.debug("Found sparse system_profile: %s", data, extra={"access_rule": get_control_rule()})


# add host
def log_add_host_attempt(logger, input_host, sp_fields_to_log, identity: Identity):
    logger.info(
        "Attempting to add host",
        extra={
            "input_host": {
                "account": input_host.account,
                "org_id": input_host.org_id,
                "display_name": input_host.display_name,
                "canonical_facts": input_host.canonical_facts,
                "reporter": input_host.reporter,
                "stale_timestamp": input_host.stale_timestamp.isoformat(),
                "tags": json.dumps(input_host.tags),
                "system_profile": json.dumps(sp_fields_to_log),
            },
            "access_rule": get_control_rule(),
            "auth_type": identity.auth_type,
        },
    )


def log_add_update_host_succeeded(logger, add_result, sp_fields_to_log, output_host):
    metrics.add_host_success.labels(add_result.name, output_host.get("reporter", "null")).inc()  # created vs updated
    # log all the incoming host data except facts and system_profile b/c they can be quite large
    logger.info(
        "Host %s",
        add_result.name,
        extra={
            "host": {i: output_host[i] for i in output_host if i not in ("facts", "system_profile")},
            "system_profile": json.dumps(sp_fields_to_log),
            "access_rule": get_control_rule(),
        },
    )


def log_add_host_failure(logger, message, host_data, sp_fields_to_log):
    logger.exception(
        f"Error adding host: {message}", extra={"host": host_data, "system_profile": json.dumps(sp_fields_to_log)}
    )
    metrics.add_host_failure.labels("InventoryException", host_data.get("reporter", "null")).inc()


# update system profile
def log_update_system_profile_success(logger: Logger, sp_fields_to_log: dict, host_data: dict):
    metrics.update_system_profile_success.inc()
    logger.info(
        "System profile updated for host ID: %s",
        host_data.get("id"),
        extra={"system_profile": json.dumps(sp_fields_to_log)},
    )


def log_update_system_profile_failure(logger, host_data, sp_fields_to_log):
    logger.exception(
        "Error updating system profile for host",
        extra={"host": host_data, "system_profile": json.dumps(sp_fields_to_log)},
    )
    metrics.update_system_profile_failure.labels("InventoryException").inc()


# patch host
def log_patch_host_success(logger, host_id_list):
    logger.info("Patched hosts- hosts: %s", host_id_list)


def log_patch_host_failed(logger, host_id_list):
    logger.debug("Failed to find hosts during patch operation - hosts: %s", host_id_list)


# patch group
def log_patch_group_success(logger, group_id):
    logger.info(f"Patched group: {group_id}")


def log_patch_group_failed(logger, group_id):
    logger.debug(f"Failed to find group during patch operation: {group_id}")


def rbac_failure(logger, error_message=None):
    logger.error("Failed to fetch RBAC permissions: %s", error_message)
    rbac_fetching_failure.inc()


def rbac_permission_denied(logger, required_permission, user_permissions):
    logger.debug(
        "Access denied due to RBAC",
        extra={"required_permission": required_permission, "user_permissions": user_permissions},
    )
    rbac_access_denied.labels(required_permission=required_permission).inc()


def rbac_group_permission_denied(logger, group_ids, required_permission):
    logger.debug(f"You do not have access to the the following groups: {group_ids}")
    rbac_access_denied.labels(required_permission=required_permission).inc()


def log_db_access_failure(logger, message, host_data):
    logger.error("Failure to access database %s", message)
    metrics.db_communication_error.labels("OperationalError", host_data.get("insights_id", message)).inc()


def pendo_failure(logger, error_message=None):
    logger.error("Failed to send Pendo data: %s", error_message)
    pendo_fetching_failure.inc()


# get resource_types
def log_get_resource_type_list_succeeded(logger, results_list):
    logger.debug("Got resource types: %s", results_list, extra={"access_rule": get_control_rule()})


def log_get_resource_type_list_failed(logger):
    logger.debug("Resource types not found", extra={"access_rule": get_control_rule()})


def log_create_staleness_succeeded(logger, staleness_id):
    logger.info("Created account staleness: %s", staleness_id)


def log_patch_staleness_succeeded(logger, staleness_id):
    logger.info(f"Account staleness: {staleness_id} successfully updated.")


def log_create_staleness_failed(logger, org_id):
    logger.info("Failed to create staleness for account with org_id %s", org_id)


# stale host notification
def log_host_stale_notification_succeeded(logger, host_id, control_rule):
    logger.info("Sent Notification for stale host: %s", host_id, extra={"access_rule": control_rule})
