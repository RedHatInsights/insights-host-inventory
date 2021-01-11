from connexion.decorators.response import ResponseValidator
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


VALIDATOR_MAP = {"response": CustomResponseValidator}
