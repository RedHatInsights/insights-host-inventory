# # Probably want to delete this whole file in the refactor
# # from kafka import KafkaProducer
# from app.logging import get_logger
# # from app.queue.event_producer import KafkaEventProducer
# logger = get_logger(__name__)
# producer = None
# # cfg = None
# def init_tasks(config):
#     # global cfg
#     global producer
#     logger.info("Starting event KafkaProducer()")
#     producer = KafkaEventProducer(config)
#     # cfg = config
#     # producer = _init_event_producer()
# def emit_event(event, key, headers):
#     producer.write_event_events_topic(event, key, headers)
# # def _init_event_producer():
# #     logger.info("Starting event KafkaProducer()")
# #     return KafkaProducer(bootstrap_servers=cfg.bootstrap_servers)
# # def emit_event(event, key, headers):
# #     k = key.encode("utf-8") if key else None
# #     v = event.encode("utf-8")
# #     h = [(hk, hv.encode("utf-8")) for hk, hv in headers.items()]
# #     producer.send(cfg.event_topic, key=k, value=v, headers=h)
# #     logger.info("Event message produced: topic %s, key %s", cfg.event_topic, key)
# #     logger.debug("Event message body: %s", event)
# def flush():
#     producer.flush()
#     logger.info("Event messages flushed")
