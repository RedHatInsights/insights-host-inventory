import uuid
from enum import Enum

import flask
import sqlalchemy
import ujson
import re
from flask_api import status
from marshmallow import ValidationError
from sqlalchemy.orm.base import instance_state

from api import api_operation
from api import metrics
from app import db
from app import events
from app.auth import current_identity
from app.exceptions import InventoryException
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from app.models import HostSchema
from app.models import PatchHostSchema
from app.payload_tracker import get_payload_tracker
from app.payload_tracker import PayloadTrackerContext
from app.payload_tracker import PayloadTrackerProcessingContext
from tasks import emit_event


TAG_OPERATIONS = ("apply", "remove")
FactOperations = Enum("FactOperations", ["merge", "replace"])

# These are the "elevated" canonical facts that are
# given priority in the host deduplication process.
# NOTE: The order of this tuple is important.  The order defines
# the priority.
ELEVATED_CANONICAL_FACT_FIELDS = ("insights_id", "subscription_manager_id")


logger = get_logger(__name__)


@api_operation
@metrics.api_request_time.time()
def add_host_list(host_list):
    response_host_list = []
    number_of_errors = 0

    payload_tracker = get_payload_tracker(account=current_identity.account_number, payload_id=threadctx.request_id)

    with PayloadTrackerContext(payload_tracker, received_status_message="add host operation"):

        for host in host_list:
            try:
                with PayloadTrackerProcessingContext(
                    payload_tracker, processing_status_message="adding/updating host"
                ) as payload_tracker_processing_ctx:
                    (host, status_code) = _add_host(host)

                    response_host_list.append({"status": status_code, "host": host})
                    payload_tracker_processing_ctx.inventory_id = host["id"]
            except InventoryException as e:
                number_of_errors += 1
                logger.exception("Error adding host", extra={"host": host})
                response_host_list.append({**e.to_json(), "host": host})
            except ValidationError as e:
                number_of_errors += 1
                logger.exception("Input validation error while adding host", extra={"host": host})
                response_host_list.append(
                    {"status": 400, "title": "Bad Request", "detail": str(e.messages), "type": "unknown", "host": host}
                )
            except Exception:
                number_of_errors += 1
                logger.exception("Error adding host", extra={"host": host})
                response_host_list.append(
                    {
                        "status": 500,
                        "title": "Error",
                        "type": "unknown",
                        "detail": "Could not complete operation",
                        "host": host,
                    }
                )

        response = {"total": len(response_host_list), "errors": number_of_errors, "data": response_host_list}
        return _build_json_response(response, status=207)


def _add_host(host):
    """
    Add or update a host

    Required parameters:
     - at least one of the canonical facts fields is required
     - account number
    """
    validated_input_host_dict = HostSchema(strict=True).load(host)

    input_host = Host.from_json(validated_input_host_dict.data)

    if not current_identity.is_trusted_system and current_identity.account_number != input_host.account:
        raise InventoryException(
            title="Invalid request",
            detail="The account number associated with the user does not match the account number associated with the "
            "host",
        )

    existing_host = find_existing_host(input_host.account, input_host.canonical_facts)

    if existing_host:
        return update_existing_host(existing_host, input_host)
    else:
        return create_new_host(input_host)


@metrics.host_dedup_processing_time.time()
def find_existing_host(account_number, canonical_facts):
    existing_host = _find_host_by_elevated_ids(account_number, canonical_facts)

    if not existing_host:
        existing_host = find_host_by_canonical_facts(account_number, canonical_facts)

    return existing_host


@metrics.find_host_using_elevated_ids.time()
def _find_host_by_elevated_ids(account_number, canonical_facts):
    for elevated_cf_name in ELEVATED_CANONICAL_FACT_FIELDS:
        cf_value = canonical_facts.get(elevated_cf_name)
        if cf_value:
            existing_host = find_host_by_canonical_facts(account_number, {elevated_cf_name: cf_value})
            if existing_host:
                return existing_host

    return None


def _canonical_facts_host_query(account_number, canonical_facts):
    return Host.query.filter(
        (Host.account == account_number)
        & (
            Host.canonical_facts.comparator.contains(canonical_facts)
            | Host.canonical_facts.comparator.contained_by(canonical_facts)
        )
    )


def find_host_by_canonical_facts(account_number, canonical_facts):
    """
    Returns first match for a host containing given canonical facts
    """
    logger.debug("find_host_by_canonical_facts(%s)", canonical_facts)

    host = _canonical_facts_host_query(account_number, canonical_facts).first()

    if host:
        logger.debug("Found existing host using canonical_fact match: %s", host)

    return host


