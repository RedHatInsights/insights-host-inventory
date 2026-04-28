from itertools import pairwise

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
        fields_in_order = [
            "time_to_stale",
            "time_to_stale_warning",
            "time_to_delete",
        ]
        present = [(name, data[f"conventional_{name}"]) for name in fields_in_order if f"conventional_{name}" in data]
        for (prev_name, prev_value), (curr_name, curr_value) in pairwise(present):
            if prev_value >= curr_value:
                field_1 = f"conventional_{prev_name}"
                field_2 = f"conventional_{curr_name}"
                raise MarshmallowValidationError(f"{field_1} must be lower than {field_2}")
