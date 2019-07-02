from marshmallow import Schema, fields, ValidationError
from app.logging import get_logger


logger = get_logger("mq_service")


class OperationSchema(Schema):
    operation = fields.Str()
    request_id = fields.Str()
    data = fields.Dict()


def parse_operation_message(message):
    try:
        return OperationSchema(strict=True).load(message).data
    except ValidationError as e:
        logger.exception("Input validation error while parsing operation message",
                         extra={"operation": message})
        raise
    except Exception as e:
        logger.exception("Error parsing operation message", extra={"operation": message})
        raise