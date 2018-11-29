import os
import logging
from enum import Enum
from app.models import Host
from app.auth import current_identity, requires_identity
from app import db
from flask import current_app

TAG_OPERATIONS = ("apply", "remove")
FactOperations = Enum("FactOperations", ["merge", "replace"])

logger = logging.getLogger(__name__)


@requires_identity
def addHost(host):
    """
    Add or update a host

    Required parameters:
     - at least one of the canonical facts fields is required
     - account number
    """
    current_app.logger.debug("addHost(%s)" % host)

    account_number = host.get("account", None)

    if(current_identity.account_number != account_number):
        return "The account number associated with the user does not match "\
               "the account number associated with the host", 400

    input_host = Host.from_json(host)

    canonical_facts = input_host.canonical_facts

    if not canonical_facts:
        return "Invalid request:  At least one of the canonical fact fields "\
                "must be present.", 400

    found_host = Host.query.filter(
        (Host.account == account_number) &
        (Host.canonical_facts.comparator.contains(canonical_facts) |
         Host.canonical_facts.comparator.contained_by(canonical_facts))
    ).first()

    if not found_host:
        current_app.logger.debug("Creating a new host")
        db.session.add(input_host)
        db.session.commit()
        current_app.logger.debug("Created host:%s" % input_host)
        return input_host.to_json(), 201
    else:
        current_app.logger.debug("Updating an existing host")
        found_host.update(input_host)
        db.session.commit()
        current_app.logger.debug("Updated host:%s" % found_host)
        return found_host.to_json(), 200


@requires_identity
def getHostList(tag=None, display_name=None, page=1, per_page=100):
    """
    Get the list of hosts.  Filtering can be done by the tag or display_name.

    If multiple tags are passed along, they are AND'd together during
    the filtering.

    """
    current_app.logger.debug("getHostList(tag=%s, display_name=%s)" % (tag, display_name))

    if tag:
        (total, host_list) = findHostsByTag(
                                 current_identity.account_number,
                                 tag,
                                 page,
                                 per_page)
    elif display_name:
        (total, host_list) = findHostsByDisplayName(
                                 current_identity.account_number,
                                 display_name,
                                 page,
                                 per_page)
    else:
        query_results = Host.query.filter(
                  Host.account == current_identity.account_number
                ).paginate(page, per_page, True)
        total = query_results.total
        host_list = query_results.items

    return _buildPaginatedHostListResponse(total, page, per_page, host_list)


def _buildPaginatedHostListResponse(total, page, per_page, host_list):
    json_host_list = [host.to_json() for host in host_list]
    return {'total': total,
            'count': len(host_list),
            'page': page,
            'per_page': per_page,
            'results': json_host_list}, 200


def findHostsByTag(account, tag, page, per_page):
    current_app.logger.debug("findHostsByTag(%s)" % tag)
    query_results = Host.query.filter(
            (Host.account == account) &
            Host.tags.comparator.contains(tag)).paginate(page, per_page, True)
    total = query_results.total
    found_host_list = query_results.items
    current_app.logger.debug("found_host_list:%s" % found_host_list)
    return (total, found_host_list)


def findHostsByDisplayName(account, display_name, page, per_page):
    current_app.logger.debug("findHostsByDisplayName(%s)" % display_name)
    query_results = Host.query.filter(
        (Host.account == account) &
        Host.display_name.comparator.contains(display_name)).paginate(page, per_page, True)
    total = query_results.total
    found_host_list = query_results.items
    current_app.logger.debug("found_host_list:%s" % found_host_list)
    return (total, found_host_list)


@requires_identity
def getHostById(hostId, page=1, per_page=100):
    current_app.logger.debug("getHostById(%s, %d, %d)" % (hostId, page, per_page))
    query_results = Host.query.filter(
            (Host.account == current_identity.account_number) &
            Host.id.in_(hostId)).paginate(page, per_page, True)
    total = query_results.total
    found_host_list = query_results.items

    return _buildPaginatedHostListResponse(total, page, per_page, found_host_list)


