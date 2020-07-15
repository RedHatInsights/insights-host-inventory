from app.queue.metrics import event_producer_failure
from app.queue.metrics import event_producer_success


def message_produced(logger, value, key, headers, record_metadata):
    status = "PRODUCED"
    offset = record_metadata.offset
    timestamp = record_metadata.timestamp
    topic = record_metadata.topic
    extra = {"status": status, "offset": offset, "timestamp": timestamp, "topic": topic, "key": key}

    info_extra = {**extra, "headers": headers}
    info_message = "Message %s offset=%d timestamp=%d topic=%s, key=%s, headers=%s"
    logger.info(info_message, status, offset, timestamp, topic, key, headers, extra=info_extra)

    debug_message = "Message offset=%d timestamp=%d topic=%s key=%s value=%s"
    debug_extra = {**extra, "value": value}
    logger.debug(debug_message, offset, timestamp, topic, key, value, extra=debug_extra)

    event_producer_success.inc()


def message_not_produced(logger, topic, value, key, headers, error):
    status = "NOT PRODUCED"
    error_message = str(error)
    extra = {"status": status, "topic": topic, "key": key}

    info_extra = {**extra, "headers": headers, "error": error_message}
    info_message = "Message %s topic=%s, key=%s, headers=%s, error=%s"
    logger.error(info_message, status, topic, key, headers, error, extra=info_extra)

    debug_message = "Message topic=%s key=%s value=%s"
    debug_extra = {**extra, "value": value}
    logger.debug(debug_message, topic, key, value, extra=debug_extra)

    event_producer_failure.labels(event_type=headers["event_type"], topic=topic).inc()
