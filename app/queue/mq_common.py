import json

from app.logging import get_logger
from app.queue import metrics

logger = get_logger(__name__)


@metrics.common_message_parsing_time.time()
def common_message_parser(message):
    try:
        # Due to RHCLOUD-3610 we're receiving messages with invalid unicode code points (invalid surrogate pairs)
        # Python pretty much ignores that but it is not possible to store such strings in the database (db INSERTS
        # blow up)
        parsed_message = json.loads(message)
        return parsed_message
    except json.decoder.JSONDecodeError:
        # The "extra" dict cannot have a key named "msg" or "message"
        # otherwise an exception in thrown in the logging code
        logger.exception("Unable to parse json message from message queue", extra={"incoming_message": message})
        metrics.common_message_parsing_failure.labels("invalid").inc()
        raise
