from marshmallow import Schema as MarshmallowSchema
from marshmallow import fields


class AdvisorDataSchema(MarshmallowSchema):
    """Schema for Advisor application data."""

    recommendations = fields.Int(allow_none=True)
    incidents = fields.Int(allow_none=True)
    critical = fields.Int(allow_none=True)
    important = fields.Int(allow_none=True)
    moderate = fields.Int(allow_none=True)
    low = fields.Int(allow_none=True)
