from flask import abort, request
from werkzeug.exceptions import Forbidden

__all__ = ["AuthManager"]

_IDENTITY_HEADER = "x-rh-identity"


def _validate_identity(payload):
    """
    Identity payload validation dummy. Fails if the data is empty.
    """
    if not payload:
        raise ValueError


class AuthManager:
    """
    Authentication manager for a Flask app. Hooks to a request, parses the identity HTTP
    header and either raises an error or makes the identity data available to the views.
    """

    def __init__(self):
        """
        Identities are stored by a request context.
        """
        self.identities = {}

    def _before_request(self):
        """
        Validates the identity HTTP header. Stores the value for it to be available in
        the views. Fails with 403 otherwise.
        """
        try:
            payload = request.headers[_IDENTITY_HEADER]
            _validate_identity(payload)
        except (KeyError, ValueError):
            abort(Forbidden.code)
        else:
            self.identities[request] = payload

    def identity(self):
        """
        Gets the identity data by the current request context.
        """
        return self.identities[request]

    def init_app(self, flask_app):
        """
        Hooks the identity HTTP header parsing to every request.
        """
        flask_app.auth_manager = self
        flask_app.before_request(self._before_request)
