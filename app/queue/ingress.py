from marshmallow import Schema, fields, ValidationError
from app.logging import get_logger


logger = get_logger(__name__)


class OperationSchema(Schema):
    operation = fields.Str()
    request_id = fields.Str()
    data = fields.Dict()


def parse_operation_message(message):
    try:
        parsed_operation = OperationSchema(strict=True).load(message).data
    except ValidationError as e:
        logger.error("Input validation error while parsing operation message", extra={"operation": message})  # logger.error is used to avoid printing out the same traceback twice
        raise
    except Exception as e:
        logger.exception("Error parsing operation message", extra={"operation": message})
        raise
    
    return parsed_operation