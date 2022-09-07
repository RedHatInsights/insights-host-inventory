import logging
import os

import payloads
from ttictoc import TicToc

from app.config import Config
from app.environment import RuntimeEnvironment
from app.queue.event_producer import EventProducer


NUM_HOSTS = int(os.environ.get("NUM_HOSTS", 20))


def main():
    # Create list of host payloads to add to the message queue
    # payloads.build_payloads takes two optional args: number of hosts, and payload type ("default", "rhsm", "qpc")
    with TicToc("Build payloads"):
        all_payloads = [payloads.build_mq_payload() for _ in range(NUM_HOSTS)]
    print("Number of hosts (payloads): ", len(all_payloads))

    config = Config(RuntimeEnvironment.JOB)

    producer = EventProducer(config, "platform.inventory.host-ingress")

    with TicToc("Send all hosts to queue"):
        for payload in all_payloads:
            producer.send("platform.inventory.host-ingress", value=payload)
    producer.flush()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