def _tags_host_query(account_number, tags):
    tags_to_find = {}

    for tag in tags:
        split_tag = re.split(r'/|=', tag)
        namespace = split_tag[0]
        key = split_tag[1]
        value = split_tag[2]

        if namespace in tags_to_find:
            if key in tags_to_find[namespace]:
                tags_to_find[namespace][key].append(value)
            else:
                tags_to_find[namespace][key] = [value]
        else:
            tags_to_find[namespace] = {key: [value]}

    return Host.query.filter(
        (Host.account == account_number)
        & (Host.tags.contains(tags_to_find)))


def find_hosts_by_tag(account_number, tags):
    """
    Returns all of the hosts with the tag/tags
    """
    logger.debug("find_host_by_tag(%s)", tags)

    hosts = _tags_host_query(account_number, tags)

    if hosts:
        logger.debug("found the host with those ids: %s", hosts)

    return hosts


@metrics.new_host_commit_processing_time.time()
def create_new_host(input_host):
    logger.debug("Creating a new host")
    input_host.save()
    db.session.commit()
    metrics.create_host_count.inc()
    logger.debug("Created host:%s", input_host)
    return input_host.to_json(), 201


@metrics.update_host_commit_processing_time.time()
def update_existing_host(existing_host, input_host):
    logger.debug("Updating an existing host")
    existing_host.update(input_host)
    db.session.commit()
    metrics.update_host_count.inc()
    logger.debug("Updated host:%s", existing_host)
    return existing_host.to_json(), 200


@api_operation
@metrics.api_request_time.time()
def get_host_list(
    display_name=None,
    fqdn=None,
    hostname_or_id=None,
    insights_id=None,
    tags=None,
    page=1,
    per_page=100,
    order_by=None,
    order_how=None,
):
    if fqdn:
        query = find_hosts_by_canonical_facts(current_identity.account_number, {"fqdn": fqdn})
    elif display_name:
        query = find_hosts_by_display_name(current_identity.account_number, display_name)
    elif hostname_or_id:
        query = find_hosts_by_hostname_or_id(current_identity.account_number, hostname_or_id)
    elif insights_id:
        query = find_hosts_by_canonical_facts(current_identity.account_number, {"insights_id": insights_id})
    elif tags:
        query = find_hosts_by_tag(current_identity.account_number, tags)
    else:
        query = Host.query.filter(Host.account == current_identity.account_number)

    try:
        order_by = _params_to_order_by(order_by, order_how)
    except ValueError as e:
        flask.abort(400, str(e))
    else:
        query = query.order_by(*order_by)

    query_results = query.paginate(page, per_page, True)
    logger.debug("Found hosts: %s", query_results.items)

    return _build_paginated_host_list_response(query_results.total, page, per_page, query_results.items)


def _order_how(column, order_how):
    if order_how == "ASC":
        return column.asc()
    elif order_how == "DESC":
        return column.desc()
    else:
        raise ValueError('Unsupported ordering direction, use "ASC" or "DESC".')


def _params_to_order_by(order_by=None, order_how=None):
    modified_on_ordering = (Host.modified_on.desc(),)
    ordering = ()

    if order_by == "updated":
        if order_how:
            modified_on_ordering = (_order_how(Host.modified_on, order_how),)
    elif order_by == "display_name":
        if order_how:
            ordering = (_order_how(Host.display_name, order_how),)
        else:
            ordering = (Host.display_name.asc(),)
    elif order_by:
        raise ValueError('Unsupported ordering column, use "updated" or "display_name".')
    elif order_how:
        raise ValueError(
            "Providing ordering direction without a column is not supported. "
            "Provide order_by={updated,display_name}."
        )

    return ordering + modified_on_ordering


def _build_paginated_host_list_response(total, page, per_page, host_list):
    json_host_list = [host.to_json() for host in host_list]
    json_output = {
        "total": total,
        "count": len(host_list),
        "page": page,
        "per_page": per_page,
        "results": json_host_list,
    }
    return _build_json_response(json_output, status=200)


def _build_json_response(json_data, status=200):
    return flask.Response(ujson.dumps(json_data), status=status, mimetype="application/json")


def find_hosts_by_display_name(account, display_name):
    logger.debug("find_hosts_by_display_name(%s)", display_name)
    return Host.query.filter((Host.account == account) & Host.display_name.comparator.contains(display_name))


