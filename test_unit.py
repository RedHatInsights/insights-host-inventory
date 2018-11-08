#!/usr/bin/env python

from app.auth import _before_request, current_identity, _get_identity, init_app
from app.auth.identity import from_dict, from_encoded, from_json, Identity, validate
from base64 import b64encode
from json import dumps
from unittest import main, TestCase
from unittest.mock import Mock, patch
from werkzeug.local import LocalProxy


class Abort(Exception):
    pass


class AuthInitAppTestCase(TestCase):
    """
    Test the before request hook binding to the Flask app.
    """

    def test_init_app(self):
        """
        The before request hook is bound to the Flask app.
        """
        app = Mock()
        init_app(app)
        app.before_request.assert_called_once_with(_before_request)


class AuthGetIdentityTestCase(TestCase):
    """
    Tests retrieving the identity from the request context.
    """

    @patch("app.auth._request_ctx_stack")
    def test_get_identity(self, request_ctx_stack):
        """
        The Authentication Manager request hook is bound to every request.
        """
        self.assertEqual(request_ctx_stack.top.identity, _get_identity())


class AuthCurrentIdentityTestCase(TestCase):
    """
    Tests retrieving the identity from the request context through Werkzeug‘s local
    proxy.
    """

    @patch("app.auth._request_ctx_stack")
    def test_get_identity(self, request_ctx_stack):
        """
        The Authentication Manager request hook is bound to every request.
        """
        self.assertIsInstance(current_identity, LocalProxy)
        self.assertEqual(request_ctx_stack.top.identity, current_identity)


class AuthBeforeRequestTestCase(TestCase):
    """
    Tests the before request hook that passes the HTTP header to the parser/validator.
    """

    @patch("app.auth.validate")
    @patch("app.auth.from_encoded")
    @patch("app.auth.abort", side_effect=Abort)
    @patch("app.auth.request", **{"headers": {}})
    def test_missing_header(self, request, abort, from_encoded, validate):
        """
        The identity HTTP header is missing. Fails with 403 (Forbidden).
        """
        with self.assertRaises(Abort):
            _before_request()

        abort.assert_called_once_with(403)  # Forbidden
        from_encoded.assert_not_called()
        validate.assert_not_called()

    def test_identity_undecodable(self):
        """
        The identity payload cannot be decoded. Fails with 403 (Forbidden) and is not
        even validated.
        """
        payload = "some payload"

        @patch("app.auth.abort", side_effect=Abort)
        @patch("app.auth.validate")
        def _test(validate, abort):
            with patch("app.auth.request", **{"headers": {"x-rh-identity": payload}}):
                with self.assertRaises(Abort):
                    _before_request()

            abort.assert_called_once_with(403)  # Forbidden
            validate.assert_not_called()

        errors = [TypeError, ValueError]
        for error in errors:
            with self.subTest(error=error):
                with patch(
                    "app.auth.from_encoded", side_effect=error
                ) as from_encoded_mock:
                    _test()
                    from_encoded_mock.assert_called_once_with(payload)

    @patch("app.auth.abort")
    @patch("app.auth.validate")
    @patch("app.auth.from_encoded", side_effect=RuntimeError)
    def test_from_encoded_error_not_caught(
        self, from_encoded_mock, validate_mock, abort
    ):
        """
        Any other error during the parsing is not caught and does not result in a
        controlled abort.
        """
        payload = "some payload"
        with patch("app.auth.request", **{"headers": {"x-rh-identity": payload}}):
            with self.assertRaises(RuntimeError):
                _before_request()

            from_encoded_mock.assert_called_once_with(payload)
            validate_mock.assert_not_called()

        abort.assert_not_called()

    @patch("app.auth.abort", side_effect=Abort)
    @patch("app.auth.validate", side_effect=ValueError)
    @patch("app.auth.from_encoded")
    def test_identity_invalid(self, from_encoded_mock, validate_mock, abort):
        """
        The identity payload is validated. Fails with 403 (Forbidden) if not valid.
        """
        payload = "some payload"

        with patch("app.auth.request", **{"headers": {"x-rh-identity": payload}}):
            with self.assertRaises(Abort):
                _before_request()

        abort.assert_called_once_with(403)  # Forbidden
        from_encoded_mock.assert_called_once_with(payload)
        validate_mock.assert_called_once_with(from_encoded_mock.return_value)

    @patch("app.auth.abort")
    @patch("app.auth.validate", side_effect=RuntimeError)
    @patch("app.auth.from_encoded")
    def test_validate_error_not_caught(self, from_encoded_mock, validate_mock, abort):
        """
        Any other error during the validation is not caught and does not result in a
        controlled abort.
        """
        payload = "some payload"
        with patch("app.auth.request", **{"headers": {"x-rh-identity": payload}}):
            with self.assertRaises(RuntimeError):
                _before_request()

            from_encoded_mock.assert_called_once_with(payload)
            validate_mock.assert_called_once_with(from_encoded_mock.return_value)

        abort.assert_not_called()

    @patch("app.auth._request_ctx_stack")
    @patch("app.auth.abort", side_effect=Abort)
    @patch("app.auth.validate")
    @patch("app.auth.from_encoded")
    def test_everything_ok(
        self, from_encoded_mock, validate_mock, abort, request_ctx_stack
    ):
        """
        The identity payload is decoded and validated. Doesn’t fail if valid.
        """
        payload = "some payload"
        with patch("app.auth.request", **{"headers": {"x-rh-identity": payload}}):
            _before_request()

        from_encoded_mock.assert_called_once_with(payload)
        validate_mock.assert_called_once_with(from_encoded_mock.return_value)
        abort.assert_not_called()

    @patch("app.auth._request_ctx_stack")
    @patch("app.auth.validate")
    @patch("app.auth.from_encoded")
    @patch("app.auth.request")
    def test_store_identity(
        self, request, from_encoded_mock, validate_mock, request_ctx_stack
    ):
        """
        The identity payload is stored by the current request context.
        """
        _before_request()
        self.assertEqual(from_encoded_mock.return_value, request_ctx_stack.top.identity)


