from unittest import TestCase

import pytest
from jsonschema import Draft4Validator
from jsonschema import Draft7Validator
from jsonschema import RefResolver
from jsonschema.exceptions import ValidationError
from jsonschema.validators import extend
from yaml import safe_load

from tests.helpers.system_profile_utils import INVALID_SYSTEM_PROFILES
from tests.helpers.system_profile_utils import VALID_SYSTEM_PROFILES

CustomDraft4Validator = extend(Draft4Validator, {"x-propertyNames": Draft7Validator.VALIDATORS.get("propertyNames")})


class SystemProfileTests(TestCase):
    def setUp(self):
        super().setUp()

        with open("swagger/system_profile.spec.yaml") as spec_yaml:
            self.specification = safe_load(spec_yaml)
            self.resolver = RefResolver.from_schema(self.specification)

    def test_system_profile_invalids(self):
        for system_profile in INVALID_SYSTEM_PROFILES:
            with self.subTest(system_profile=system_profile):
                with pytest.raises(ValidationError):
                    CustomDraft4Validator(
                        self.specification["$defs"]["SystemProfile"], resolver=self.resolver
                    ).validate(system_profile)

    def test_system_profile_valids(self):
        for system_profile in VALID_SYSTEM_PROFILES:
            with self.subTest(system_profile=system_profile):
                CustomDraft4Validator(self.specification["$defs"]["SystemProfile"], resolver=self.resolver).validate(
                    system_profile
                )
