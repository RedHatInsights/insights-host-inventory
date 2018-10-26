#from insights_connexion.db.base import session
from app.models import Host
from app import db


def addHost(host):
    print("addHost()")
    print("host:", host)
    print("type(host):", type(host))

    canonical_facts = host.get("canonical_facts")

    found_host = Host.query.filter(
                         Host.canonical_facts.comparator.contains(canonical_facts) |
                         Host.canonical_facts.comparator.contained_by(canonical_facts)
                       ).first()

    if not found_host:
        print("found_host:", found_host)
        h = Host.from_json(host)
        db.session.add(h)
        db.session.commit()
        return {'count': 0, 'results': h.to_json()}, 201
    else:
        print("Updating host...")

        # ---------------------------------------------------------------
        # FIXME: The update logic needs to be moved into the model object
        # ---------------------------------------------------------------

        found_host.canonical_facts.update(canonical_facts)

        facts = host.get("facts", []) 
        if facts:
            if found_host.facts:
                found_host.facts.append(facts)
            else:
                found_host.facts = facts

        tags = host.get("tags", [])
        if tags:
            found_host.tags.append(tags)

        print("*** Updated host:", found_host)

        db.session.commit()
        return {'count': 0, 'results': found_host.to_json()}, 200


def getHostList(tag=None):
    print(f"getHostList(tag={tag})")

    if tag:
        host_list = findHostsByTag(tag)
    else:
        host_list = Host.get_all()

    json_host_list = []
    for host in host_list:
        json_host_list.append(host.to_json())

    return json_host_list, 200


def findHostsByTag(tag):
    print(f"findHostsByTag({tag})")
    found_host_list = Host.query.filter(
            Host.tags.comparator.contains(tag)).all()
    print("found_host_list:", found_host_list)
    return found_host_list


def getHostById(hostId):
    print(f"getHostById({hostId})")
    return host


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