class AuthIdentityConstructorTestCase(TestCase):
    """
    Tests the Identity module constructors.
    """

    @staticmethod
    def _identity():
        return Identity(account_number="some number", org_id="some org id")


class AuthIdentityFromDictTest(AuthIdentityConstructorTestCase):
    """
    Tests creating an Identity from a dictionary.
    """

    def test_valid(self):
        """
        Initialize the Identity object with a valid dictionary.
        """
        identity = self._identity()

        dict_ = {"account_number": identity.account_number, "org_id": identity.org_id}

        self.assertEqual(identity, from_dict(dict_))

    def test_invalid(self):
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


class AuthIdentityFromJsonTest(AuthIdentityConstructorTestCase):
    """
    Tests creating an Identity from a JSON string.
    """

    def test_valid(self):
        """
        Initialize the Identity object with a valid JSON string.
        """
        identity = self._identity()

        dict_ = {"identity": identity._asdict()}
        json = dumps(dict_)

        try:
            self.assertEqual(identity, from_json(json))
        except (TypeError, ValueError):
            self.fail()

    def test_invalid_type(self):
        """
        Initializing the Identity object with an invalid type that can’t be JSON should
        raise a TypeError.
        """
        with self.assertRaises(TypeError):
            from_json(["not", "a", "string"])

    def test_invalid_value(self):
        """
        Initializing the Identity object with an invalid JSON string should raise a
        ValueError.
        """
        with self.assertRaises(ValueError):
            from_json("invalid JSON")

    def test_invalid_format(self):
        """
        Initializing the Identity object with a JSON string that is not
        formatted correctly.
        """
        identity = self._identity()

        dict_ = identity._asdict()
        json = dumps(dict_)

        with self.assertRaises(KeyError):
            from_json(json)


class AuthIdentityFromEncodedTest(AuthIdentityConstructorTestCase):
    """
    Tests creating an Identity from a Base64 encoded JSON string, which is what is in
    the HTTP header.
    """

    def test_valid(self):
        """
        Initialize the Identity object with an encoded payload – a base64-encoded JSON.
        That would typically be a raw HTTP header content.
        """
        identity = self._identity()

        dict_ = {"identity": identity._asdict()}
        json = dumps(dict_)
        base64 = b64encode(json.encode())

        try:
            self.assertEqual(identity, from_encoded(base64))
        except (TypeError, ValueError):
            self.fail()

    def test_invalid_type(self):
        """
        Initializing the Identity object with an invalid type that can’t be a Base64
        encoded payload should raise a TypeError.
        """
        with self.assertRaises(TypeError):
            from_encoded(["not", "a", "string"])

    def test_invalid_value(self):
        """
        Initializing the Identity object with an invalid Base6č encoded payload should
        raise a ValueError.
        """
        with self.assertRaises(ValueError):
            from_encoded("invalid Base64")

    def test_invalid_format(self):
        """
        Initializing the Identity object with an valid Base64 encoded payload
        that does not contain the "identity" field.
        """
        identity = self._identity()

        dict_ = identity._asdict()
        json = dumps(dict_)
        base64 = b64encode(json.encode())

        with self.assertRaises(KeyError):
            from_encoded(base64)


class AuthIdentityValidateTestCase(TestCase):
    def test_valid(self):
        try:
            identity = Identity(account_number="some number", org_id="some org id")
            validate(identity)
            self.assertTrue(True)
        except ValueError:
            self.fail()

    def test_invalid(self):
        identities = [
            Identity(account_number=None, org_id=None),
            Identity(account_number="", org_id=""),
            Identity(account_number=None, org_id="some org_id"),
            Identity(account_number="", org_id="some org_id"),
            Identity(account_number="some account_number", org_id=None),
            Identity(account_number="some account_number", org_id=""),
        ]
        for identity in identities:
            with self.subTest(identity=identity):
                with self.assertRaises(ValueError):
                    validate(identity)


if __name__ == "__main__":
    main()
