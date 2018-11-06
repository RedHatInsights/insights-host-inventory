from app.auth import AuthManager, _validate_identity
from unittest import main, TestCase
from unittest.mock import Mock, patch


class AuthManagerTestCase(TestCase):
    """
    Tests the Authentication Manager, the binding between the Flask app and the identity
    HTTP header parser/validator.
    """

    def setUp(self):
        """
        Instantiates the Authentication Manager.
        """
        self.auth_manager = AuthManager()

    def test_init_app_access(self):
        """
        The Authentication Manager instance is accessible from the Flask Application.
        """
        app = Mock()
        self.auth_manager.init_app(app)
        self.assertEqual(self.auth_manager, app.auth_manager)

    def test_init_app_before_request(self):
        """
        The Authentication Manager request hook is bound to every request.
        """
        app = Mock()
        self.auth_manager.init_app(app)
        app.before_request.assert_called_once_with(self.auth_manager._before_request)

    def test_identity(self):
        """
        The identity method retrieves a stored identity by the current request context.
        """
        key = "some key"
        value = "some value"
        with patch("app.auth.request", key):
            self.auth_manager.identities = {key: value}
            self.assertEqual(value, self.auth_manager.identity())

    @patch("app.auth.abort")
    @patch("app.auth._validate_identity")
    def test_before_request_validate_identity(self, validate_identity, abort):
        """
        The identity payload is validated. Doesn’t fail if valid.
        """
        payload = "some payload"
        with patch("app.auth.request", **{"headers": {"x-rh-identity": payload}}):
            self.auth_manager._before_request()

        validate_identity.assert_called_once_with(payload)
        abort.assert_not_called()

    @patch("app.auth.abort")
    @patch("app.auth._validate_identity")
    def test_before_request_missing_abort(self, validate_identity, abort):
        """
        The identity header is missing. Fails with 403 (Forbidden).
        """
        with patch("app.auth.request", **{"headers": {}}):
            self.auth_manager._before_request()

        validate_identity.assert_not_called()
        abort.assert_called_once_with(403)  # Forbidden

    def test_before_request_invalid_abort(self):
        """
        The identity payload is validated. Fails with 403 (Forbidden) if not valid,
        assuming it can raise KeyError or ValueError.
        """
        payload = "some payload"

        @patch("app.auth.abort")
        def _test(abort):
            with patch("app.auth.request", **{"headers": {"x-rh-identity": payload}}):
                self.auth_manager._before_request()

            abort.assert_called_once_with(403)  # Forbidden

        errors = [KeyError, ValueError]
        for error in errors:
            with self.subTest(error=error):
                with patch(
                    "app.auth._validate_identity", side_effect=error
                ) as validate_identity:
                    _test()
                    validate_identity.assert_called_once_with(payload)

    @patch("app.auth.abort")
    def test_before_request_error_not_caught(self, abort):
        """
        Any other error during the validation is not caught and does not result in a
        controlled abort.
        """
        payload = "some payload"
        error = RuntimeError
        with patch(
            "app.auth.request", **{"headers": {"x-rh-identity": payload}}
        ) as request:
            with patch(
                "app.auth._validate_identity", side_effect=error
            ) as validate_identity:
                with self.assertRaises(error):
                    self.auth_manager._before_request()

                validate_identity.assert_called_once_with(payload)

        abort.assert_not_called()

    @patch("app.auth._validate_identity")
    def test_before_request_identities(self, validate_identity):
        """
        The identity payload is stored by the current request context.
        """
        payload = "some payload"
        with patch(
            "app.auth.request", **dict(headers={"x-rh-identity": payload})
        ) as request:
            self.auth_manager._before_request()
            self.assertIn(request, self.auth_manager.identities)
            self.assertEqual(payload, self.auth_manager.identities[request])

    @patch("app.auth._validate_identity")
    def test_get_identity_from_header(self, validate_identity):
        """
        The identity payload is stored on request and retrieved by the identity method.
        """
        payload = "some payload"
        with patch(
            "app.auth.request", **{"headers": {"x-rh-identity": payload}}
        ) as request:
            self.auth_manager._before_request()
            self.assertEqual(payload, self.auth_manager.identity())


class ValidationTestCase(TestCase):
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
