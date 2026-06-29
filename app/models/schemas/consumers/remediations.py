from marshmallow import fields

from app.models.schemas.common import BaseSchemaWithExclude


class RemediationsDataSchema(BaseSchemaWithExclude):
    """Schema for Remediations application data."""

    remediations_plans = fields.Int(allow_none=True)
