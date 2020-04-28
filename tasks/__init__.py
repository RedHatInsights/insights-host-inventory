from kafka import KafkaProducer

from app.logging import get_logger
from app.logging import log_produced_message

logger = get_logger(__name__)


producer = None
cfg = None


def init_tasks(config):
    global cfg
    global producer

    cfg = config
    producer = _init_event_producer()


def _init_event_producer():
    logger.info("Starting event KafkaProducer()")
    return KafkaProducer(bootstrap_servers=cfg.bootstrap_servers)


def emit_event(event, key, headers):
    k = key.encode("utf-8") if key else None
    v = event.encode("utf-8")
    h = [(hk, hv.encode("utf-8")) for hk, hv in headers.items()]
    producer.send(cfg.event_topic, key=k, value=v, headers=h)
    log_produced_message(logger, cfg.event_topic, event, key, headers)


def flush():
    producer.flush()
    logger.info("Event messages flushed")
