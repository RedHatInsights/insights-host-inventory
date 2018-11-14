import os
import logging
from enum import Enum
from app.models import Host
from app.auth import current_identity
from app import db

TAG_OPERATIONS = ["apply", "remove"]
FactOperations = Enum("FactOperations", ["merge", "replace"])

logger = logging.getLogger(__name__)


def addHost(host):
    """
    Add or update a host

    Required parameters:
     - at least one of the canonical facts fields is required
     - account number
    """
    logger.debug("addHost(%s)" % host)

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
        logger.debug("Creating a new host")
        input_host.save()
        return input_host.to_json(), 201

    else:
        logger.debug("Updating an existing host")

        found_host.update(input_host)

        logger.debug("Updated host:%s" % found_host)

        return found_host.to_json(), 200


def getHostList(tag=None, display_name=None):
    """
    Get the list of hosts.  Filtering can be done by the tag or display_name.

    If multiple tags are passed along, they are AND'd together during
    the filtering.

    """
    logger.debug("getHostList(tag=%s, display_name=%s)" % (tag, display_name))

    if tag:
        host_list = findHostsByTag(current_identity.account_number, tag)
    elif display_name:
        host_list = findHostsByDisplayName(current_identity.account_number,
                                           display_name)
    else:
        host_list = Host.query.filter(
                Host.account == current_identity.account_number).all()

    json_host_list = [host.to_json() for host in host_list]

    # FIXME: pagination
    return {'count': 0, 'results': json_host_list}, 200


def findHostsByTag(account, tag):
    logger.debug("findHostsByTag(%s)" % tag)
    found_host_list = Host.query.filter(
            (Host.account == account) &
            Host.tags.comparator.contains(tag)).all()
    logger.debug("found_host_list:%s" % found_host_list)
    return found_host_list


def findHostsByDisplayName(account, display_name):
    logger.debug("findHostsByDisplayName(%s)" % display_name)
    found_host_list = Host.query.filter(
        (Host.account == account) &
        Host.display_name.comparator.contains(display_name)
    ).all()
    logger.debug("found_host_list:%s" % found_host_list)
    return found_host_list


def getHostById(hostId):
    logger.debug("getHostById(%s)" % hostId)

    found_host_list = Host.query.filter(
            (Host.account == current_identity.account_number) &
            Host.id.in_(hostId)).all()

    json_host_list = [host.to_json() for host in found_host_list]

    return {'count': 0, 'results': json_host_list}, 200


def replaceFacts(hostId, namespace, fact_dict):
    logger.debug("replaceFacts(%s, %s, %s)" % (hostId, namespace, fact_dict))

    return updateFactsByNamespace(FactOperations.replace,
                                  hostId,
                                  namespace,
                                  fact_dict)


def mergeFacts(hostId, namespace, fact_dict):
    logger.debug("mergeFacts(%s, %s, %s)" % (hostId, namespace, fact_dict))

    return updateFactsByNamespace(FactOperations.merge,
                                  hostId,
                                  namespace,
                                  fact_dict)


def updateFactsByNamespace(operation, host_id_list, namespace, fact_dict):
    hosts_to_update = Host.query.filter(
            (Host.account == current_identity.account_number) &
            Host.id.in_(host_id_list) &
            Host.facts.has_key(namespace)).all()

    logger.debug("hosts_to_update:%s" % hosts_to_update)

    if len(hosts_to_update) != len(host_id_list):
        error_msg = "ERROR: The number of hosts requested does not match the "\
                   "number of hosts found.  Rejecting the fact change request."
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


def handleTagOperation(hostId, tag_op):
    logger.debug("handleTagOperation(%s, %s)" % (hostId, tag_op))

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
        logger.debug(error_msg)
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
        logger.debug(error_msg)
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
