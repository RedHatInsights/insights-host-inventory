from connexion.decorators.validation import RequestBodyValidator
from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError
from jsonschema.validators import extend


def validate_property_names(validator, property_names, instance, schema):
    if not validator.is_type(instance, "object"):
        return

    prop_length = property_names["minLength"]
    if any(len(key) < prop_length for key in instance.keys()):
        yield ValidationError(f"{instance!r} key length is less than {prop_length!r}")


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
