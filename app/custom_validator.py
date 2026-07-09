import functools
import json
import logging
import typing

from connexion.exceptions import BadRequestProblem
from connexion.exceptions import NonConformingResponseBody
from connexion.json_schema import Draft4ResponseValidator
from connexion.json_schema import format_error_with_path
from connexion.validators.abstract import AbstractResponseBodyValidator
from connexion.validators.parameter import ParameterValidator
from jsonschema import Draft4Validator
from jsonschema import ValidationError
from jsonschema import draft4_format_checker

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
            raise NonConformingResponseBody(str(e)) from e

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
            ) from exception


class CustomParameterValidator(ParameterValidator):
    def __init__(self, *args, system_profile_spec, **kwargs):
        super().__init__(*args, **kwargs)
        self.sp_spec = system_profile_spec

    def _resolve_query_params(self, request):
        return request.query_params

    def _validate_system_profile_field_names(self, fields):
        query_fields = fields.get("system_profile", {}).keys()
        for field in query_fields:
            if field not in self.sp_spec:
                raise BadRequestProblem(
                    detail=f"Requested field '{field}' is not present in the system_profile schema."
                )

    def _validate_sparse_fields(self, fields):
        if not fields or "system_profile" not in fields:
            raise BadRequestProblem(detail="Invalid sparse fields")

        self._validate_system_profile_field_names(fields)

    def _validate_host_view_sparse_fields(self, fields):
        if not fields:
            raise BadRequestProblem(detail="Invalid host view sparse fields")

        if "system_profile" in fields:
            self._validate_system_profile_field_names(fields)

    def validate_query_parameter_list(self, request, security_params=None):
        query_params = self._resolve_query_params(request)

        for param in self.parameters.get("query", []):
            validator_name = param.get("x-validator")
            param_name = param.get("name")

            if validator_name not in {"sparseFields", "hostViewSparseFields"} or param_name not in query_params:
                continue

            fields = query_params.get(param_name)
            if validator_name == "sparseFields":
                self._validate_sparse_fields(fields)
            elif validator_name == "hostViewSparseFields":
                self._validate_host_view_sparse_fields(fields)

        request_params = list(query_params.keys())
        spec_params = [x.get("name") for x in self.parameters.get("query", [])]
        if security_params:
            spec_params.extend(security_params)
        return self.validate_parameter_list(request_params, spec_params)


def build_validator_map(system_profile_spec):
    return {
        "response": {"application/json": CustomResponseValidator},
        "parameter": functools.partial(CustomParameterValidator, system_profile_spec=system_profile_spec),
    }
