from marshmallow import Schema as MarshmallowSchema
from marshmallow import fields


class RemediationsDataSchema(MarshmallowSchema):
    """Schema for Remediations application data."""

    remediations_plans = fields.Int(allow_none=True)
