# MUST DESTROY!
# from app.logging import get_logger
# from app.queue.event_producer import EventProducer
# logger = get_logger(__name__)
# producer = None
# def init_tasks(config):
#     global producer
#     logger.info("Starting event KafkaProducer()")
#     producer = EventProducer(config)
# def emit_event(event, key, headers):
#     producer.write_event_events_topic(event, key, headers)
# def flush():
#     producer.flush()
#     logger.info("Event messages flushed")
