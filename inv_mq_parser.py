from marshmallow import Schema, fields, ValidationError
from app.logging import get_logger
from app.exceptions import ValidationException


logger = get_logger("mq_parser")


class OperationSchema(Schema):
    operation = fields.Str()
    request_id = fields.Str()
    data = fields.Dict()


def parse_operation_message(message):
    try:
        parsed_operation = OperationSchema(strict=True).load(message).data
    except ValidationError as e:
        # logger.error("Input validation error while parsing operation message")  # logger.error is used to avoid printing out ValidationError traceback
        raise ValidationException(e) from None
    except Exception as e:
        logger.exception("Error parsing operation message", extra={"operation": message})
        raise
    
    return parsed_operation