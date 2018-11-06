from app.auth.identity import from_dict, from_encoded, from_json, Identity, validate
from base64 import b64encode
from json import dumps
from unittest import main, TestCase


class IdentityConstructorTestCase(TestCase):
    """
    Test the Identity module: the named tuple, its constructors and validation.
    """

    @staticmethod
    def _identity():
        return Identity(account_number="some number", org_id="some org id")

    def test_from_dict_valid(self):
        """
        Initialize the Identity object with a valid dictionary.
        """
        identity = self._identity()

        dict_ = {"account_number": identity.account_number, "org_id": identity.org_id}

        self.assertEqual(identity, from_dict(dict_))

    def test_from_dict_invalid(self):
        """
        Initializing the Identity object with a dictionary with missing values or with
        anything else should raise TypeError.
        """
        dicts = [
            {},
            {"account_number": "some account number"},
            {"org_id": "some org id"},
            "some string",
            ["some", "list"],
        ]
        for dict_ in dicts:
            with self.assertRaises(TypeError):
                from_dict(dict_)

    def test_from_json_valid(self):
        """
        Initialize the Identity object with a valid JSON string.
        """
        identity = self._identity()

        dict_ = identity._asdict()
        json = dumps(dict_)

        try:
            self.assertEqual(identity, from_json(json))
        except (TypeError, ValueError):
            self.fail()

    def test_from_json_invalid_type(self):
        """
        Initializing the Identity object with an invalid type that can’t be JSON should
        raise a TypeError.
        """
        with self.assertRaises(TypeError):
            from_json(["not", "a", "string"])

    def test_from_json_invalid_value(self):
        """
        Initializing the Identity object with an invalid JSON string should raise a
        ValueError.
        """
        with self.assertRaises(ValueError):
            from_json("invalid JSON")

    def test_from_encoded_valid(self):
        """
        Initialize the Identity object with an encoded payload – a base64-encoded JSON.
        That would typically be a raw HTTP header content.
        """
        identity = self._identity()

        dict_ = identity._asdict()
        json = dumps(dict_)
        base64 = b64encode(json.encode())

        try:
            self.assertEqual(identity, from_encoded(base64))
        except (TypeError, ValueError):
            self.fail()

    def test_from_encoded_invalid_type(self):
        """
        Initializing the Identity object with an invalid type that can’t be a Base64
        encoded payload should raise a TypeError.
        """
        with self.assertRaises(TypeError):
            from_encoded(["not", "a", "string"])

    def test_from_encoded_invalid_value(self):
        """
        Initializing the Identity object with an invalid Base6č encoded payload should
        raise a ValueError.
        """
        with self.assertRaises(ValueError):
            from_encoded("invalid Base64")


class IdentityValidateTestCase(TestCase):
    def test_validate_valid(self):
        try:
            identity = Identity(account_number="some number", org_id="some org id")
            validate(identity)
            self.assertTrue(True)
        except ValueError:
            self.fail()

    def test_validate_invalid(self):
        identities = [
            Identity(account_number=None, org_id=None),
            Identity(account_number=None, org_id="some org_id"),
            Identity(account_number="some account_number", org_id=None),
        ]
        for identity in identities:
            with self.subTest(identity=identity):
                with self.assertRaises(ValueError):
                    validate(identity)


if __name__ == "__main__":
    main()
