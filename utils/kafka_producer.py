import argparse
import logging
import os
import sys

import payloads
from confluent_kafka import Producer as KafkaProducer

HOST_INGRESS_TOPIC = os.environ.get("KAFKA_HOST_INGRESS_TOPIC", "platform.inventory.host-ingress")
BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
NUM_HOSTS = int(os.environ.get("NUM_HOSTS", 1))
HOST_TYPE = os.environ.get("HOST_TYPE", "default")


# Mapping of host types to their corresponding payload builders
HOST_TYPE_BUILDERS = {
    "default": payloads.build_host_chunk,
    "rhsm": payloads.build_rhsm_payload,
    "qpc": payloads.build_qpc_payload,
    "sap": payloads.build_sap_host_chunk,
}

# Mapping of host types to their corresponding MQ payload builders
MQ_PAYLOAD_BUILDERS = {
    "default": lambda: payloads.build_mq_payload(),
    "rhsm": payloads.build_rhsm_mq_payload,
    "qpc": payloads.build_qpc_mq_payload,
    "sap": payloads.build_sap_mq_payload,
}


def get_payload_builder(host_type):
    """Get the appropriate payload builder for the specified host type."""
    if host_type not in MQ_PAYLOAD_BUILDERS:
        available_types = ", ".join(MQ_PAYLOAD_BUILDERS.keys())
        raise ValueError(f"Invalid host type '{host_type}'. Available types: {available_types}")

    return MQ_PAYLOAD_BUILDERS[host_type]


def create_payloads(num_hosts, host_type):
    """Create a list of host payloads based on the specified type and count."""
    payload_builder = get_payload_builder(host_type)

    print(f"Creating {num_hosts} host(s) of type '{host_type}'...")
    all_payloads = [payload_builder() for _ in range(num_hosts)]

    return all_payloads


def main():
    parser = argparse.ArgumentParser(description="Kafka producer for creating different types of hosts")
    parser.add_argument(
        "--host-type",
        choices=list(HOST_TYPE_BUILDERS.keys()),
        default=HOST_TYPE,
        help="Type of hosts to create (default: %(default)s)",
    )
    parser.add_argument(
        "--num-hosts", type=int, default=NUM_HOSTS, help="Number of hosts to create (default: %(default)s)"
    )
    parser.add_argument(
        "--bootstrap-servers", default=BOOTSTRAP_SERVERS, help="Kafka bootstrap servers (default: %(default)s)"
    )
    parser.add_argument(
        "--topic", default=HOST_INGRESS_TOPIC, help="Kafka topic for host ingress (default: %(default)s)"
    )
    parser.add_argument("--list-types", action="store_true", help="List available host types and exit")

    args = parser.parse_args()

    if args.list_types:
        print("Available host types:")
        for host_type, builder in HOST_TYPE_BUILDERS.items():
            description = builder.__doc__ or "No description available"
            print(f"  {host_type}: {description.split('.')[0]}")
        return

    try:
        # Create list of host payloads based on specified type
        all_payloads = create_payloads(args.num_hosts, args.host_type)
        print(f"Number of hosts (payloads): {len(all_payloads)}")
        print(f"Host type: {args.host_type}")

        producer = KafkaProducer({"bootstrap.servers": args.bootstrap_servers})
        print(f"HOST_INGRESS_TOPIC: {args.topic}")

        def delivery_callback(err, msg):
            if err:
                sys.stderr.write(f"% Message failed delivery: {err}\n")
            else:
                sys.stderr.write(f"% Message delivered to {msg.topic()} [{msg.partition()}] @ {msg.offset()}\n")

        # Send all payloads to Kafka
        for i, payload in enumerate(all_payloads, 1):
            producer.produce(args.topic, value=payload, callback=delivery_callback)
            sys.stderr.write(f"% Produced host {i}/{len(all_payloads)}\n")

        producer.flush()
        print(f"Successfully sent {len(all_payloads)} {args.host_type} host(s) to Kafka topic '{args.topic}'")

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
