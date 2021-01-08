from connexion.decorators.response import ResponseValidator
from connexion.json_schema import Draft4ResponseValidator
from jsonschema import Draft7Validator
from jsonschema.validators import extend


def get_draft4_custom_validators():
    """
    Copies over the custom validators from connexion's Draft4ResponseValidator and returns them in a new dictionary
    """
    custom_validator_names = ["type", "enum", "required", "writeOnly", "x-writeOnly"]
    custom_validators = {}

    for name in custom_validator_names:
        custom_validators[name] = Draft4ResponseValidator.VALIDATORS.get(name)

    return custom_validators


def get_custom_validator():
    custom_validators = get_draft4_custom_validators()
    CustomDraft7Validator = extend(
        Draft7Validator, {**custom_validators, "x-propertyNames": Draft7Validator.VALIDATORS.get("propertyNames")}
    )
    return CustomDraft7Validator


class CustomResponseValidator(ResponseValidator):
    """
    Extends the connexion ResponseValidator with x-propertyNames
    See https://connexion.readthedocs.io/en/latest/request.html#custom-validators
    See https://github.com/zalando/connexion/blob/master/examples/swagger2/enforcedefaults/enforcedefaults.py
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, validator=get_custom_validator(), **kwargs)


VALIDATOR_MAP = {"response": CustomResponseValidator}
