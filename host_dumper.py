#!/usr/bin/env python
import argparse
import pprint

from app import create_app
from app.common import inventory_config
from app.culling import Timestamps
from app.environment import RuntimeEnvironment
from app.models import Host
from app.serialization import serialize_host

application = create_app(RuntimeEnvironment.COMMAND)

parser = argparse.ArgumentParser(
    description="Util that dumps a host from the hosts table.  The db configuration is read from the environment.  "
    "This util is expected to be used within the image/pod."
)
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument("--id", help="search for a host using id")
group.add_argument("--hostname", help="search for a host using display_name, fqdn")
group.add_argument("--insights_id", help="search for a host using insights_id")
group.add_argument("--org_id", help="dump all hosts associated with the org_id")
parser.add_argument("--no-pp", help="enable pretty printing", action="store_true")
args = parser.parse_args()

with application.app_context():
    # query_results = Host.query.filter().all()
    # print(query_results)
    if args.id:
        host_id_list = [args.id]
        print("looking up host using id")
        query_results = Host.query.filter(Host.id.in_(host_id_list)).all()
    elif args.hostname:
        print("looking up host using display_name, fqdn")
        query_results = Host.query.filter(
            Host.display_name.comparator.contains(args.hostname)
            | Host.canonical_facts["fqdn"].astext.contains(args.hostname)
        ).all()
    elif args.insights_id:
        print("looking up host using insights_id")
        query_results = Host.query.filter(
            Host.canonical_facts.comparator.contains({"insights_id": args.insights_id})
        ).all()
    elif args.org_id:
        query_results = Host.query.filter(Host.org_id == args.org_id).all()

    staleness_timestamps = Timestamps.from_config(inventory_config())
    json_host_list = [serialize_host(host, staleness_timestamps) for host in query_results]

    if args.no_pp:
        print(json_host_list)
    else:
        pp = pprint.PrettyPrinter(indent=4)
        pp.pprint(json_host_list)
