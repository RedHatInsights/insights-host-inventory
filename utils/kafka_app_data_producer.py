import argparse
import json
import logging
import os
import random
import sys
import uuid
from datetime import UTC
from datetime import datetime
from datetime import timedelta

from confluent_kafka import Producer as KafkaProducer

HOST_APP_DATA_TOPIC = os.environ.get("KAFKA_HOST_APP_DATA_TOPIC", "platform.inventory.host-apps")
BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")

# All supported application types, matching HostAppMessageConsumer routing
APP_DATA_BUILDERS = {}


def _register(app_name):
    """Decorator to register an app data builder function."""

    def wrapper(fn):
        APP_DATA_BUILDERS[app_name] = fn
        return fn

    return wrapper


@_register("advisor")
def build_advisor_data():
    """Advisor application data — recommendations and incidents."""
    return {
        "recommendations": random.randint(0, 15),
        "incidents": random.randint(0, 3),
    }


@_register("vulnerability")
def build_vulnerability_data():
    """Vulnerability application data — CVE counts by severity."""
    total = random.randint(5, 120)
    critical = random.randint(0, min(5, total))
    high = random.randint(0, min(20, total - critical))
    return {
        "total_cves": total,
        "critical_cves": critical,
        "high_severity_cves": high,
        "cves_with_security_rules": random.randint(0, min(3, critical + high)),
        "cves_with_known_exploits": random.randint(0, min(2, critical)),
    }


@_register("patch")
def build_patch_data():
    """Patch application data — advisory and package counts."""
    return {
        "advisories_rhsa_applicable": random.randint(0, 10),
        "advisories_rhba_applicable": random.randint(0, 25),
        "advisories_rhea_applicable": random.randint(0, 15),
        "advisories_other_applicable": random.randint(0, 5),
        "advisories_rhsa_installable": random.randint(0, 8),
        "advisories_rhba_installable": random.randint(0, 20),
        "advisories_rhea_installable": random.randint(0, 12),
        "advisories_other_installable": random.randint(0, 3),
        "packages_applicable": random.randint(5, 50),
        "packages_installable": random.randint(3, 30),
        "packages_installed": random.randint(100, 500),
        "template_name": random.choice([None, "RHEL-8-base", "RHEL-9-stig", "CIS-Level-1"]),
        "template_uuid": str(uuid.uuid4()) if random.choice([True, False]) else None,
    }


@_register("remediations")
def build_remediations_data():
    """Remediations application data — remediation plan count."""
    return {
        "remediations_plans": random.randint(0, 5),
    }


@_register("compliance")
def build_compliance_data():
    """Compliance application data — policies and last scan."""
    policy_names = ["PCI-DSS", "HIPAA", "CIS-Level-1", "STIG", "NIST-800-53", "SOC2"]
    num_policies = random.randint(0, 3)
    policies = [{"id": str(uuid.uuid4()), "name": random.choice(policy_names)} for _ in range(num_policies)]
    days_ago = random.randint(0, 30)
    return {
        "policies": policies if policies else None,
        "last_scan": (datetime.now(UTC) - timedelta(days=days_ago)).isoformat(),
    }


@_register("malware")
def build_malware_data():
    """Malware application data — scan results and match counts."""
    is_clean = random.random() > 0.15  # 85% chance of clean
    last_matches = 0 if is_clean else random.randint(1, 5)
    return {
        "last_status": "clean" if is_clean else "infected",
        "last_matches": last_matches,
        "total_matches": last_matches + random.randint(0, 5),
        "last_scan": (datetime.now(UTC) - timedelta(days=random.randint(0, 7))).isoformat(),
    }


def build_app_data_message(org_id, host_ids, data_builder):
    """Build a Kafka message payload for the host-apps topic.

    Message format matches HostAppOperationSchema:
      {"org_id": str, "timestamp": ISO datetime, "hosts": [{"id": UUID, "data": {...}}]}
    """
    return {
        "org_id": org_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "hosts": [{"id": host_id, "data": data_builder()} for host_id in host_ids],
    }


def resolve_apps(requested):
    """Resolve the list of app names to produce data for."""
    if not requested or requested == ["all"]:
        return list(APP_DATA_BUILDERS.keys())

    valid = []
    for app in requested:
        if app not in APP_DATA_BUILDERS:
            available = ", ".join(APP_DATA_BUILDERS.keys())
            raise ValueError(f"Unknown app '{app}'. Available: {available}")
        valid.append(app)
    return valid


def main():
    parser = argparse.ArgumentParser(
        description="Kafka producer for host application data (advisor, vulnerability, patch, etc.)"
    )
    parser.add_argument(
        "--org-id",
        default=os.environ.get("INVENTORY_HOST_ACCOUNT", "321"),
        help="Organization ID for the host app data (default: %(default)s)",
    )
    parser.add_argument(
        "--host-ids",
        nargs="+",
        required=False,
        help="Space-separated host UUIDs to populate app data for",
    )
    parser.add_argument(
        "--apps",
        nargs="*",
        default=["all"],
        help="App names to produce data for (default: all). Options: " + ", ".join(APP_DATA_BUILDERS.keys()),
    )
    parser.add_argument(
        "--bootstrap-servers",
        default=BOOTSTRAP_SERVERS,
        help="Kafka bootstrap servers (default: %(default)s)",
    )
    parser.add_argument(
        "--topic",
        default=HOST_APP_DATA_TOPIC,
        help="Kafka topic for host app data (default: %(default)s)",
    )
    parser.add_argument("--list-apps", action="store_true", help="List available app types and exit")

    args = parser.parse_args()

    if args.list_apps:
        print("Available app data types:")
        for app_name, builder in APP_DATA_BUILDERS.items():
            description = builder.__doc__ or "No description available"
            print(f"  {app_name}: {description.strip()}")
        return

    if not args.host_ids:
        print("Error: --host-ids is required (provide at least one host UUID)", file=sys.stderr)
        sys.exit(1)

    try:
        apps = resolve_apps(args.apps)
        print(f"Producing app data for {len(args.host_ids)} host(s), apps: {', '.join(apps)}")
        print(f"Organization: {args.org_id}")

        producer = KafkaProducer({"bootstrap.servers": args.bootstrap_servers})
        print(f"Topic: {args.topic}")

        def delivery_callback(err, msg):
            if err:
                sys.stderr.write(f"% Message failed delivery: {err}\n")
            else:
                sys.stderr.write(f"% Message delivered to {msg.topic()} [{msg.partition()}] @ {msg.offset()}\n")

        messages_sent = 0
        for app_name in apps:
            builder = APP_DATA_BUILDERS[app_name]
            message = build_app_data_message(args.org_id, args.host_ids, builder)

            # The "application" header is required by HostAppMessageConsumer
            # to route the message to the correct model class.
            producer.produce(
                args.topic,
                value=json.dumps(message).encode("utf-8"),
                headers=[("application", app_name.encode("utf-8"))],
                callback=delivery_callback,
            )
            messages_sent += 1
            sys.stderr.write(f"% Produced {app_name} data for {len(args.host_ids)} host(s)\n")

        producer.flush()
        print(
            f"Successfully sent {messages_sent} app data message(s) "
            f"for {len(args.host_ids)} host(s) to topic '{args.topic}'"
        )

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
