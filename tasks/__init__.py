import json
from kafka import KafkaConsumer
from kafka import KafkaProducer
from threading import Thread

from api import metrics
from app import db
from app.logging import threadctx, get_logger
from app.config import Config
from app.models import Host, SystemProfileSchema

logger = get_logger(__name__)

cfg = Config()


class NullProducer:

    def send(self, topic, value=None):
        pass


if cfg.kafka_enabled:
    producer = KafkaProducer(bootstrap_servers=cfg.bootstrap_servers)
else:
    producer = NullProducer()


def emit_event(e):
    producer.send(cfg.event_topic, value=e.encode("utf-8"))


@metrics.system_profile_commit_processing_time.time()
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
            cfg.system_profile_topic,
            group_id=cfg.consumer_group,
            bootstrap_servers=cfg.bootstrap_servers)

    def _f():
        with flask_app.app_context():
            while True:
                for msg in consumer:
                    try:
                        with metrics.system_profile_deserialization_time.time():
                            data = json.loads(msg.value)
                        handler(data)
                        metrics.system_profile_commit_count.inc()
                    except Exception:
                        logger.exception("uncaught exception in handler, moving on.")
                        metrics.system_profile_failure_count.inc()

    t = Thread(
        target=_f,
        daemon=True)
    t.start()
