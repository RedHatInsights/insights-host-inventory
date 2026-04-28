from marshmallow import EXCLUDE
from marshmallow import Schema as MarshmallowSchema
from marshmallow import ValidationError as MarshmallowValidationError

from app.validators import verify_uuid_format


def verify_uuid_format_not_empty_dict(value):
    """Validate UUID format and reject empty dict."""
    if isinstance(value, dict) and len(value) == 0:
        raise MarshmallowValidationError("Value cannot be an empty dictionary")
    return verify_uuid_format(value)


class BaseSchemaWithExclude(MarshmallowSchema):
    """Base with Meta.unknown = EXCLUDE for APIs that must ignore unknown fields."""

    class Meta:
        unknown = EXCLUDE
