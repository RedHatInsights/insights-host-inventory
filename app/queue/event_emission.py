# from datetime import datetime
# from datetime import timezone
# from kafka import KafkaProducer
# from marshmallow import fields
# from marshmallow import Schema
# from app.logging import get_logger
# from app.models import SystemProfileSchema
# from app.models import TagsSchema
# from app.queue import metrics
# from app.queue.event_producer import KafkaEventProducer
# logger = get_logger(__name__)
# # # Try to have only one emit event function
# # def emit_delete_event(event, key, headers):
# #     # encoded_key = key.encode("utf-8") if key else None
# #     # encoded_event = event.encode("utf-8")
# #     # encoded_headers = [(hk, hv.encode("utf-8")) for hk, hv in headers.items()]
# #     producer.write_event_events_topic(event, key, headers)
# #     # producer.send(cfg.event_topic, key=k, value=v, headers=h)
# #     logger.info("Event message produced: topic %s, key %s", cfg.event_topic, key)
# #     logger.debug("Event message body: %s", event)
