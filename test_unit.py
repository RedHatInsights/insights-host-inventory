from app.auth import (
    _before_request,
    current_identity,
    _get_identity,
    init_app,
    _validate_identity,
)
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

    @patch("app.auth._validate_identity")
    @patch("app.auth.abort", side_effect=Abort)
    @patch("app.auth.request", **{"headers": {}})
    def test_missing_header(self, request, abort, validate_identity):
        """
        The identity HTTP header is missing. Fails with 403 (Forbidden).
        """
        with self.assertRaises(Abort):
            _before_request()

        abort.assert_called_once_with(403)  # Forbidden
        validate_identity.assert_not_called()

    def test_identity_invalid(self):
        """
        The identity payload is validated. Fails with 403 (Forbidden) if not parsable or
        otherwise invalid.
        """
        payload = "some payload"

        @patch("app.auth.abort", side_effect=Abort)
        def _test(abort):
            with patch("app.auth.request", **{"headers": {"x-rh-identity": payload}}):
                with self.assertRaises(Abort):
                    _before_request()

            abort.assert_called_once_with(403)  # Forbidden

        errors = [TypeError, ValueError]
        for error in errors:
            with self.subTest(error=error):
                with patch(
                    "app.auth._validate_identity", side_effect=error
                ) as validate_identity:
                    _test()
                    validate_identity.assert_called_once_with(payload)

    @patch("app.auth.abort")
    @patch("app.auth._validate_identity", side_effect=RuntimeError)
    def test_error_not_caught(self, validate_identity, abort):
        """
        Any other error during the validation is not caught and does not result in a
        controlled abort.
        """
        payload = "some payload"
        error = RuntimeError
        with patch("app.auth.request", **{"headers": {"x-rh-identity": payload}}):
            with self.assertRaises(error):
                _before_request()

        validate_identity.assert_called_once_with(payload)
        abort.assert_not_called()

    @patch("app.auth._request_ctx_stack")
    @patch("app.auth.abort", side_effect=Abort)
    @patch("app.auth._validate_identity")
    def test_identity_valid(self, validate_identity, abort, request_ctx_stack):
        """
        The identity payload is validated. Doesn’t fail if valid.
        """
        payload = "some payload"
        with patch("app.auth.request", **{"headers": {"x-rh-identity": payload}}):
            _before_request()

        validate_identity.assert_called_once_with(payload)
        abort.assert_not_called()

    @patch("app.auth._request_ctx_stack")
    @patch("app.auth._validate_identity")
    def test_store_identity(self, validate_identity, request_ctx_stack):
        """
        The identity payload is stored by the current request context.
        """
        payload = "some payload"
        with patch(
            "app.auth.request", **dict(headers={"x-rh-identity": payload})
        ) as request:
            _before_request()
            self.assertEqual(payload, request_ctx_stack.top.identity)


class AuthValidateIdentityTestCase(TestCase):
    """
    Tests the dummy identity validator.
    """

    def test_valid(self):
        """
        Any non-empty identity payload is considered valid.
        """
        _validate_identity("some payload")
        self.assertTrue(True)

    def test_invalid(self):
        """
        An empty identity payload is not valid.
        """
        payloads = {None, ""}
        for payload in payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    _validate_identity(payload)


if __name__ == "__main__":
    main()
