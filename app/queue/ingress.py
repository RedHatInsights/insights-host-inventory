import json
from marshmallow import Schema, fields, ValidationError
from app.logging import get_logger
from app.queue import metrics


logger = get_logger(__name__)


class OperationSchema(Schema):
    operation = fields.Str()
    request_id = fields.Str()
    data = fields.Dict()

@metrics.ingress_message_parsing_time.time()
def parse_operation_message(message):
    try:
        parsed_message = json.loads(message.value)
    except Exception as e:
        # The "extra" dict cannot have a key named "msg" or "message"
        # otherwise an exception in thrown in the logging code
        logger.exception("Unable to parse json message from message queue",
                         extra={"incoming_message": message.value})
        metrics.ingress_message_parsing_failure.inc()
        raise

    try:
        parsed_operation = OperationSchema(strict=True).load(parsed_message).data
    except ValidationError as e:
        logger.error("Input validation error while parsing operation message", extra={"operation": parsed_message})  # logger.error is used to avoid printing out the same traceback twice
        metrics.ingress_message_parsing_failure.inc()
        raise
    except Exception as e:
        logger.exception("Error parsing operation message", extra={"operation": parsed_message})
        metrics.ingress_message_parsing_failure.inc()
        raise
    
    return parsed_operation