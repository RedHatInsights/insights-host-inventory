"""
Test cases for RHINENG-4809: SP filtering uses "*" as wildcard even if it is formatted

This test module verifies that URL-encoded wildcards like "%2A" (which is "*" encoded)
are treated as literal characters, not as wildcards.
"""

import pytest

from api.filtering.db_custom_filters import _was_wildcard_url_encoded
from api.filtering.db_custom_filters import build_single_filter


class TestWildcardUrlEncoding:
    """Test wildcard URL encoding behavior."""

    def test_was_wildcard_url_encoded_detection(self, flask_app):
        """Test the helper function that detects URL-encoded wildcards."""
        with flask_app.test_request_context("/?filter[system_profile][os_release]=abc%2A123"):
            # Should detect URL-encoded wildcard
            assert _was_wildcard_url_encoded("abc*123", "system_profile][os_release") is True

        with flask_app.test_request_context("/?filter[system_profile][os_release]=abc*123"):
            # Should not detect URL-encoded wildcard (it's a literal *)
            assert _was_wildcard_url_encoded("abc*123", "system_profile][os_release") is False

        with flask_app.test_request_context("/?filter[system_profile][os_release]=abc123"):
            # No wildcards at all
            assert _was_wildcard_url_encoded("abc123", "system_profile][os_release") is False

    def test_was_wildcard_url_encoded_backslash(self, flask_app):
        """Test detection of URL-encoded backslashes."""
        with flask_app.test_request_context("/?filter[system_profile][os_release]=test%5Cpath"):
            # Should detect URL-encoded backslash
            assert _was_wildcard_url_encoded("test\\path", "system_profile][os_release") is True

        with flask_app.test_request_context("/?filter[system_profile][os_release]=test\\path"):
            # Should not detect URL-encoded backslash (it's a literal \)
            assert _was_wildcard_url_encoded("test\\path", "system_profile][os_release") is False

    def test_build_filter_url_encoded_wildcard(self, flask_app):
        """Test that URL-encoded wildcards are treated as literal characters."""
        with flask_app.test_request_context("/?filter[system_profile][os_release]=abc%2A123"):
            # When wildcard was URL-encoded, should use exact match (=) not ILIKE
            filter_param = {"os_release": "abc*123"}
            result = build_single_filter(filter_param)

            # Should be an exact match operation, not ILIKE
            assert str(result).find("=") != -1  # Contains equals
            assert str(result).find("ILIKE") == -1  # Does not contain ILIKE

    def test_build_filter_literal_wildcard(self, flask_app):
        """Test that literal wildcards are treated as wildcards."""
        with flask_app.test_request_context("/?filter[system_profile][os_release]=abc*123"):
            # When wildcard was not URL-encoded, should use ILIKE with % replacement
            filter_param = {"os_release": "abc*123"}
            result = build_single_filter(filter_param)

            # Should be an ILIKE operation
            assert str(result).find("ILIKE") != -1  # Contains ILIKE

    def test_build_filter_mixed_wildcards(self, flask_app):
        """Test handling of mixed literal and URL-encoded wildcards."""
        with flask_app.test_request_context("/?filter[system_profile][os_release]=abc%2Adef*ghi"):
            # Mixed case: %2A should be literal, * should be wildcard
            # But since we detect any URL-encoded wildcards, the whole value is treated as literal
            filter_param = {"os_release": "abc*def*ghi"}
            result = build_single_filter(filter_param)

            # Should use exact match since URL encoding was detected
            assert str(result).find("=") != -1  # Contains equals
            assert str(result).find("ILIKE") == -1  # Does not contain ILIKE

    def test_build_filter_no_wildcards(self, flask_app):
        """Test that values without wildcards work normally."""
        with flask_app.test_request_context("/?filter[system_profile][os_release]=abc123"):
            filter_param = {"os_release": "abc123"}
            result = build_single_filter(filter_param)

            # Should be an exact match operation
            assert str(result).find("=") != -1  # Contains equals

    def test_build_filter_url_encoded_backslash(self, flask_app):
        """Test that URL-encoded backslashes are handled correctly."""
        with flask_app.test_request_context("/?filter[system_profile][os_release]=test1%2Atest2%5Ctest3"):
            # This is the exact case from the ticket description
            filter_param = {"os_release": "test1*test2\\test3"}
            result = build_single_filter(filter_param)

            # Should use exact match since URL encoding was detected
            assert str(result).find("=") != -1  # Contains equals
            assert str(result).find("ILIKE") == -1  # Does not contain ILIKE

    def test_build_filter_nested_field(self, flask_app):
        """Test URL encoding detection works for nested fields."""
        with flask_app.test_request_context("/?filter[system_profile][workloads][mssql][version]=15%2A3"):
            filter_param = {"workloads": {"mssql": {"version": "15*3"}}}
            result = build_single_filter(filter_param)

            # Should use exact match since URL encoding was detected
            assert str(result).find("=") != -1  # Contains equals

    def test_build_filter_insights_client_version(self, flask_app):
        """Test with insights_client_version field which supports wildcards."""
        with flask_app.test_request_context("/?filter[system_profile][insights_client_version]=3.0%2A"):
            filter_param = {"insights_client_version": "3.0*"}
            result = build_single_filter(filter_param)

            # Should use exact match since URL encoding was detected
            assert str(result).find("=") != -1  # Contains equals
            assert str(result).find("ILIKE") == -1  # Does not contain ILIKE

    def test_build_filter_insights_client_version_literal(self, flask_app):
        """Test with insights_client_version field with literal wildcard."""
        with flask_app.test_request_context("/?filter[system_profile][insights_client_version]=3.0*"):
            filter_param = {"insights_client_version": "3.0*"}
            result = build_single_filter(filter_param)

            # Should use ILIKE since no URL encoding was detected
            assert str(result).find("ILIKE") != -1  # Contains ILIKE

    def test_edge_cases(self, flask_app):
        """Test edge cases and error conditions."""
        # Test with no Flask request context - should not crash
        filter_param = {"os_release": "abc*123"}
        result = build_single_filter(filter_param)
        # Should default to wildcard behavior when no request context
        assert str(result).find("ILIKE") != -1  # Contains ILIKE

        # Test with empty value
        with flask_app.test_request_context("/?filter[system_profile][os_release]="):
            filter_param = {"os_release": ""}
            result = build_single_filter(filter_param)
            # Should handle empty values gracefully
            assert result is not None

    def test_case_insensitive_url_encoding(self, flask_app):
        """Test that both %2A and %2a are detected."""
        with flask_app.test_request_context("/?filter[system_profile][os_release]=abc%2a123"):
            # Should detect lowercase URL-encoded wildcard
            assert _was_wildcard_url_encoded("abc*123", "system_profile][os_release") is True

        with flask_app.test_request_context("/?filter[system_profile][os_release]=test%5c"):
            # Should detect lowercase URL-encoded backslash
            assert _was_wildcard_url_encoded("test\\", "system_profile][os_release") is True