def find_hosts_by_canonical_facts(account_number, canonical_facts):
    """
    Returns results for all hosts containing given canonical facts
    """
    logger.debug("find_hosts_by_canonical_facts(%s)", canonical_facts)
    return _canonical_facts_host_query(account_number, canonical_facts)


def find_hosts_by_hostname_or_id(account_number, hostname):
    logger.debug("find_hosts_by_hostname_or_id(%s)", hostname)
    filter_list = [
        Host.display_name.comparator.contains(hostname),
        Host.canonical_facts["fqdn"].astext.contains(hostname),
    ]

    try:
        uuid.UUID(hostname)
        host_id = hostname
        filter_list.append(Host.id == host_id)
        logger.debug("Adding id (uuid) to the filter list")
    except Exception:
        # Do not filter using the id
        logger.debug("The hostname (%s) could not be converted into a UUID", hostname, exc_info=True)

    return Host.query.filter(sqlalchemy.and_(*[Host.account == account_number, sqlalchemy.or_(*filter_list)]))


@api_operation
@metrics.api_request_time.time()
def delete_by_id(host_id_list):
    payload_tracker = get_payload_tracker(account=current_identity.account_number, payload_id=threadctx.request_id)

    with PayloadTrackerContext(payload_tracker, received_status_message="delete operation"):

        query = _get_host_list_by_id_list(current_identity.account_number, host_id_list)

        hosts_to_delete = query.all()

        if not hosts_to_delete:
            return flask.abort(status.HTTP_404_NOT_FOUND)

        with metrics.delete_host_processing_time.time():
            query.delete(synchronize_session="fetch")
        db.session.commit()

        metrics.delete_host_count.inc(len(hosts_to_delete))

        # This process of checking for an already deleted host relies
        # on checking the session after it has been updated by the commit()
        # function and marked the deleted hosts as expired.  It is after this
        # change that the host is called by a new query and, if deleted by a
        # different process, triggers the ObjectDeletedError and is not emited.
        for deleted_host in hosts_to_delete:
            # Prevents ObjectDeletedError from being raised.
            if instance_state(deleted_host).expired:
                # Can’t log the Host ID. Accessing an attribute raises ObjectDeletedError.
                logger.info("Host already deleted. Delete event not emitted.")
            else:
                with PayloadTrackerProcessingContext(
                    payload_tracker, processing_status_message="deleted host"
                ) as payload_tracker_processing_ctx:
                    logger.debug("Deleted host: %s", deleted_host)
                    emit_event(events.delete(deleted_host))
                    payload_tracker_processing_ctx.inventory_id = deleted_host.id


@api_operation
@metrics.api_request_time.time()
def get_host_by_id(host_id_list, page=1, per_page=100, order_by=None, order_how=None):
    query = _get_host_list_by_id_list(current_identity.account_number, host_id_list)

    try:
        order_by = _params_to_order_by(order_by, order_how)
    except ValueError as e:
        flask.abort(400, str(e))
    else:
        query = query.order_by(*order_by)
    query_results = query.paginate(page, per_page, True)

    logger.debug("Found hosts: %s", query_results.items)

    return _build_paginated_host_list_response(query_results.total, page, per_page, query_results.items)


def _get_host_list_by_id_list(account_number, host_id_list):
    return Host.query.filter((Host.account == account_number) & Host.id.in_(host_id_list))


@api_operation
@metrics.api_request_time.time()
def get_host_system_profile_by_id(host_id_list, page=1, per_page=100, order_by=None, order_how=None):
    query = _get_host_list_by_id_list(current_identity.account_number, host_id_list)

    try:
        order_by = _params_to_order_by(order_by, order_how)
    except ValueError as e:
        flask.abort(400, str(e))
    else:
        query = query.order_by(*order_by)
    query_results = query.paginate(page, per_page, True)

    response_list = [host.to_system_profile_json() for host in query_results.items]

    json_output = {
        "total": query_results.total,
        "count": len(response_list),
        "page": page,
        "per_page": per_page,
        "results": response_list,
    }

    return _build_json_response(json_output, status=200)


