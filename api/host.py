import os
import logging
from app.models import Host, CFSquasher
from app import db

TAG_OPERATIONS = ["apply", "remove"]


logger = logging.getLogger(__name__)


def addHost(host):
    logger.debug("addHost(%s)" % host)
    print("addHost(%s)" % host)

    # Required inputs:
    # account
    # canonical_facts

    canonical_facts = CFSquasher().convert_fields_to_canonical_facts(host)
    print("canonical_facts:", canonical_facts)

    found_host = Host.query.filter(
        Host.canonical_facts.comparator.contains(canonical_facts) |
        Host.canonical_facts.comparator.contained_by(canonical_facts)
    ).first()

    if not found_host:
        logger.debug("Creating a new host")
        host = Host.from_json(host)
        # FIXME:
        host.canonical_facts = canonical_facts
        host.save()
        return host.to_json(), 201

    else:
        logger.debug("Updating an existing host")

        found_host.update(host)

        logger.debug("Updated host:%s" % found_host)

        return found_host.to_json(), 200


def getHostList(tag=None, display_name=None):
    logger.debug("getHostList(tag=%s, display_name=%s)" % (tag, display_name))

    if tag:
        host_list = findHostsByTag(tag)
    elif display_name:
        host_list = findHostsByDisplayName(display_name)
    else:
        host_list = Host.get_all()

    json_host_list = [host.to_json() for host in host_list]

    # FIXME: pagination
    return {'count': 0, 'results': json_host_list}, 200


def findHostsByTag(tag):
    logger.debug("findHostsByTag(%s)" % tag)
    found_host_list = Host.query.filter(Host.tags.comparator.contains(tag)).all()
    logger.debug("found_host_list:%s" % found_host_list)
    return found_host_list


def findHostsByDisplayName(display_name):
    logger.debug("findHostsByDisplayName(%s)" % display_name)
    found_host_list = Host.query.filter(
        Host.display_name.comparator.contains(display_name)
    ).all()
    logger.debug("found_host_list:%s" % found_host_list)
    return found_host_list


def getHostById(hostId):
    logger.debug("getHostById(%s)" % hostId)

    found_host_list = Host.query.filter(Host.id.in_(hostId)).all()

    json_host_list = [host.to_json() for host in found_host_list]

    return {'count': 0, 'results': json_host_list}, 200


def deleteHost(hostId):
    logger.debug("deleteHost(%s)" % hostId)


def replaceFacts(hostId, namespace, fact_dict):
    logger.debug("replaceFacts(%s, %s, %s)" % (hostId, namespace, fact_dict))


def mergeFacts(hostId, namespace, fact_dict):
    logger.debug("mergeFacts(%s, %s, %s)" % (hostId, namespace, fact_dict))

    hosts_to_update = Host.query.filter(
            Host.id.in_(hostId) &
            Host.facts.has_key(namespace)).all()

    logger.debug("hosts_to_update:%s" % hosts_to_update)

    for host in hosts_to_update:
        host.merge_facts_in_namespace(namespace, fact_dict)

    db.session.commit()

    logger.debug("hosts_to_update:%s" % hosts_to_update)

    return 200


def handleTagOperation(hostId, tag_op):
    logger.debug("handleTagOperation(%s, %s)" % (hostId, tag_op))

    try:
        (operation, tag) = validate_tag_operation_request(tag_op)
    except KeyError:
        return "Invalid request", 400
    # except InvalidTag:
    #    return "Invalid request", 400
    except:
        return "Invalid request", 400

    if operation == "apply":
        apply_tag_to_hosts(hostId, tag)
    else:
        remove_tag_from_hosts(hostId, tag)

    return 200


def apply_tag_to_hosts(host_id_list, tag):
    hosts_to_update = Host.query.filter(Host.id.in_(host_id_list)).all()

    for h in hosts_to_update:
        h.add_tag(tag)

    db.session.commit()


def remove_tag_from_hosts(host_id_list, tag):
    hosts_to_update = Host.query.filter(
                Host.id.in_(host_id_list) &
                Host.tags.comparator.contains([tag])
                ).all()

    for h in hosts_to_update:
        h.remove_tag(tag)

    db.session.commit()


def validate_tag_operation_request(tag_op_doc):
    operation = tag_op_doc["operation"]
    tag = tag_op_doc["tag"]

    if (operation in TAG_OPERATIONS and tag is not None and is_valid_tag(tag)):
        return (operation, tag)
    else:
        return None


def is_valid_tag(tag):
    return True
