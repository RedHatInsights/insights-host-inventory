from types import SimpleNamespace

from app.config import _v1_dependency_endpoint_uri
from app.config import resolve_dependency_endpoint_settings


class TestResolveDependencyEndpointSettings:
    def test_uses_v2_when_available(self):
        v2 = SimpleNamespace(uri="https://rbac:8443", ca_certificate="/ca.crt", authenticated=True)
        uri, ca, auth = resolve_dependency_endpoint_settings(
            v2,
            v1_uri="http://old:8080",
            v1_ca_certificate="/old.ca",
        )

        assert uri == "https://rbac:8443"
        assert ca == "/ca.crt"
        assert auth is True

    def test_falls_back_to_v1_when_v2_missing(self):
        uri, ca, auth = resolve_dependency_endpoint_settings(
            None,
            v1_uri="http://rbac:8080",
            v1_ca_certificate="/tls.ca",
        )

        assert uri == "http://rbac:8080"
        assert ca == "/tls.ca"
        assert auth is False

    def test_falls_back_to_v1_when_v2_uri_empty(self):
        v2 = SimpleNamespace(uri="", ca_certificate=None, authenticated=True)
        uri, ca, auth = resolve_dependency_endpoint_settings(
            v2,
            v1_uri="http://rbac:8080",
            v1_ca_certificate="/tls.ca",
        )

        assert uri == "http://rbac:8080"
        assert ca == "/tls.ca"
        assert auth is False


class TestV1DependencyEndpointUri:
    def test_builds_http_uri_without_tls(self):
        endpoint = SimpleNamespace(app="rbac", hostname="rbac.svc", port=8080, tlsPort=8443)

        assert _v1_dependency_endpoint_uri([endpoint], "rbac", None) == "http://rbac.svc:8080"

    def test_builds_https_uri_with_tls_ca(self):
        endpoint = SimpleNamespace(app="rbac", hostname="rbac.svc", port=8080, tlsPort=8443)

        assert _v1_dependency_endpoint_uri([endpoint], "rbac", "/ca.crt") == "https://rbac.svc:8443"

    def test_returns_empty_string_when_app_not_found(self):
        endpoint = SimpleNamespace(app="other", hostname="other.svc", port=8080, tlsPort=8443)

        assert _v1_dependency_endpoint_uri([endpoint], "rbac", None) == ""
