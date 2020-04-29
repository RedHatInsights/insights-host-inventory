def message_produced(logger, topic, value, key, headers):
    extra_message = {"key": key, "headers": headers}

    info_extra = {"topic": topic, "produced_message": extra_message}
    logger.info("Produced message on topic %s, key %s, headers %s", topic, key, headers, extra=info_extra)

    debug_extra = {**info_extra, "produced_message": {**extra_message, "value": value}}
    logger.debug("Produced message body: %s", value, extra=debug_extra)
