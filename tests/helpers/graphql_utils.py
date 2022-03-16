from api.host_query_xjoin import QUERY as HOST_QUERY
from tests.helpers.api_utils import get_valid_auth_header
from tests.helpers.test_utils import USER_IDENTITY

EMPTY_HOSTS_RESPONSE = {"hosts": {"meta": {"total": 0}, "data": []}}
TAGS_EMPTY_RESPONSE = {"hostTags": {"meta": {"count": 0, "total": 0}, "data": []}}
SYSTEM_PROFILE_SAP_SYSTEM_EMPTY_RESPONSE = {
    "hostSystemProfile": {"sap_system": {"meta": {"total": 0, "count": 0}, "data": []}}
}
SYSTEM_PROFILE_SAP_SIDS_EMPTY_RESPONSE = {
    "hostSystemProfile": {"sap_sids": {"meta": {"total": 0, "count": 0}, "data": []}}
}

XJOIN_HOSTS_RESPONSE_FOR_FILTERING = {
    "hosts": {
        "meta": {"total": 3},
        "data": [
            {
                "id": "6e7b6317-0a2d-4552-a2f2-b7da0aece49d",
                "canonical_facts": {
                    "fqdn": "fqdn.test01.rhel7.jharting.local",
                    "satellite_id": "ce87bfac-a6cb-43a0-80ce-95d9669db71f",
                    "insights_id": "a58c53e0-8000-4384-b902-c70b69faacc5",
                },
            },
            {
                "id": "22cd8e39-13bb-4d02-8316-84b850dc5136",
                "canonical_facts": {
                    "fqdn": "fqdn.test02.rhel7.jharting.local",
                    "satellite_id": "ce87bfac-a6cb-43a0-80ce-95d9669db71f",
                    "insights_id": "17c52679-f0b9-4e9b-9bac-a3c7fae5070c",
                },
            },
            {"id": "22cd8e39-13bb-4d02-8316-84b850dc5136", "canonical_facts": {"fqdn": "test03.rhel7.fqdn"}},
        ],
    }
}

XJOIN_HOSTS_RESPONSE = {
    "hosts": {
        "meta": {"total": 2},
        "data": [
            {
                "id": "6e7b6317-0a2d-4552-a2f2-b7da0aece49d",
                "account": "test",
                "display_name": "test01.rhel7.jharting.local",
                "ansible_host": "test01.rhel7.jharting.local",
                "created_on": "2019-02-10T08:07:03.354307Z",
                "modified_on": "2019-02-10T08:07:03.354312Z",
                "canonical_facts": {
                    "fqdn": "fqdn.test01.rhel7.jharting.local",
                    "satellite_id": "ce87bfac-a6cb-43a0-80ce-95d9669db71f",
                    "insights_id": "a58c53e0-8000-4384-b902-c70b69faacc5",
                },
                "facts": None,
                "stale_timestamp": "2020-02-10T08:07:03.354307Z",
                "reporter": "puptoo",
                "per_reporter_staleness": {
                    "puptoo": {
                        "check_in_succeeded": True,
                        "last_check_in": "2020-02-10T08:07:03.354307+00:00",
                        "stale_timestamp": "2020-02-10T08:07:03.354307+00:00",
                    }
                },
                "system_profile_facts": {"test_data": "1.2.3", "random": ["data"]},
            },
            {
                "id": "22cd8e39-13bb-4d02-8316-84b850dc5136",
                "account": "test",
                "display_name": "test02.rhel7.jharting.local",
                "ansible_host": "test02.rhel7.jharting.local",
                "created_on": "2019-01-10T08:07:03.354307Z",
                "modified_on": "2019-01-10T08:07:03.354312Z",
                "canonical_facts": {
                    "fqdn": "fqdn.test02.rhel7.jharting.local",
                    "satellite_id": "ce87bfac-a6cb-43a0-80ce-95d9669db71f",
                    "insights_id": "17c52679-f0b9-4e9b-9bac-a3c7fae5070c",
                },
                "facts": {
                    "os": {"os.release": "Red Hat Enterprise Linux Server"},
                    "bios": {
                        "bios.vendor": "SeaBIOS",
                        "bios.release_date": "2014-04-01",
                        "bios.version": "1.11.0-2.el7",
                    },
                },
                "stale_timestamp": "2020-01-10T08:07:03.354307Z",
                "reporter": "puptoo",
                "per_reporter_staleness": {
                    "puptoo": {
                        "check_in_succeeded": True,
                        "last_check_in": "2020-02-10T08:07:03.354307+00:00",
                        "stale_timestamp": "2020-02-10T08:07:03.354307+00:00",
                    }
                },
                "system_profile_facts": {"test_data": "1.2.3", "random": ["data"]},
            },
        ],
    }
}

