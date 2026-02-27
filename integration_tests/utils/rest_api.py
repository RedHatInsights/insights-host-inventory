from typing import Any

from requests import Response

from integration_tests.utils.app import TestApp


def _non_null_params(**kwargs: Any) -> dict[str, Any]:
    return {k: v for k, v in kwargs.items() if v is not None}


class InventoryAPI:
    def __init__(self, test_app: TestApp):
        self._test_app = test_app
        self.session = test_app.api_session
        self.base_url = test_app.config.hbi_api_url

    def get_host_list_response(
        self,
        *,
        display_name: str | None = None,
        fqdn: str | None = None,
        hostname_or_id: str | None = None,
        insights_id: str | None = None,
        subscription_manager_id: str | None = None,
        provider_id: str | None = None,
        provider_type: str | None = None,
        updated_start: str | None = None,
        updated_end: str | None = None,
        last_check_in_start: str | None = None,
        last_check_in_end: str | None = None,
        group_name: list[str] | None = None,
        group_id: list[str] | None = None,
        branch_id: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        staleness: list[str] | None = None,
        tags: list[str] | None = None,
        registered_with: list[str] | None = None,
        system_type: list[str] | None = None,
        filter: dict[str, Any] | None = None,
        fields: dict[str, Any] | None = None,
    ) -> Response:
        """Send a GET request to /hosts and return the raw response.

        All parameters are optional and correspond to the query parameters
        defined in the HBI API specification.  Parameters set to None are
        omitted from the request.
        """
        params = _non_null_params(
            display_name=display_name,
            fqdn=fqdn,
            hostname_or_id=hostname_or_id,
            insights_id=insights_id,
            subscription_manager_id=subscription_manager_id,
            provider_id=provider_id,
            provider_type=provider_type,
            updated_start=updated_start,
            updated_end=updated_end,
            last_check_in_start=last_check_in_start,
            last_check_in_end=last_check_in_end,
            group_name=group_name,
            group_id=group_id,
            branch_id=branch_id,
            per_page=per_page,
            page=page,
            order_by=order_by,
            order_how=order_how,
            staleness=staleness,
            tags=tags,
            registered_with=registered_with,
            system_type=system_type,
            filter=filter,
            fields=fields,
        )
        response = self.session.get(f"{self.base_url}/hosts", params=params)
        return response

    def get_host_list(
        self,
        *,
        display_name: str | None = None,
        fqdn: str | None = None,
        hostname_or_id: str | None = None,
        insights_id: str | None = None,
        subscription_manager_id: str | None = None,
        provider_id: str | None = None,
        provider_type: str | None = None,
        updated_start: str | None = None,
        updated_end: str | None = None,
        last_check_in_start: str | None = None,
        last_check_in_end: str | None = None,
        group_name: list[str] | None = None,
        group_id: list[str] | None = None,
        branch_id: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        staleness: list[str] | None = None,
        tags: list[str] | None = None,
        registered_with: list[str] | None = None,
        system_type: list[str] | None = None,
        filter: dict[str, Any] | None = None,
        fields: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Send a GET request to /hosts and return the parsed JSON body.

        Raises requests.HTTPError if the response status code indicates
        a failure.  All parameters are forwarded to get_host_list_response.
        """
        response = self.get_host_list_response(
            display_name=display_name,
            fqdn=fqdn,
            hostname_or_id=hostname_or_id,
            insights_id=insights_id,
            subscription_manager_id=subscription_manager_id,
            provider_id=provider_id,
            provider_type=provider_type,
            updated_start=updated_start,
            updated_end=updated_end,
            last_check_in_start=last_check_in_start,
            last_check_in_end=last_check_in_end,
            group_name=group_name,
            group_id=group_id,
            branch_id=branch_id,
            per_page=per_page,
            page=page,
            order_by=order_by,
            order_how=order_how,
            staleness=staleness,
            tags=tags,
            registered_with=registered_with,
            system_type=system_type,
            filter=filter,
            fields=fields,
        )
        response.raise_for_status()

        response_json = response.json()
        return response_json["results"]

    def get_hosts_by_id_response(
        self,
        host_id_list: list[str],
        *,
        branch_id: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        fields: dict[str, Any] | None = None,
    ) -> Response:
        """Send a GET request to /hosts/{host_id_list} and return the raw response.

        Args:
            host_id_list: One or more host IDs to look up.
        """
        host_ids = ",".join(host_id_list)
        params = _non_null_params(
            branch_id=branch_id,
            per_page=per_page,
            page=page,
            order_by=order_by,
            order_how=order_how,
            fields=fields,
        )
        response = self.session.get(f"{self.base_url}/hosts/{host_ids}", params=params)
        return response

    def get_hosts_by_id(
        self,
        host_id_list: list[str],
        *,
        branch_id: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        fields: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Send a GET request to /hosts/{host_id_list} and return the parsed JSON body.

        Raises requests.HTTPError if the response status code indicates
        a failure.  All parameters are forwarded to get_hosts_by_id_response.

        Args:
            host_id_list: One or more host IDs to look up.
        """
        response = self.get_hosts_by_id_response(
            host_id_list,
            branch_id=branch_id,
            per_page=per_page,
            page=page,
            order_by=order_by,
            order_how=order_how,
            fields=fields,
        )
        response.raise_for_status()

        response_json = response.json()
        return response_json["results"]
