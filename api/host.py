import logging
import sqlalchemy
import uuid

from enum import Enum

from app import db
from app.models import Host
from app.auth import current_identity, requires_identity
from app.exceptions import InventoryException
from api import api_operation, metrics


TAG_OPERATIONS = ("apply", "remove")
FactOperations = Enum("FactOperations", ["merge", "replace"])

logger = logging.getLogger(__name__)


@api_operation
@metrics.api_request_time.time()
@requires_identity
def add_host(host):
    """
    Add or update a host

    Required parameters:
     - at least one of the canonical facts fields is required
     - account number
    """
    account_number = host.get("account", None)

    if current_identity.account_number != account_number:
        raise InventoryException(title="Invalid request",
                detail="The account number associated with the user does not "
                "match the account number associated with the host")

    input_host = Host.from_json(host)

    canonical_facts = input_host.canonical_facts

    if not canonical_facts:
        raise InventoryException(title="Invalid request",
                                 detail="At least one of the canonical fact "
                                 "fields must be present.")

    existing_host = find_existing_host(account_number, canonical_facts)

    if existing_host:
        return update_existing_host(existing_host, input_host)
    else:
        return create_new_host(input_host)


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
    return Host.query.filter(
            (Host.account == account_number)
            & (Host.canonical_facts["insights_id"].astext == insights_id)
        ).first()


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
    logger.debug("found_host:%s", host)
    return host


def create_new_host(input_host):
    logger.debug("Creating a new host")
    input_host.save()
    db.session.commit()
    metrics.create_host_count.inc()
    logger.debug("Created host:%s" % input_host)
    return input_host.to_json(), 201


def update_existing_host(existing_host, input_host):
    logger.debug("Updating an existing host")
    existing_host.update(input_host)
    db.session.commit()
    metrics.update_host_count.inc()
    logger.debug("Updated host:%s" % existing_host)
    return existing_host.to_json(), 200


@api_operation
@metrics.api_request_time.time()
@requires_identity
def get_host_list(tag=None, display_name=None, fqdn=None,
        hostname_or_id=None, insights_id=None,
        page=1, per_page=100):

    """
    Get the list of hosts.  Filtering can be done by the tag, display_name, or fqdn.

    If multiple tags are passed along, they are AND'd together during
    the filtering.

    """
    if fqdn:
        (total, host_list) = find_hosts_by_canonical_facts(
            current_identity.account_number, {"fqdn": fqdn}, page, per_page
        )
    elif tag:
        (total, host_list) = find_hosts_by_tag(
            current_identity.account_number, tag, page, per_page
        )
    elif display_name:
        (total, host_list) = find_hosts_by_display_name(
            current_identity.account_number, display_name, page, per_page
        )
    elif hostname_or_id:
        (total, host_list) = find_hosts_by_hostname_or_id(
            current_identity.account_number, hostname_or_id, page, per_page)
    elif insights_id:
        (total, host_list) = find_hosts_by_canonical_facts(
            current_identity.account_number, {"insights_id": insights_id}, page, per_page)
    else:
        query_results = Host.query.filter(
            Host.account == current_identity.account_number
        ).paginate(page, per_page, True)
        total = query_results.total
        host_list = query_results.items

    return _build_paginated_host_list_response(total, page, per_page, host_list)


def _build_paginated_host_list_response(total, page, per_page, host_list):
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


def find_hosts_by_tag(account, tag, page, per_page):
    logger.debug("find_hosts_by_tag(%s)" % tag)
    query_results = Host.query.filter(
        (Host.account == account) & Host.tags.comparator.contains(tag)
    ).paginate(page, per_page, True)
    total = query_results.total
    found_host_list = query_results.items
    logger.debug("found_host_list:%s" % found_host_list)
    return (total, found_host_list)


def find_hosts_by_display_name(account, display_name, page, per_page):
    logger.debug("find_hosts_by_display_name(%s)" % display_name)
    query_results = Host.query.filter(
        (Host.account == account)
        & Host.display_name.comparator.contains(display_name)
    ).paginate(page, per_page, True)
    total = query_results.total
    found_host_list = query_results.items
    logger.debug("found_host_list:%s" % found_host_list)
    return (total, found_host_list)


def find_hosts_by_canonical_facts(account_number, canonical_facts, page, per_page):
    """
    Returns paginated results for all hosts containing given canonical facts
    """
    logger.debug("find_hosts_by_canonical_facts(%s)", canonical_facts)
    query_results = _canonical_facts_host_query(account_number, canonical_facts).paginate(page, per_page, True)
    total = query_results.total
    found_host_list = query_results.items
    logger.debug("found_host_list:%s", found_host_list)
    return (total, found_host_list)


def find_hosts_by_hostname_or_id(account_number, hostname, page, per_page):
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

    query = Host.query.filter(sqlalchemy.or_(*filter_list))

    query_results = query.paginate(page, per_page, True)
    total = query_results.total
    found_host_list = query_results.items
    logger.debug("found_host_list:%s", found_host_list)

    return (total, found_host_list)


@api_operation
@metrics.api_request_time.time()
@requires_identity
def get_host_by_id(host_id_list, page=1, per_page=100):
    query_results = Host.query.filter(
        (Host.account == current_identity.account_number)
        & Host.id.in_(host_id_list)
    ).paginate(page, per_page, True)
    total = query_results.total
    found_host_list = query_results.items

    return _build_paginated_host_list_response(total, page,
                                               per_page, found_host_list)


@api_operation
@metrics.api_request_time.time()
@requires_identity
def replace_facts(host_id_list, namespace, fact_dict):
    return update_facts_by_namespace(FactOperations.replace, host_id_list,
                                     namespace, fact_dict)


@api_operation
@metrics.api_request_time.time()
@requires_identity
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
