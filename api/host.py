#from insights_connexion.db.base import session
from app.models import Host, convert_json_facts_to_dict
from app import db



def addHost(host):
    print("addHost()")
    print("host:", host)

    # Required inputs:
    # account
    # canonical_facts

    canonical_facts = host.get("canonical_facts")

    found_host = Host.query.filter(
                         Host.canonical_facts.comparator.contains(canonical_facts) |
                         Host.canonical_facts.comparator.contained_by(canonical_facts)
                       ).first()

    if not found_host:
        print("Creating a new host")
        host = Host.from_json(host)
        print("FACTS:", host.facts)
        host.save()
        return {'count': 0, 'results': host.to_json()}, 201
    else:
        print("Updating host...")

        found_host.update(host)

        print("*** Updated host:", found_host)

        return {'count': 0, 'results': found_host.to_json()}, 200


def getHostList(tag=None):
    print(f"getHostList(tag={tag})")

    if tag:
        host_list = findHostsByTag(tag)
    else:
        host_list = Host.get_all()

    json_host_list = [host.to_json() for host in host_list]

    # FIXME: pagination
    return json_host_list, 200


def findHostsByTag(tag):
    print(f"findHostsByTag({tag})")
    found_host_list = Host.query.filter(
            Host.tags.comparator.contains(tag)).all()
    print("found_host_list:", found_host_list)
    return found_host_list


def getHostById(hostId):
    print(f"getHostById({hostId})")

    print(type(hostId[0]))

    host_id_list = [int(host_id) for host_id in hostId]

    found_host_list = Host.query.filter(Host.id.in_(host_id_list)).all()

    json_host_list = [host.to_json() for host in found_host_list]

    return {'count': 0, 'results': json_host_list}, 200


def updateHostWithForm():
    print("updateHostWithForm()")


def deleteHost(hostId):
    print(f"deleteHost({hostId})")


def replaceFacts(hostId, namespace):
    print(f"replaceFacts({hostId}, {namespace})")


def mergeFacts(hostId, namespace):
    print(f"mergeFacts({hostId}, {namespace})")
    found_host = Host.query.filter(
            Host.facts.contains([{"namespace": namespace}])).all()

            # works
            #Host.canonical_facts["key5"].astext == "value5" ).all()

    print("found_host:", found_host)


def handleTagOperation(hostId, tag_op):
    print(f"handleTagOperation({hostId},{tag_op})")

    found_host = Host.query.filter(Host.id.in_(hostId)).all()
    print("found_host:", found_host)
