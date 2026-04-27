from marshmallow import Schema as MarshmallowSchema
from marshmallow import fields
from marshmallow import validate as marshmallow_validate

from app.validators import verify_uuid_format


class ComplianceDataPolicySchema(MarshmallowSchema):
    """Schema for a compliance policy entry."""

    id = fields.Str(validate=verify_uuid_format, allow_none=False)
    name = fields.Str(allow_none=False, validate=marshmallow_validate.Length(max=255))


class ComplianceDataSchema(MarshmallowSchema):
    """Schema for Compliance application data."""

    policies = fields.List(fields.Nested(ComplianceDataPolicySchema), allow_none=True)
    last_scan = fields.DateTime(allow_none=True)
