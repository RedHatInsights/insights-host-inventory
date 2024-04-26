import functools
import json
import logging
import typing

import flask
from connexion.exceptions import NonConformingResponseBody
from connexion.json_schema import Draft4ResponseValidator
from connexion.json_schema import format_error_with_path
from connexion.validators.abstract import AbstractResponseBodyValidator
from connexion.validators.parameter import ParameterValidator
from jsonschema import draft4_format_checker
from jsonschema import Draft4Validator
from jsonschema import ValidationError


logger = logging.getLogger(__name__)


class CustomResponseValidator(AbstractResponseBodyValidator):
    """Response body validator for json content types."""

    @property
    def validator(self) -> Draft4Validator:
        return Draft4ResponseValidator(self._schema, format_checker=draft4_format_checker)

    def _parse(self, stream: typing.Generator[bytes, None, None]) -> typing.Any:
        body = b"".join(stream).decode(self._encoding)

        if not body:
            return None

        try:
            return json.loads(body)
        except json.decoder.JSONDecodeError as e:
            raise NonConformingResponseBody(str(e))

    def _validate(self, body: dict):
        try:
            self.validator.validate(body)
        except ValidationError as exception:
            error_path_msg = format_error_with_path(exception=exception)
            logger.error(
                f"Validation error: {exception.message}{error_path_msg}",
                extra={"validator": "body"},
            )
            raise NonConformingResponseBody(
                detail=f"Response body does not conform to specification. {exception.message}{error_path_msg}"
            )


class CustomParameterValidator(ParameterValidator):
    def __init__(self, *args, system_profile_spec, unindexed_fields, **kwargs):
        super().__init__(*args, **kwargs)
        self.sp_spec = system_profile_spec
        self.unindexed_fields = unindexed_fields

    def validate_query_parameter_list(self, request):
        for param in [
            p
            for p in self.parameters.get("query", [])
            if p.get("x-validator") == "sparseFields" and request.query.get(p["name"])
        ]:
            fields = request.query[param["name"]]
            if "system_profile" in fields:
                query_fields = list(fields.get("system_profile").keys())
                system_profile_schema = self.sp_spec
                unindexed_fields = self.unindexed_fields
                for field in query_fields:
                    if field in unindexed_fields:
                        flask.abort(400, f"Requested field '{field}' is not indexed and not filterable.")
                    if field not in system_profile_schema.keys():
                        flask.abort(400, f"Requested field '{field}' is not present in the system_profile schema.")
            else:
                flask.abort(400)

        return super().validate_query_parameter_list(request)


def build_validator_map(system_profile_spec, unindexed_fields):
    return {
        "response": {"application/json": CustomResponseValidator},
        "parameter": functools.partial(
            CustomParameterValidator, system_profile_spec=system_profile_spec, unindexed_fields=unindexed_fields
        ),
    }
