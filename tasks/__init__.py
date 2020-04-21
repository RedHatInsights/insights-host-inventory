from kafka import KafkaProducer

from app.logging import get_logger

logger = get_logger(__name__)


producer = None
cfg = None


def init_tasks(config):
    global cfg
    global producer

    cfg = config

    if config.kafka_enabled:
        producer = _init_event_producer(config)


def _init_event_producer(config):
    logger.info("Starting event KafkaProducer()")
    return KafkaProducer(bootstrap_servers=config.bootstrap_servers)


def emit_event(e, key):
    status = "produced" if producer else "not produced"
    logger.info("Event message (%s): topic %s, key %s", status, cfg.event_topic, key)
    logger.debug("Event message body: %s", e)
    if producer:
        producer.send(cfg.event_topic, key=key.encode("utf-8") if key else None, value=e.encode("utf-8"))


def flush():
    suffix = "" if producer else " (no producer)"
    logger.info("Event messages flush%s", suffix)
    if producer:
        producer.flush()
