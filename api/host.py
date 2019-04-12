import logging
import uuid
from enum import Enum

import sqlalchemy
from api import api_operation, metrics
from app import db
from app.auth import current_identity
from app.exceptions import InventoryException
from app.models import Host, HostSchema
from marshmallow import ValidationError

TAG_OPERATIONS = ("apply", "remove")
FactOperations = Enum("FactOperations", ["merge", "replace"])

logger = logging.getLogger(__name__)


@api_operation
@metrics.api_request_time.time()
def add_host_list(host_list):
    response_host_list = []
    number_of_errors = 0
    for host in host_list:
        try:
            (host, status_code) = _add_host(host)
            response_host_list.append({'status': status_code, 'host': host})
        except InventoryException as e:
            number_of_errors += 1
            logger.exception("Error adding host: %s" % host)
            response_host_list.append({**e.to_json(), "host": host})
        except ValidationError as e:
            number_of_errors += 1
            logger.exception(
                "Input validation error while adding host: %s" % host)
            response_host_list.append({"status": 400,
                                       "title": "Bad Request",
                                       "detail": str(e.messages),
                                       "type": "unknown",
                                       "host": host})
        except Exception as e:
            number_of_errors += 1
            logger.exception("Error adding host: %s" % host)
            response_host_list.append({"status": 500,
                                       "title": "Error",
                                       "type": "unknown",
                                       "detail": "Could not complete operation",
                                       "host": host})

    response = {'total': len(response_host_list),
                'errors': number_of_errors,
                'data': response_host_list}
    return response, 207


def _add_host(host):
    """
    Add or update a host

    Required parameters:
     - at least one of the canonical facts fields is required
     - account number
    """
    validated_input_host_dict = HostSchema(strict=True).load(host)

    input_host = Host.from_json(validated_input_host_dict.data)

    if (not current_identity.is_trusted_system and
            current_identity.account_number != input_host.account):
        raise InventoryException(title="Invalid request",
                                 detail="The account number associated with the user does not "
                                 "match the account number associated with the host")

    existing_host = find_existing_host(input_host.account,
                                       input_host.canonical_facts)

    if existing_host:
        return update_existing_host(existing_host, input_host)
    else:
        return create_new_host(input_host)


@metrics.host_dedup_processing_time.time()
def find_existing_host(account_number, canonical_facts):
    existing_host = None
    insights_id = canonical_facts.get("insights_id", None)

    if insights_id:
        # The insights_id is the most important canonical fact.  If there
        # is a matching insights_id, then update that host.
        existing_host = find_host_by_insights_id(account_number, insights_id)

    if not existing_host:
        existing_host = find_host_by_canonical_facts(account_number,
                                                     canonical_facts)

    return existing_host


def find_host_by_insights_id(account_number, insights_id):
    existing_host = Host.query.filter(
        (Host.account == account_number)
        & (Host.canonical_facts["insights_id"].astext == insights_id)
    ).first()

    if existing_host:
        logger.debug("Found existing host using id match: %s", existing_host)

    return existing_host


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
        logger.debug(
            "Found existing host using canonical_fact match: %s", host)

    return host


@metrics.new_host_commit_processing_time.time()
def create_new_host(input_host):
    logger.debug("Creating a new host")
    input_host.save()
    db.session.commit()
    metrics.create_host_count.inc()
    logger.debug("Created host:%s" % input_host)
    return input_host.to_json(), 201


@metrics.update_host_commit_processing_time.time()
def update_existing_host(existing_host, input_host):
    logger.debug("Updating an existing host")
    existing_host.update(input_host)
    db.session.commit()
    metrics.update_host_count.inc()
    logger.debug("Updated host:%s" % existing_host)
    return existing_host.to_json(), 200


@api_operation
@metrics.api_request_time.time()
def get_host_list(display_name=None, fqdn=None,
                  hostname_or_id=None, insights_id=None,
                  page=1, per_page=100):
    if fqdn:
        query = find_hosts_by_canonical_facts(
            current_identity.account_number, {"fqdn": fqdn}
        )
    elif display_name:
        query = find_hosts_by_display_name(
            current_identity.account_number, display_name
        )
    elif hostname_or_id:
        query = find_hosts_by_hostname_or_id(
            current_identity.account_number, hostname_or_id)
    elif insights_id:
        query = find_hosts_by_canonical_facts(
            current_identity.account_number, {"insights_id": insights_id})
    else:
        query = Host.query.filter(
            Host.account == current_identity.account_number
        )

    query = query.order_by(Host.created_on, Host.id)
    query_results = query.paginate(page, per_page, True)
    logger.debug(f"Found hosts: {query_results.items}")

    return build_paginated_host_list_response(
        query_results.total, page, per_page, query_results.items
    )


