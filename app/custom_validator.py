from connexion.decorators.validation import RequestBodyValidator
from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError
from jsonschema.validators import extend


def validate_property_names(validator, property_length, instance, schema):
    # Todo
    yield ValidationError(f"error {property_length}, {instance}")


Draft7RequestValidator = extend(Draft7Validator, {"x-propertyNames": validate_property_names})


class CustomRequestBodyValidator(RequestBodyValidator):
    """
    Extends the connexion RequestBodyValidator with enforcing defaults
    See https://connexion.readthedocs.io/en/latest/request.html#custom-validators
    See https://github.com/zalando/connexion/blob/master/examples/swagger2/enforcedefaults/enforcedefaults.py
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, validator=Draft7RequestValidator, **kwargs)


VALIDATOR_MAP = {"body": CustomRequestBodyValidator}
