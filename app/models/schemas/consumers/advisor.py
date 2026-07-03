from marshmallow import fields

from app.models.schemas.common import BaseSchemaWithExclude


class AdvisorDataSchema(BaseSchemaWithExclude):
    """Schema for Advisor application data."""

    recommendations = fields.Int(allow_none=True)
    incidents = fields.Int(allow_none=True)
    critical = fields.Int(allow_none=True)
    important = fields.Int(allow_none=True)
    moderate = fields.Int(allow_none=True)
    low = fields.Int(allow_none=True)