XJOIN_TAGS_RESPONSE = {
    "hostTags": {
        "meta": {"count": 3, "total": 3},
        "data": [
            {"tag": {"namespace": "Sat", "key": "env", "value": "prod"}, "count": 3},
            {"tag": {"namespace": "insights-client", "key": "database", "value": None}, "count": 2},
            {"tag": {"namespace": "insights-client", "key": "os", "value": "fedora"}, "count": 2},
        ],
    }
}

XJOIN_SYSTEM_PROFILE_SAP_SYSTEM = {
    "hostSystemProfile": {
        "sap_system": {
            "meta": {"total": 2, "count": 2},
            "data": [{"value": False, "count": 1}, {"value": True, "count": 2}],
        }
    }
}

XJOIN_SYSTEM_PROFILE_SAP_SIDS = {
    "hostSystemProfile": {
        "sap_sids": {
            "meta": {"total": 5, "count": 5},
            "data": [
                {"value": "AEB", "count": 2},
                {"value": "C2C", "count": 1},
                {"value": "KLL", "count": 1},
                {"value": "M1P", "count": 1},
                {"value": "XQC", "count": 1},
            ],
        }
    }
}

XJOIN_SPARSE_SYSTEM_PROFILE_EMPTY_RESPONSE = {"hosts": {"meta": {"count": 2, "total": 2}, "data": []}}
CASEFOLDED_FIELDS = ("fqdn", "insights_id", "provider_type", "provider_id")


def xjoin_host_response(timestamp):
    return {
        "hosts": {
            **XJOIN_HOSTS_RESPONSE["hosts"],
            "meta": {"total": 1},
            "data": [
                {
                    **XJOIN_HOSTS_RESPONSE["hosts"]["data"][0],
                    "created_on": timestamp,
                    "modified_on": timestamp,
                    "stale_timestamp": timestamp,
                }
            ],
        }
    }


def xjoin_response_with_per_reporter_staleness(newprs):
    return {
        "hosts": {
            **XJOIN_HOSTS_RESPONSE["hosts"],
            "meta": {"total": 1},
            "data": [{**XJOIN_HOSTS_RESPONSE["hosts"]["data"][0], "per_reporter_staleness": newprs}],
        }
    }


def assert_graph_query_single_call_with_staleness(mocker, graphql_query, staleness_conditions):
    conditions = tuple({"stale_timestamp": staleness_condition} for staleness_condition in staleness_conditions)
    graphql_query.assert_called_once_with(
        HOST_QUERY,
        {
            "order_by": mocker.ANY,
            "order_how": mocker.ANY,
            "limit": mocker.ANY,
            "offset": mocker.ANY,
            "filter": ({"OR": conditions},),
            "fields": mocker.ANY,
        },
        mocker.ANY,
    )


def assert_called_with_headers(mocker, post, request_id):
    identity = get_valid_auth_header(USER_IDENTITY).get("x-rh-identity").decode()

    post.assert_called_once_with(
        mocker.ANY, json=mocker.ANY, headers={"x-rh-identity": identity, "x-rh-insights-request-id": request_id}
    )
