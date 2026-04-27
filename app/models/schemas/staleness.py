from marshmallow import Schema as MarshmallowSchema
from marshmallow import ValidationError as MarshmallowValidationError
from marshmallow import fields
from marshmallow import validate as marshmallow_validate
from marshmallow import validates_schema

from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS


class StalenessSchema(MarshmallowSchema):
    conventional_time_to_stale = fields.Integer(
        validate=marshmallow_validate.Range(min=1, max=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS)
    )
    conventional_time_to_stale_warning = fields.Integer(validate=marshmallow_validate.Range(min=1, max=15552000))
    conventional_time_to_delete = fields.Integer(validate=marshmallow_validate.Range(min=1, max=63072000))

    @validates_schema
    def validate_staleness(self, data, **kwargs):
        staleness_fields = ["time_to_stale", "time_to_stale_warning", "time_to_delete"]
        for i in range(len(staleness_fields) - 1):
            for j in range(i + 1, len(staleness_fields)):
                if (
                    data[(field_1 := f"conventional_{staleness_fields[i]}")]
                    >= data[(field_2 := f"conventional_{staleness_fields[j]}")]
                ):
                    raise MarshmallowValidationError(f"{field_1} must be lower than {field_2}")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