@api_operation
@metrics.api_request_time.time()
def patch_by_id(host_id_list, host_data):
    try:
        validated_patch_host_data = PatchHostSchema(strict=True).load(host_data).data
    except ValidationError as e:
        logger.exception(f"Input validation error while patching host: {host_id_list} - {host_data}")
        return ({"status": 400, "title": "Bad Request", "detail": str(e.messages), "type": "unknown"}, 400)

    query = _get_host_list_by_id_list(current_identity.account_number, host_id_list)

    hosts_to_update = query.all()

    if not hosts_to_update:
        logger.debug("Failed to find hosts during patch operation - hosts: %s", host_id_list)
        return flask.abort(status.HTTP_404_NOT_FOUND)

    for host in hosts_to_update:
        host.patch(validated_patch_host_data)

    db.session.commit()

    return 200


@api_operation
@metrics.api_request_time.time()
def replace_facts(host_id_list, namespace, fact_dict):
    return update_facts_by_namespace(FactOperations.replace, host_id_list, namespace, fact_dict)


@api_operation
@metrics.api_request_time.time()
def merge_facts(host_id_list, namespace, fact_dict):
    if not fact_dict:
        error_msg = "ERROR: Invalid request.  Merging empty facts into existing facts is a no-op."
        logger.debug(error_msg)
        return error_msg, 400

    return update_facts_by_namespace(FactOperations.merge, host_id_list, namespace, fact_dict)


def update_facts_by_namespace(operation, host_id_list, namespace, fact_dict):
    hosts_to_update = Host.query.filter(
        (Host.account == current_identity.account_number)
        & Host.id.in_(host_id_list)
        & Host.facts.has_key(namespace)  # noqa: W601 JSONB query filter, not a dict
    ).all()

    logger.debug("hosts_to_update:%s", hosts_to_update)

    if len(hosts_to_update) != len(host_id_list):
        error_msg = (
            "ERROR: The number of hosts requested does not match the number of hosts found in the host database.  "
            "This could happen if the namespace does not exist or the account number associated with the call does "
            "not match the account number associated with one or more the hosts.  Rejecting the fact change request."
        )
        logger.debug(error_msg)
        return error_msg, 400

    for host in hosts_to_update:
        if operation is FactOperations.replace:
            host.replace_facts_in_namespace(namespace, fact_dict)
        else:
            host.merge_facts_in_namespace(namespace, fact_dict)

    db.session.commit()

    logger.debug("hosts_to_update:%s", hosts_to_update)

    return 200


@api_operation
@metrics.api_request_time.time()
def get_host_tag_count(host_id_list, page=1, per_page=100, order_by=None, order_how=None):
    query = Host.query.filter((Host.account == current_identity.account_number) & Host.id.in_(host_id_list))

    try:
        order_by = _params_to_order_by(order_by, order_how)
    except ValueError as e:
        flask.abort(400, str(e))
    else:
        query = query.order_by(*order_by)
    query = query.paginate(page, per_page, True)

    counts = _count_tags(query)

    return _build_paginated_host_tags_response(query.total, page, per_page, counts)


# returns counts in format [{id: count}, {id: count}]
def _count_tags(query):
    counts = []

    for host in query.items:
        host_tag_count = 0
        for namespace in host.tags:
            for tag in host.tags[namespace]:
                host_tag_count += len(host.tags[namespace][tag])
        counts.append({f"{host.id}": host_tag_count})

    return counts


@api_operation
@metrics.api_request_time.time()
def get_host_tags(host_id_list, page=1, per_page=100, order_by=None, order_how=None):
    query = Host.query.filter((Host.account == current_identity.account_number) & Host.id.in_(host_id_list))

    try:
        order_by = _params_to_order_by(order_by, order_how)
    except ValueError as e:
        flask.abort(400, str(e))
    else:
        query = query.order_by(*order_by)
    query = query.paginate(page, per_page, True)

    tags_list = _build_serialized_tags_list(query.items)

    return _build_paginated_host_tags_response(query.total, page, per_page, tags_list)


def _build_serialized_tags_list(host_list):
    serialized_tags_list = []

    #serialized_tags_list = _serialize_tags(host_list)
    logger.debug(host_list)


    for host in host_list:
        host_tags = []
        for namespace in host.tags:
            for tag_name in host.tags[namespace]:
                for value in host.tags[namespace][tag_name]:
                    host_tags.append(namespace + "/" + tag_name + "=" + value)
        system_tag_list = {f"{host.id}": host_tags}
        serialized_tags_list.append(system_tag_list)

    return serialized_tags_list


def _build_paginated_host_tags_response(total, page, per_page, tags_list):
    json_output = {
        "total": total,
        "count": len(tags_list),
        "page": page,
        "per_page": per_page,
        "results": tags_list,
    }

    return _build_json_response(json_output, status=200)
