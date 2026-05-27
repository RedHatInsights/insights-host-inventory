import pytest

from tests.helpers.api_utils import api_get
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.test_utils import minimal_host


class TestSystemProfileFiltering:
    @pytest.mark.parametrize(
        "field, value, query_value",
        [
            ("display_name", "test\\host", "test\\\\host"),
            ("display_name", "test%host", "test%host"),
            ("display_name", "test_host", "test_host"),
            ("hostname", "test\\host", "test\\\\host"),
            ("hostname", "test%host", "test%host"),
            ("hostname", "test_host", "test_host"),
        ],
    )
    def test_filter_by_sp_with_special_chars(
        self, mq_create_or_update_host, api_get, field, value, query_value
    ):
        host_data = minimal_host()
        host_data["system_profile"][field] = value
        created_host = mq_create_or_update_host(host_data)

        url = build_hosts_url(query=f"?filter[system_profile][{field}]={query_value}")
        response_status, response_data = api_get(url)

        assert response_status == 200
        assert response_data["count"] == 1
        assert response_data["results"][0]["id"] == created_host.id

    @pytest.mark.parametrize(
        "field, value, query_value",
        [
            ("display_name", "test\\host", "*\\\\*"),
            ("display_name", "test%host", "*%*"),
            ("display_name", "test_host", "*_*"),
            ("hostname", "test\\host", "*\\\\*"),
            ("hostname", "test%host", "*%*"),
            ("hostname", "test_host", "*_*"),
        ],
    )
    def test_filter_by_sp_with_special_chars_and_wildcard(
        self, mq_create_or_update_host, api_get, field, value, query_value
    ):
        host_data = minimal_host()
        host_data["system_profile"][field] = value
        created_host = mq_create_or_update_host(host_data)

        url = build_hosts_url(query=f"?filter[system_profile][{field}]={query_value}")
        response_status, response_data = api_get(url)

        assert response_status == 200
        assert response_data["count"] == 1
        assert response_data["results"][0]["id"] == created_host.id

    def test_filter_by_sp_with_all_special_chars_and_wildcard(
        self, mq_create_or_update_host, api_get
    ):
        host_data = minimal_host()
        host_data["system_profile"]["display_name"] = "test\\%_*host"
        created_host = mq_create_or_update_host(host_data)

        url = build_hosts_url(query=r"?filter[system_profile][display_name]=*\\%_*")
        response_status, response_data = api_get(url)

        assert response_status == 200
        assert response_data["count"] == 1
        assert response_data["results"][0]["id"] == created_host.id

    @pytest.mark.parametrize(
        "field",
        [
            "display_name",
            "hostname",
        ],
    )
    def test_wildcard_still_works(self, mq_create_or_update_host, api_get, field):
        host_data = minimal_host()
        host_data["system_profile"][field] = "my-testing-host"
        created_host = mq_create_or_update_host(host_data)

        url = build_hosts_url(query=f"?filter[system_profile][{field}]=*testing*")
        response_status, response_data = api_get(url)

        assert response_status == 200
        assert response_data["count"] == 1
        assert response_data["results"][0]["id"] == created_host.id
