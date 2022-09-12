import functools

import flask
from connexion.decorators.response import ResponseValidator
from connexion.decorators.validation import ParameterValidator
from connexion.json_schema import Draft4ResponseValidator
from jsonschema import Draft7Validator
from jsonschema.validators import extend


CustomDraft4ResponseValidator = extend(
    Draft4ResponseValidator, {"x-propertyNames": Draft7Validator.VALIDATORS.get("propertyNames")}
)


class CustomResponseValidator(ResponseValidator):
    """
    Extends the connexion ResponseValidator with x-propertyNames
    See https://connexion.readthedocs.io/en/latest/request.html#custom-validators
    See https://github.com/zalando/connexion/blob/master/examples/swagger2/enforcedefaults/enforcedefaults.py
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, validator=CustomDraft4ResponseValidator, **kwargs)


class CustomParameterValidator(ParameterValidator):
    def __init__(self, *args, system_profile_spec, **kwargs):
        super().__init__(*args, **kwargs)
        self.sp_spec = system_profile_spec
        self.strict_validation = True

    def validate_query_parameter_list(self, request):
        super().validate_query_parameter_list(request)
        for param in [
            p
            for p in self.parameters.get("query", [])
            if p.get("x-validator") == "sparseFields" and request.query.get(p["name"])
        ]:
            fields = request.query[param["name"]]
            if "system_profile" in fields:
                query_fields = list(fields.get("system_profile").keys())
                system_profile_schema = self.sp_spec
                for field in query_fields:
                    if field not in system_profile_schema.keys():
                        flask.abort(400, f"Requested field '{field}' is not present in the system_profile schema.")
            else:
                flask.abort(400)


def build_validator_map(system_profile_spec):
    return {
        "response": CustomResponseValidator,
        "parameter": functools.partial(CustomParameterValidator, system_profile_spec=system_profile_spec),
    }
