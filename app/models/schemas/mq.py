from marshmallow import Schema as MarshmallowSchema
from marshmallow import ValidationError as MarshmallowValidationError
from marshmallow import fields
from marshmallow import pre_load
from marshmallow import validate as marshmallow_validate
from marshmallow import validates

from app.validators import verify_uuid_format


class HostIdListSchema(MarshmallowSchema):
    host_ids = fields.List(fields.Str(validate=verify_uuid_format), required=False)

    @validates("host_ids")
    def validate_host_ids(self, host_ids, data_key):  # noqa: ARG002, required for marshmallow validator functions
        if host_ids is not None and len(host_ids) != len(set(host_ids)):
            raise MarshmallowValidationError("Host IDs must be unique.")


class RequiredHostIdListSchema(HostIdListSchema):
    host_ids = fields.List(fields.Str(validate=verify_uuid_format), required=True)

    @validates("host_ids")
    def validate_host_ids(self, host_ids, data_key):  # noqa: ARG002, required for marshmallow validator functions
        if len(host_ids) == 0:
            raise MarshmallowValidationError("Body content must be an array with system UUIDs, not an empty array")
        # Call parent validation for duplicate checking
        super().validate_host_ids(host_ids, data_key)


class InputGroupSchema(HostIdListSchema):
    name = fields.Str(validate=marshmallow_validate.Length(min=1, max=255))

    @pre_load
    def strip_whitespace_from_name(self, in_data, **kwargs):
        if "name" in in_data:
            in_data["name"] = in_data["name"].strip()

        return in_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
