import contextlib

from marshmallow import ValidationError as MarshmallowValidationError
from marshmallow import fields
from marshmallow import validate as marshmallow_validate
from marshmallow import validates_schema

from app.models.schemas.common import BaseSchemaWithExclude
from app.models.schemas.common import verify_uuid_format_not_empty_dict
from app.validators import verify_satellite_id
from app.validators import verify_uuid_format


class OutboxEventMetadataSchema(BaseSchemaWithExclude):
    local_resource_id = fields.Raw(validate=verify_uuid_format, required=True)
    api_href = fields.Str(validate=marshmallow_validate.Length(min=1, max=2048), required=True)
    console_href = fields.Str(validate=marshmallow_validate.Length(min=1, max=2048), required=True)
    reporter_version = fields.Str(validate=marshmallow_validate.Length(min=1, max=50), required=True)
    transaction_id = fields.UUID(required=True)


class OutboxEventCommonSchema(BaseSchemaWithExclude):
    workspace_id = fields.Raw(validate=verify_uuid_format_not_empty_dict, allow_none=False, required=True)


class OutboxEventReporterSchema(BaseSchemaWithExclude):
    satellite_id = fields.Str(validate=verify_satellite_id, allow_none=True)
    subscription_manager_id = fields.Str(validate=verify_uuid_format, allow_none=True)
    insights_id = fields.Raw(validate=verify_uuid_format, allow_none=True)
    ansible_host = fields.Str(validate=marshmallow_validate.Length(max=255), allow_none=True)

    @validates_schema
    def validate_at_least_one_field(self, data, **kwargs):
        """Ensure at least one field has a non-none value."""
        fields_to_check = ["satellite_id", "subscription_manager_id", "insights_id", "ansible_host"]
        if all(data.get(field) is None for field in fields_to_check):
            raise MarshmallowValidationError("At least one field must have a non-none value")


class OutboxEventRepresentationsSchema(BaseSchemaWithExclude):
    metadata = fields.Nested(OutboxEventMetadataSchema, required=True)
    common = fields.Nested(OutboxEventCommonSchema, required=True)
    reporter = fields.Nested(OutboxEventReporterSchema, required=True)


class OutboxCreateUpdatePayloadSchema(BaseSchemaWithExclude):
    type = fields.Str(validate=marshmallow_validate.OneOf(["host"]), required=True)
    reporter_type = fields.Str(validate=marshmallow_validate.OneOf(["hbi"]), required=True)
    reporter_instance_id = fields.Str(validate=marshmallow_validate.Length(min=1, max=255), required=True)
    representations = fields.Nested(OutboxEventRepresentationsSchema, required=True)


class OutboxDeleteReporterSchema(BaseSchemaWithExclude):
    type = fields.Str(validate=marshmallow_validate.OneOf(["HBI"]), required=True)


class OutboxDeleteReferenceSchema(BaseSchemaWithExclude):
    resource_type = fields.Str(validate=marshmallow_validate.OneOf(["host"]), required=True)
    resource_id = fields.Raw(validate=verify_uuid_format, allow_none=True)
    reporter = fields.Nested(OutboxDeleteReporterSchema, required=True)


class OutboxDeletePayloadSchema(BaseSchemaWithExclude):
    reference = fields.Nested(OutboxDeleteReferenceSchema, required=True)


class OutboxSchema(BaseSchemaWithExclude):
    id = fields.Raw(validate=verify_uuid_format, dump_only=True)
    aggregatetype = fields.Str(validate=marshmallow_validate.Length(min=1, max=255), load_default="hbi.hosts")
    aggregateid = fields.Raw(validate=verify_uuid_format, required=True)
    operation = fields.Str(validate=marshmallow_validate.Length(min=1, max=255), required=True)
    version = fields.Str(validate=marshmallow_validate.Length(min=1, max=50), required=True)
    payload = fields.Raw(required=True)

    @validates_schema
    def validate_payload_with_operation(self, data, **kwargs):
        operation = data.get("operation")
        payload = data.get("payload")

        if operation and payload:
            if operation in ["created", "updated"]:
                OutboxCreateUpdatePayloadSchema().load(payload)
            elif operation == "delete":
                OutboxDeletePayloadSchema().load(payload)
            else:
                # Allow other operation types but still validate payload structure if it matches known patterns
                with contextlib.suppress(MarshmallowValidationError):
                    OutboxCreateUpdatePayloadSchema().load(payload)
                with contextlib.suppress(MarshmallowValidationError):
                    OutboxDeletePayloadSchema().load(payload)
                # If payload doesn't match either schema, that's okay for unknown operations

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
