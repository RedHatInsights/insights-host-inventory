#!/usr/bin/env python
from base64 import b64encode
from json import dumps
from unittest import main

from .test_api_utils import build_auth_header
from .test_api_utils import build_valid_auth_header
from .test_api_utils import DBAPITestCase
from .test_api_utils import HOST_URL
from .test_utils import set_environment
from app.auth.identity import Identity


class HeaderAuthTestCase(DBAPITestCase):
    @staticmethod
    def _valid_identity():
        """
        Provides a valid Identity object.
        """
        return Identity(account_number="some account number")

    @staticmethod
    def _valid_payload():
        """
        Builds a valid HTTP header payload – Base64 encoded JSON string with valid data.
        """
        identity = __class__._valid_identity()
        dict_ = {"identity": identity._asdict()}
        json = dumps(dict_)
        return b64encode(json.encode())

    def _get_hosts(self, headers):
        """
        Issues a GET request to the /hosts URL, providing given headers.
        """
        return self.client().get(HOST_URL, headers=headers)

    def test_validate_missing_identity(self):
        """
        Identity header is not present.
        """
        response = self._get_hosts({})
        self.assertEqual(401, response.status_code)

    def test_validate_invalid_identity(self):
        """
        Identity header is not valid – empty in this case
        """
        response = self._get_hosts({"x-rh-identity": ""})
        self.assertEqual(401, response.status_code)

    def test_validate_valid_identity(self):
        """
        Identity header is valid – non-empty in this case
        """
        payload = self._valid_payload()
        response = self._get_hosts({"x-rh-identity": payload})
        self.assertEqual(200, response.status_code)  # OK


class TokenAuthTestCase(DBAPITestCase):
    """
    A couple of sanity checks to make sure the service is denying access
    """

    def test_validate_invalid_token_on_GET(self):
        auth_header = build_auth_header("NotTheSuperSecretValue")
        response = self.client().get(HOST_URL, headers=auth_header)
        self.assertEqual(401, response.status_code)

    def test_validate_invalid_token_on_POST(self):
        auth_header = build_auth_header("NotTheSuperSecretValue")
        response = self.client().post(HOST_URL, headers=auth_header)
        self.assertEqual(401, response.status_code)

    def test_validate_token_on_POST_shared_secret_not_set(self):
        with set_environment({}):
            auth_header = build_valid_auth_header()
            response = self.client().post(HOST_URL, headers=auth_header)
            self.assertEqual(401, response.status_code)


if __name__ == "__main__":
    main()
