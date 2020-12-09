from connexion.decorators.validation import RequestBodyValidator
from jsonschema import Draft7Validator


class DefaultsEnforcingRequestBodyValidator(RequestBodyValidator):
    def __init__(self, *args, **kwargs):
        super(DefaultsEnforcingRequestBodyValidator, self).__init__(
            *args, validator=Draft7Validator, **kwargs)


VALIDATOR_MAP = {
    'body': DefaultsEnforcingRequestBodyValidator
}
