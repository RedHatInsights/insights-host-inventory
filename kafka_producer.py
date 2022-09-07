import logging
import os

from ttictoc import TicToc

from app import create_app
from app.environment import RuntimeEnvironment
from app.queue.event_producer import EventProducer
from lib.handlers import register_shutdown
from utils import payloads


NUM_HOSTS = int(os.environ.get("NUM_HOSTS", 20))


def main():
    # Create list of host payloads to add to the message queue
    # payloads.build_payloads takes two optional args: number of hosts, and payload type ("default", "rhsm", "qpc")
    application = create_app(RuntimeEnvironment.JOB)
    config = application.config["INVENTORY_CONFIG"]

    with TicToc("Build payloads"):
        all_payloads = [payloads.build_mq_payload() for _ in range(NUM_HOSTS)]
    print("Number of hosts (payloads): ", len(all_payloads))

    producer = EventProducer(config, "platform.inventory.host-ingress")
    register_shutdown(producer.close, "Closing producer")

    with TicToc("Send all hosts to queue"):
        for payload in all_payloads:
            producer.write_event("platform.inventory.host-ingress", value=payload)
    producer.flush()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