@pytest.mark.integration
class TestWildcardUrlEncodingIntegration:
    """Integration tests with actual database queries."""

    def test_filter_hosts_with_url_encoded_wildcard(self, db_create_host, api_get):
        """Test filtering hosts with URL-encoded wildcards."""
        # Create a host with a literal "*" in os_release
        host_data = {"system_profile_facts": {"os_release": "abc*123"}}
        host_id = str(db_create_host(extra_data=host_data).id)

        # Create another host with a different os_release
        host_data2 = {"system_profile_facts": {"os_release": "abc.123"}}
        db_create_host(extra_data=host_data2)

        # Filter with URL-encoded wildcard - should match only the host with literal "*"
        url = "/api/inventory/v1/hosts?filter[system_profile][os_release]=abc%2A123"
        response_status, response_data = api_get(url)

        assert response_status == 200
        assert response_data["count"] == 1
        assert response_data["results"][0]["id"] == host_id

    def test_filter_hosts_with_literal_wildcard(self, db_create_host, api_get):
        """Test filtering hosts with literal wildcards."""
        # Create hosts with different os_release values
        host_data1 = {"system_profile_facts": {"os_release": "abc*123"}}
        host_id1 = str(db_create_host(extra_data=host_data1).id)

        host_data2 = {"system_profile_facts": {"os_release": "abc.123"}}
        host_id2 = str(db_create_host(extra_data=host_data2).id)

        host_data3 = {"system_profile_facts": {"os_release": "abcdef123"}}
        host_id3 = str(db_create_host(extra_data=host_data3).id)

        # Filter with literal wildcard - should match hosts with patterns
        url = "/api/inventory/v1/hosts?filter[system_profile][os_release]=abc*123"
        response_status, response_data = api_get(url)

        assert response_status == 200
        assert response_data["count"] == 3  # All three should match the wildcard pattern
        returned_ids = {host["id"] for host in response_data["results"]}
        assert returned_ids == {host_id1, host_id2, host_id3}

    def test_filter_hosts_backslash_issue(self, db_create_host, api_get):
        """Test the specific backslash issue mentioned in the ticket."""
        # Create a host with the exact value from the ticket
        host_data = {"system_profile_facts": {"os_release": "test1*test2\\test3"}}
        host_id = str(db_create_host(extra_data=host_data).id)

        # Filter with URL-encoded value - should match the host
        url = "/api/inventory/v1/hosts?filter[system_profile][os_release]=test1%2Atest2%5Ctest3"
        response_status, response_data = api_get(url)

        assert response_status == 200
        assert response_data["count"] == 1
        assert response_data["results"][0]["id"] == host_id
