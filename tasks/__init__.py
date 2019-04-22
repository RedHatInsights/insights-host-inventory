import os
import json
from kafka import KafkaConsumer
from threading import Thread, local
import logging

from app import db
from app.logging import threadctx
from app.models import Host, SystemProfileSchema

logger = logging.getLogger(__name__)

TOPIC = os.environ.get("KAFKA_TOPIC", "platform.system-profile")
KAFKA_GROUP = os.environ.get("KAFKA_GROUP", "inventory")
BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")


def msg_handler(parsed):
    id_ = parsed["id"]
    threadctx.request_id = parsed["request_id"]
    if not id_:
        logger.error("ID is null, something went wrong.")
        return
    host = Host.query.get(id_)
    if host is None:
        logger.error("Host with id [%s] not found!", id_)
        return
    logger.info("Processing message id=%s request_id=%s", parsed["id"], parsed["request_id"])
    profile = SystemProfileSchema(strict=True).load(parsed["system_profile"]).data
    host._update_system_profile(profile)
    db.session.commit()


def start_consumer(flask_app, handler=msg_handler, consumer=None):

    logger.info("Starting system profile queue consumer.")

    if consumer is None:
        consumer = KafkaConsumer(
            TOPIC,
            group_id=KAFKA_GROUP,
            bootstrap_servers=BOOTSTRAP_SERVERS)

    def _f():
        with flask_app.app_context():
            while True:
                for msg in consumer:
                    try:
                        handler(json.loads(msg.value))
                    except Exception:
                        logger.exception("uncaught exception in handler, moving on.")

    t = Thread(
        target=_f,
        daemon=True)
    t.start()