def build_paginated_host_list_response(total, page, per_page, host_list):
    json_host_list = [host.to_json() for host in host_list]
    return (
        {
            "total": total,
            "count": len(host_list),
            "page": page,
            "per_page": per_page,
            "results": json_host_list,
        },
        200,
    )


def find_hosts_by_display_name(account, display_name):
    logger.debug("find_hosts_by_display_name(%s)" % display_name)
    return Host.query.filter(
        (Host.account == account)
        & Host.display_name.comparator.contains(display_name)
    )


def find_hosts_by_canonical_facts(account_number, canonical_facts):
    """
    Returns results for all hosts containing given canonical facts
    """
    logger.debug("find_hosts_by_canonical_facts(%s)", canonical_facts)
    return _canonical_facts_host_query(account_number, canonical_facts)


def find_hosts_by_hostname_or_id(account_number, hostname):
    logger.debug("find_hosts_by_hostname_or_id(%s)", hostname)
    filter_list = [Host.display_name.comparator.contains(hostname),
                   Host.canonical_facts['fqdn'].astext.contains(hostname), ]

    try:
        uuid.UUID(hostname)
        host_id = hostname
        filter_list.append(Host.id == host_id)
        logger.debug("Adding id (uuid) to the filter list")
    except Exception as e:
        # Do not filter using the id
        logger.debug("The hostname (%s) could not be converted into a UUID",
                     hostname,
                     exc_info=True)

    return Host.query.filter(sqlalchemy.and_(*[Host.account == account_number,
                                               sqlalchemy.or_(*filter_list)]))


@api_operation
@metrics.api_request_time.time()
def get_host_by_id(host_id_list, page=1, per_page=100):
    query = get_host_list_by_id_list(current_identity.account_number,
                                     host_id_list)

    query_results = query.paginate(page, per_page, True)

    logger.debug(f"Found hosts: {query_results.items}")

    return build_paginated_host_list_response(
        query_results.total, page, per_page, query_results.items
    )


def get_host_list_by_id_list(account_number, host_id_list):
    return Host.query.filter(
        (Host.account == account_number)
        & Host.id.in_(host_id_list)
    ).order_by(Host.created_on, Host.id)


@api_operation
@metrics.api_request_time.time()
def get_host_system_profile_by_id(host_id_list, page=1, per_page=100):
    query = get_host_list_by_id_list(current_identity.account_number,
                                     host_id_list)

    query_results = query.paginate(page, per_page, True)

    response_list = [host.to_system_profile_json()
                     for host in query_results.items]

    return (
        {
            "total": query_results.total,
            "count": len(response_list),
            "page": page,
            "per_page": per_page,
            "results": response_list,
        },
        200,
    )


@api_operation
@metrics.api_request_time.time()
def replace_facts(host_id_list, namespace, fact_dict):
    return update_facts_by_namespace(FactOperations.replace, host_id_list,
                                     namespace, fact_dict)


@api_operation
@metrics.api_request_time.time()
def merge_facts(host_id_list, namespace, fact_dict):
    if not fact_dict:
        error_msg = "ERROR: Invalid request.  Merging empty facts into existing facts is a no-op."
        logger.debug(error_msg)
        return error_msg, 400

    return update_facts_by_namespace(FactOperations.merge, host_id_list,
                                     namespace, fact_dict)


def update_facts_by_namespace(operation, host_id_list, namespace, fact_dict):
    hosts_to_update = Host.query.filter(
        (Host.account == current_identity.account_number)
        & Host.id.in_(host_id_list)
        & Host.facts.has_key(namespace)
    ).all()

    logger.debug("hosts_to_update:%s" % hosts_to_update)

    if len(hosts_to_update) != len(host_id_list):
        error_msg = "ERROR: The number of hosts requested does not match the " "number of hosts found in the host database.  This could " " happen if the namespace " "does not exist or the account number associated with the " "call does not match the account number associated with " "one or more the hosts.  Rejecting the fact change request."
        logger.debug(error_msg)
        return error_msg, 400

    for host in hosts_to_update:
        if operation is FactOperations.replace:
            host.replace_facts_in_namespace(namespace, fact_dict)
        else:
            host.merge_facts_in_namespace(namespace, fact_dict)

    db.session.commit()

    logger.debug("hosts_to_update:%s" % hosts_to_update)

    return 200
