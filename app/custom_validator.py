import six
import jsonschema
from connexion.decorators.validation import RequestBodyValidator

def extend_with_set_default(validator_class):
    """
    Extends given validator class with setting defaults as specified in specification
    :param validator_class:
    :return:
    """
    validate_properties = validator_class.VALIDATORS['properties']

    def set_defaults(validator, properties, instance, schema):
        for property, subschema in six.iteritems(properties):
            if 'default' in subschema:
                instance.setdefault(property, subschema['default'])

        for error in validate_properties(
                validator, properties, instance, schema):
            yield error

    return jsonschema.validators.extend(
        validator_class, {'properties': set_defaults})


DefaultsEnforcingDraftValidator = extend_with_set_default(jsonschema.Draft7Validator)


class DefaultsEnforcingRequestBodyValidator(RequestBodyValidator):
    """
    Extends the connexion RequestBodyValidator with enforcing defaults
    See https://connexion.readthedocs.io/en/latest/request.html#custom-validators
    See https://github.com/zalando/connexion/blob/master/examples/swagger2/enforcedefaults/enforcedefaults.py
    """
    def __init__(self, *args, **kwargs):
        super(DefaultsEnforcingRequestBodyValidator, self).__init__(
            *args, validator=DefaultsEnforcingDraftValidator, **kwargs)

VALIDATOR_MAP = {'body': DefaultsEnforcingRequestBodyValidator}