@requires_identity
def replaceFacts(hostId, namespace, fact_dict):
    current_app.logger.debug("replaceFacts(%s, %s, %s)" % (hostId, namespace, fact_dict))

    return updateFactsByNamespace(FactOperations.replace,
                                  hostId,
                                  namespace,
                                  fact_dict)


@requires_identity
def mergeFacts(hostId, namespace, fact_dict):
    current_app.logger.debug("mergeFacts(%s, %s, %s)" % (hostId, namespace, fact_dict))

    if not fact_dict:
        error_msg = "ERROR: Invalid request.  Merging empty facts into "\
                    "existing facts is a no-op."
        current_app.logger.debug(error_msg)
        return error_msg, 400

    return updateFactsByNamespace(FactOperations.merge,
                                  hostId,
                                  namespace,
                                  fact_dict)


def updateFactsByNamespace(operation, host_id_list, namespace, fact_dict):
    hosts_to_update = Host.query.filter(
            (Host.account == current_identity.account_number) &
            Host.id.in_(host_id_list) &
            Host.facts.has_key(namespace)).all()

    current_app.logger.debug("hosts_to_update:%s" % hosts_to_update)

    if len(hosts_to_update) != len(host_id_list):
        error_msg = "ERROR: The number of hosts requested does not match the "\
                   "number of hosts found in the host database.  This could "\
                   " happen if the namespace "\
                   "does not exist or the account number associated with the "\
                   "call does not match the account number associated with "\
                   "one or more the hosts.  Rejecting the fact change request."
        current_app.logger.debug(error_msg)
        return error_msg, 400

    for host in hosts_to_update:
        if operation is FactOperations.replace:
            host.replace_facts_in_namespace(namespace, fact_dict)
        else:
            host.merge_facts_in_namespace(namespace, fact_dict)

    db.session.commit()

    current_app.logger.debug("hosts_to_update:%s" % hosts_to_update)

    return 200


@requires_identity
def handleTagOperation(hostId, tag_op):
    current_app.logger.debug("handleTagOperation(%s, %s)" % (hostId, tag_op))

    try:
        (operation, tag) = validateTagOperationRequest(tag_op)
    except KeyError:
        return "Invalid request", 400
    # except InvalidTag:
    #    return "Invalid request", 400
    except:
        return "Invalid request", 400

    if operation == "apply":
        return applyTagToHosts(hostId, tag)
    else:
        return removeTagFromHosts(hostId, tag)


def applyTagToHosts(host_id_list, tag):
    hosts_to_update = Host.query.filter(
            (Host.account == current_identity.account_number) &
            Host.id.in_(host_id_list)).all()

    if len(hosts_to_update) != len(host_id_list):
        error_msg = "ERROR: The number of hosts requested does not match the "\
                   "number of hosts found.  Rejecting the tag change request."
        current_app.logger.debug(error_msg)
        return error_msg, 400

    for h in hosts_to_update:
        h.add_tag(tag)

    db.session.commit()

    return 200


def removeTagFromHosts(host_id_list, tag):
    hosts_to_update = Host.query.filter(
                (Host.account == current_identity.account_number) &
                Host.id.in_(host_id_list) &
                Host.tags.comparator.contains([tag])
                ).all()

    if len(hosts_to_update) != len(host_id_list):
        error_msg = "ERROR: The number of hosts requested does not match the "\
                   "number of hosts found.  Rejecting the tag change request."
        current_app.logger.debug(error_msg)
        return error_msg, 400

    for h in hosts_to_update:
        h.remove_tag(tag)

    db.session.commit()

    return 200


def validateTagOperationRequest(tag_op_doc):
    operation = tag_op_doc["operation"]
    tag = tag_op_doc["tag"]

    if (operation in TAG_OPERATIONS and tag is not None and isValidTag(tag)):
        return (operation, tag)
    else:
        return None


def isValidTag(tag):
    return True
