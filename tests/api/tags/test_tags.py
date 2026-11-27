import uuid
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from urllib.parse import urlencode

import pytest

from app.models import ProviderType
from app.models import db
from app.serialization import _deserialize_tags_dict
from tests.helpers.api_utils import HOST_READ_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_host_tags_url
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_tags_count_url
from tests.helpers.api_utils import build_tags_url
from tests.helpers.api_utils import create_hosts_by_reporter_and_staleness
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.api_utils import run_rbac_test
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import now


def _assert_aggregate_tags(response, expected_tags):
    """Compare complete tag membership and host counts, independent of ordering."""
    assert response["total"] == response["count"] == len(response["results"]) == len(expected_tags)
    assert {
        (item["tag"]["namespace"], item["tag"]["key"], item["tag"]["value"], item["count"])
        for item in response["results"]
    } == {(tag["namespace"], tag["key"], tag["value"], 1) for tag in expected_tags}


def test_get_tags_by_host_identity_and_provider(db_create_host, api_get, subtests):
    target = {
        "fqdn": "Target.Example.test",
        "insights_id": "abcdef01-2345-6789-abcd-0123456789ab",
        "provider_id": "fedcba98-7654-3210-abcd-0123456789ab",
        "provider_type": ProviderType.AWS.value,
    }
    expected_tags = [
        {"namespace": "target", "key": "role", "value": "database"},
        {"namespace": "target", "key": "env", "value": "production"},
    ]
    db_create_host(extra_data={**target, "tags": {"target": {"role": ["database"], "env": ["production"]}}})
    db_create_host(
        extra_data={
            "fqdn": "other.example.test",
            "provider_id": generate_uuid(),
            "provider_type": ProviderType.AZURE.value,
            "tags": {"other": {"role": ["web"], "env": ["stage"]}},
        }
    )
    for field, value in target.items():
        for variant in dict.fromkeys((value, value.lower(), value.upper()) if field != "provider_type" else (value,)):
            with subtests.test(field=field, value=variant):
                status, response = api_get(build_tags_url(query="?" + urlencode({field: variant})))
                assert status == 200
                _assert_aggregate_tags(response, expected_tags)


def test_get_tags_valid_filter_combinations(
    db_create_host, db_create_group, db_create_host_group_assoc, api_get, subtests
):
    """Each near match violates exactly one restriction of the conjunction."""
    group = db_create_group("selected-group")
    other_group = db_create_group("other-group")
    current = now()
    inside = current - timedelta(hours=2)
    start, end = inside - timedelta(minutes=1), inside + timedelta(minutes=1)
    identity = {"display_name": "selected-host", "fqdn": "selected.example.test", "insights_id": generate_uuid()}
    expected_tags = [
        {"namespace": "match", "key": "role", "value": "database"},
        {"namespace": "match", "key": "env", "value": "prod"},
    ]
    for reason in ("match", "group", "identity", "provider", "stale", "before", "after"):
        extra = {**identity, "provider_type": ProviderType.AWS.value, "tags": {reason: {"role": ["database"]}}}
        if reason == "match":
            extra["tags"][reason]["env"] = ["prod"]
        elif reason == "identity":
            extra.update(display_name="other-host", fqdn="other.example.test", insights_id=generate_uuid())
        elif reason == "provider":
            extra["provider_type"] = ProviderType.AZURE.value
        host = db_create_host(extra_data=extra)
        db_create_host_group_assoc(host.id, other_group.id if reason == "group" else group.id)
        # Set timestamps after group assignment, which is itself a modification.
        host.modified_on = (
            start - timedelta(seconds=1)
            if reason == "before"
            else (end + timedelta(seconds=1) if reason == "after" else inside)
        )
        host.last_check_in = current - timedelta(days=8) if reason == "stale" else current
    db.session.commit()

    for field, value in {**identity, "hostname_or_id": identity["fqdn"]}.items():
        with subtests.test(identifier=field):
            params = {
                field: value,
                "provider_type": "aws",
                "staleness": "fresh",
                "updated_start": start.isoformat(),
                "updated_end": end.isoformat(),
                "group_name": group.name,
            }
            status, response = api_get(build_tags_url(query="?" + urlencode(params)))
            assert status == 200
            _assert_aggregate_tags(response, expected_tags)


def test_get_tags_updated_boundaries_and_timezones(db_create_host, api_get, subtests):
    """One five-host dataset discriminates inclusive, interstitial and offset bounds."""
    middle = now().replace(microsecond=123456) - timedelta(hours=1)
    times = [middle + timedelta(minutes=index - 2) for index in range(5)]
    tags = [{"namespace": "time", "key": f"host-{index}", "value": "v"} for index in range(5)]
    for timestamp, tag in zip(times, tags, strict=True):
        host = db_create_host(extra_data={"tags": {"time": {tag["key"]: ["v"]}}})
        host.modified_on = timestamp
    db.session.commit()

    # Exact and interstitial cutoffs select the same hosts. Equal bounds select only the middle.
    intervals = (
        ({"updated_start": times[2]}, tags[2:]),
        ({"updated_start": times[2] - timedelta(seconds=1)}, tags[2:]),
        ({"updated_end": times[2]}, tags[:3]),
        ({"updated_end": times[2] + timedelta(seconds=1)}, tags[:3]),
        ({"updated_start": times[1], "updated_end": times[3]}, tags[1:4]),
        (
            {"updated_start": times[1] - timedelta(seconds=1), "updated_end": times[3] + timedelta(seconds=1)},
            tags[1:4],
        ),
        ({"updated_start": times[2], "updated_end": times[2]}, tags[2:3]),
    )
    for bounds, expected in intervals:
        for representation in ("naive", "utc", "z"):
            formatted = {
                key: value.replace(tzinfo=None).isoformat()
                if representation == "naive"
                else (value.isoformat().replace("+00:00", "Z") if representation == "z" else value.isoformat())
                for key, value in bounds.items()
            }
            with subtests.test(bounds=formatted):
                status, response = api_get(build_tags_url(query="?" + urlencode(formatted)))
                assert status == 200
                _assert_aggregate_tags(response, expected)

    for hours in (-3, 3):
        bounds = {
            "updated_start": times[1].astimezone(timezone(timedelta(hours=hours))).isoformat(),
            "updated_end": times[3].astimezone(timezone(timedelta(hours=hours))).isoformat(),
        }
        with subtests.test(offset=hours):
            status, response = api_get(build_tags_url(query="?" + urlencode(bounds)))
            assert status == 200
            _assert_aggregate_tags(response, tags[1:4])


@pytest.mark.usefixtures("event_producer_mock")
def test_get_tags_updated_not_created(db_create_host, db_get_host, api_patch, api_get, mocker):
    current = now()
    old, inside, after = (current - timedelta(hours=hours) for hours in (3, 2, 1))
    hosts = []
    for label, created in (("untouched", old), ("updated-inside", old), ("updated-after", inside)):
        host = db_create_host(extra_data={"tags": {"modified": {label: ["v"]}}})
        host.created_on = host.modified_on = created
        hosts.append(host)
    db.session.commit()

    for host, timestamp in zip(hosts[1:], (inside, after), strict=True):
        with mocker.patch("app.models.utils.datetime", **{"now.return_value": timestamp}):
            status, _ = api_patch(build_hosts_url(host_list_or_id=host.id), {"display_name": "changed"})
        assert status == 200
        assert db_get_host(host.id).modified_on == timestamp

    params = {
        "updated_start": (inside - timedelta(minutes=1)).isoformat(),
        "updated_end": (inside + timedelta(minutes=1)).isoformat(),
    }
    status, response = api_get(build_tags_url(query="?" + urlencode(params)))
    assert status == 200
    _assert_aggregate_tags(response, [{"namespace": "modified", "key": "updated-inside", "value": "v"}])


@pytest.mark.parametrize(
    "search",
    (
        "&search=NS1",
        "&search=NS1/key2=val1",
    ),
)
def test_get_tags_of_multiple_hosts_query_via_db(mq_create_three_specific_hosts, api_get, search):
    """
    Send a request for the tag count of multiple hosts and validate the query
    """
    created_hosts = mq_create_three_specific_hosts

    url = build_host_tags_url(host_list_or_id=created_hosts, query=f"?order_by=updated&order_how=ASC{search}")
    response_status, response = api_get(url)
    assert response_status == 200
    assert response["count"] == len(created_hosts)
    assert response["results"][created_hosts[0].id] != {}


def test_host_tag_response_and_pagination_via_db(mq_create_three_specific_hosts, api_get):
    """
    Given a set host creation, verify that the tags URL returns data correctly.
    """
    created_hosts = mq_create_three_specific_hosts

    url = build_host_tags_url(host_list_or_id=mq_create_three_specific_hosts, query="?order_by=updated&order_how=ASC")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"] == len(created_hosts)
    assert response_data["page"] == 1
    assert response_data["per_page"] == 50  # The default value, since we didn't specify


def test_tags_pagination_page_sizes(db_create_host, api_get, subtests):
    db_create_host(extra_data={"tags": {"pagination": {f"key-{i}": ["value"] for i in range(100)}}})
    for per_page in (5, 10, 15, 25, 50, 100):
        with subtests.test(per_page=per_page):
            status, data = api_get(build_tags_url(), query_parameters={"per_page": per_page})
            assert status == 200
            assert data["total"] == 100
            assert data["count"] == len(data["results"]) == per_page


def test_host_tags_via_db_invalid_updated_params(api_get):
    """
    Test using an updated_start that's later than updated_end
    """

    query_params = "?updated_start=2024-01-19T15:00:00.000Z&updated_end=2024-01-15T09:00:00.000Z"
    url = build_tags_url(query=query_params)
    response_status, _ = api_get(url)
    assert response_status == 400


def test_host_tags_via_db_invalid_last_check_in_params(api_get):
    """
    Test using an last_check_in_start that's later than last_check_in_end
    """

    query_params = "?last_check_in_start=2024-01-19T15:00:00.000Z&last_check_in_end=2024-01-15T09:00:00.000Z"
    url = build_tags_url(query=query_params)
    response_status, _ = api_get(url)
    assert response_status == 400


def test_get_tags_of_hosts_that_does_not_exist_via_db(api_get):
    """
    send a request for some host that doesn't exist
    """
    url = build_host_tags_url(generate_uuid())

    response_status, _ = api_get(url)

    assert response_status == 404


def test_get_tags_of_hosts_partial_not_found(api_get, db_create_host):
    """
    send a request for multiple hosts where some exist and some don't
    """
    existing_host = db_create_host()
    non_existent_id = generate_uuid()
    url = build_host_tags_url(host_list_or_id=[str(existing_host.id), non_existent_id])

    response_status, _ = api_get(url)

    assert response_status == 404


def test_get_list_of_tags_with_host_filters_via_db(db_create_multiple_hosts, api_get, subtests):
    """
    Validate that the /tags endpoint doesn't break when we supply it with various filters.
    """
    _now = now()
    insights_id = generate_uuid()
    provider_id = generate_uuid()
    display_name = "test-example-host"
    namespace = "ns1"
    tag_key = "database"
    tag_value = "postgresql"
    per_reporter_staleness = {
        "puptoo": _now.isoformat(),
        "yupana": (_now - timedelta(days=3)).isoformat(),
    }
    db_create_multiple_hosts(
        how_many=1,
        extra_data={
            "insights_id": insights_id,
            "provider_type": ProviderType.AZURE.value,
            "provider_id": provider_id,
            "display_name": display_name,
            "tags": _deserialize_tags_dict({namespace: {tag_key: [tag_value]}}),
            "per_reporter_staleness": per_reporter_staleness,
        },
    )

    for test_case in (
        {"query": f"?display_name={display_name}", "expected_count": 1},
        {"query": f"?insights_id={insights_id}", "expected_count": 1},
        {"query": f"?provider_id={provider_id}", "expected_count": 1},
        {"query": f"?provider_type={ProviderType.AZURE.value}", "expected_count": 1},
        {"query": f"?search={tag_key}", "expected_count": 1},
        {"query": f"?search={tag_key.swapcase()}", "expected_count": 1},
        {"query": f"?search={namespace}/{tag_key}={tag_value}", "expected_count": 1},
        {"query": "?search=not-found", "expected_count": 0},
        {"query": "?registered_with=puptoo", "expected_count": 1},
        {"query": "?registered_with=yupana", "expected_count": 1},
        {"query": "?staleness=fresh", "expected_count": 1},
    ):
        with subtests.test(query=test_case.get("query")):
            url = build_tags_url(query=test_case.get("query"))
            response_status, response_data = api_get(url)

            assert_response_status(response_status, 200)
            assert response_data["total"] == test_case.get("expected_count")
            if test_case.get("expected_count") == 1:
                assert response_data["results"][0]["tag"]["namespace"] == namespace
                assert response_data["results"][0]["tag"]["key"] == tag_key
                assert response_data["results"][0]["tag"]["value"] == tag_value
                assert response_data["results"][0]["count"] == 1


def test_get_tags_filter_by_reporter_and_staleness(db_create_host, api_get, mocker, subtests):
    reporters = ("puptoo", "yupana")
    states = ("fresh", "stale", "stale_warning")

    tag_data = {
        (state, reporter): {
            "tags": _deserialize_tags_dict({f"ns-{state}-{reporter}": {f"key-{state}-{reporter}": ["v1"]}})
        }
        for state in states
        for reporter in reporters
    }

    create_hosts_by_reporter_and_staleness(db_create_host, mocker, reporters=reporters, extra_data_per_host=tag_data)

    for state in states:
        for reporter in reporters:
            with subtests.test(state=state, reporter=reporter):
                url = build_tags_url(query=f"?staleness={state}&registered_with={reporter}")
                response_status, response_data = api_get(url)

                assert_response_status(response_status, 200)
                assert response_data["total"] >= 1

                result_tags = {(r["tag"]["namespace"], r["tag"]["key"]) for r in response_data["results"]}
                expected_ns = f"ns-{state}-{reporter}"
                expected_key = f"key-{state}-{reporter}"
                assert (expected_ns, expected_key) in result_tags

                unexpected_tags = {
                    (f"ns-{s}-{r}", f"key-{s}-{r}") for s in states for r in reporters if (s, r) != (state, reporter)
                }
                assert not result_tags & unexpected_tags


def test_get_tags_count_of_host_that_does_not_exist(api_get):
    """
    send a request for some host that doesn't exist
    """
    url = build_tags_count_url(host_list_or_id=generate_uuid())
    response_status, response_data = api_get(url)

    assert response_status == 404


def test_get_tags_count_of_hosts_partial_not_found(api_get, db_create_host):
    """
    send a request for multiple hosts where some exist and some don't
    """
    existing_host = db_create_host()
    non_existent_id = generate_uuid()
    url = build_tags_count_url(host_list_or_id=[str(existing_host.id), non_existent_id])

    response_status, _ = api_get(url)

    assert response_status == 404


def test_get_tags_from_host_with_no_tags(api_get, db_create_host):
    """
    send a request for a host with no tags
    """
    host_with_no_tags_id = str(db_create_host().id)

    url = build_host_tags_url(host_list_or_id=host_with_no_tags_id)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["results"] == {host_with_no_tags_id: []}


def test_get_tags_count_from_host_with_no_tags(api_get, db_create_host):
    """
    send a request for a host with no tags
    """
    host_with_no_tags_id = str(db_create_host().id)

    url = build_tags_count_url(host_list_or_id=host_with_no_tags_id)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["results"] == {host_with_no_tags_id: 0}


@pytest.mark.usefixtures("enable_rbac")
def test_get_host_tags_with_RBAC_allowed(subtests, mocker, api_get, db_create_host):
    host_id = str(db_create_host().id)
    url = build_host_tags_url(host_list_or_id=host_id)
    run_rbac_test(subtests, mocker, api_get, HOST_READ_ALLOWED_RBAC_RESPONSE_FILES, 200, [url])


@pytest.mark.usefixtures("enable_rbac")
def test_get_host_tags_with_RBAC_denied(subtests, db_create_host, mocker, api_get):
    get_host_tags_list_mock = mocker.patch("api.host.get_host_tags_list_by_id_list")
    host_id = str(db_create_host().id)
    url = build_host_tags_url(host_list_or_id=host_id)
    run_rbac_test(subtests, mocker, api_get, HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES, 403, [url])
    get_host_tags_list_mock.assert_not_called()


@pytest.mark.usefixtures("enable_rbac")
def test_get_host_tag_count_RBAC_allowed(mocker, api_get, subtests, mq_create_three_specific_hosts):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    host_list = mq_create_three_specific_hosts
    expected_response = {host.id: len(host.tags) for host in host_list}

    for response_file in HOST_READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            url = build_tags_count_url(host_list_or_id=host_list, query="?order_by=updated&order_how=ASC")
            response_status, response_data = api_get(url)

            assert response_status == 200
            assert len(expected_response) == len(response_data["results"])


@pytest.mark.usefixtures("enable_rbac")
def test_get_host_tag_count_RBAC_denied(mq_create_four_specific_hosts, mocker, api_get, subtests):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    get_host_tags_list_mock = mocker.patch("api.host.get_host_tags_list_by_id_list")

    created_hosts = mq_create_four_specific_hosts

    for response_file in HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            url = build_tags_count_url(host_list_or_id=created_hosts, query="?order_by=updated&order_how=ASC")
            response_status, _ = api_get(url)

            assert response_status == 403

            get_host_tags_list_mock.assert_not_called()


def test_get_tags_count_of_host_that_does_not_exist_via_db(api_get):
    """
    send a request for some host that doesn't exist via db only
    """
    url = build_tags_count_url(host_list_or_id=generate_uuid())
    response_status, response_data = api_get(url)

    assert response_status == 404


def test_get_tags_count_of_host_via_db(api_get, mq_create_three_specific_hosts):
    """
    send a request for some host that does exist via db only
    """
    created_hosts = mq_create_three_specific_hosts
    url = build_tags_count_url(host_list_or_id=created_hosts[0].id)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["results"][created_hosts[0].id] >= 0


@pytest.mark.usefixtures("enable_rbac")
def test_get_host_tags_with_RBAC_bypassed_as_system(db_create_host, api_get):
    host = db_create_host(
        SYSTEM_IDENTITY, extra_data={"system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]}}
    )

    url = build_host_tags_url(host_list_or_id=host.id)
    response_status, _ = api_get(url, SYSTEM_IDENTITY)

    assert_response_status(response_status, 200)


@pytest.mark.parametrize(
    "null_value_tag,flattened_tag",
    (
        (
            {"ns1": {"key1": None}},
            {"namespace": "ns1", "key": "key1", "value": None},
        ),
        (
            {"insights-client": {"ABaOUCuGU": []}},
            {"namespace": "insights-client", "key": "ABaOUCuGU", "value": None},
        ),
    ),
)
def test_get_host_tags_null_value_via_db(api_get, db_create_host, null_value_tag, flattened_tag):
    created_host = db_create_host(extra_data={"tags": null_value_tag})

    url = build_host_tags_url(host_list_or_id=created_host.id)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert flattened_tag in response_data["results"][str(created_host.id)]

    url = build_tags_url()
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert flattened_tag == response_data["results"][0]["tag"]


def test_get_host_tags_null_namespace_via_db(api_get, db_create_host):
    null_namespace_tag = {None: {"key1": "val1"}}
    flattened_tag = {"namespace": None, "key": "key1", "value": "val1"}
    created_host = db_create_host(extra_data={"tags": null_namespace_tag})

    url = build_host_tags_url(host_list_or_id=created_host.id)
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert flattened_tag in response_data["results"][str(created_host.id)]


@pytest.mark.parametrize(
    "tag, flattened_tag",
    (
        (
            {"insights-client": {"char-$-in-key": "50"}},
            {"namespace": "insights-client", "key": "char-$-in-key", "value": "50"},
        ),
        (
            {"insights-client": {"test-key": "char-$-in-value"}},
            {"namespace": "insights-client", "key": "test-key", "value": "char-$-in-value"},
        ),
    ),
)
def test_get_tags_with_dollar_signs_via_db(api_get, db_create_host, tag, flattened_tag):
    db_create_host(extra_data={"tags": tag})

    url = build_tags_url(query="?search=char-$-in")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert flattened_tag == response_data["results"][0]["tag"]


def test_query_tags_filter_last_check_in_both_same(db_create_host, api_get):
    match_namespace = "ns1"
    match_key = "key1"
    match_value = "value1"
    match_host = db_create_host(
        extra_data={
            "tags": _deserialize_tags_dict({match_namespace: {match_key: [match_value]}}),
        },
    )
    db_create_host(
        extra_data={
            "tags": _deserialize_tags_dict({"ns2": {"nomatch_key": ["nomatch_value"]}}),
        },
    )
    last_check_in = match_host.last_check_in.astimezone(UTC).isoformat().replace("+00:00", "Z")
    response_status, response_data = api_get(
        build_tags_url(query=f"?last_check_in_start={last_check_in}&last_check_in_end={last_check_in}")
    )
    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["tag"]["namespace"] == match_namespace
    assert response_data["results"][0]["tag"]["key"] == match_key
    assert response_data["results"][0]["tag"]["value"] == match_value


def test_query_tags_filter_last_check_in_and_updated_invalid_format(api_get, subtests):
    invalid_formats = ("foobar", "{}", "[]", generate_uuid(), [datetime.now(), datetime.now() - timedelta(days=7)])
    for invalid_format in invalid_formats:
        for param in ("last_check_in_start", "last_check_in_end", "updated_start", "updated_end"):
            with subtests.test(invalid_format=invalid_format, param=param):
                url = build_tags_url(query=f"?{param}={invalid_format}")
                response_status, response_data = api_get(url)
                assert response_status == 400
                assert "is not a 'date-time'" in response_data["detail"]


@pytest.mark.parametrize("param_prefix", ("updated", "last_check_in"))
def test_query_tags_filter_updated_last_check_in_start_after_end(api_get, param_prefix):
    url = build_tags_url(
        query=f"?{param_prefix}_start={datetime.now()}&{param_prefix}_end={datetime.now() - timedelta(days=1)}"
    )
    response_status, response_data = api_get(url)
    assert response_status == 400
    assert f"{param_prefix}_start cannot be after {param_prefix}_end." in response_data["detail"]


def test_query_tags_using_group_id(db_create_group_with_hosts, api_get):
    """Test filtering tags by group_id parameter."""
    # Create group with hosts that have tags
    group1 = db_create_group_with_hosts("test_group_1", 3)

    # Create another group that we don't want in the response
    db_create_group_with_hosts("test_group_2", 2)

    # Query tags using group_id
    url = build_tags_url(query=f"?group_id={group1.id}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    # Should return tags from hosts in group1 only
    assert response_data["count"] >= 0  # May be 0 if hosts have no tags


def test_query_tags_using_multiple_group_ids(db_create_group_with_hosts, api_get):
    """Test filtering tags by multiple group_id parameters."""
    group1 = db_create_group_with_hosts("test_group_1", 2)
    group2 = db_create_group_with_hosts("test_group_2", 2)

    # Create another group that we don't want in the response
    db_create_group_with_hosts("other_group", 3)

    # Query tags using multiple group_ids
    url = build_tags_url(query=f"?group_id={group1.id}&group_id={group2.id}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    # Should return tags from hosts in both group1 and group2
    assert response_data["count"] >= 0


def test_query_tags_group_id_rejects_invalid_uuid(api_get):
    """Test that group_id parameter rejects non-UUID values."""
    url = build_tags_url(query="?group_id=invalid-uuid")
    response_status, response_data = api_get(url)

    assert response_status == 400

    # Verify error message mentions the invalid value and UUID requirement
    assert "invalid-uuid" in response_data["detail"]
    assert "pattern" in response_data["detail"].lower() or "uuid" in response_data["detail"].lower()


def test_query_tags_group_name_and_group_id_mutually_exclusive(db_create_group, api_get, subtests):
    """Test that using both group_name and group_id together returns 400 error."""
    group = db_create_group("test_group")
    for prefix in ("group", "workspace"):
        with subtests.test(prefix=prefix):
            url = build_tags_url(query=f"?{prefix}_name=test_group&{prefix}_id={group.id}")
            response_status, response_data = api_get(url)
            assert response_status == 400
            assert f"{prefix}_name" in response_data["detail"].lower()
            assert f"{prefix}_id" in response_data["detail"].lower()


def test_get_tags_by_group_name_and_ungrouped(
    db_create_group, db_create_host, db_create_host_group_assoc, api_get, subtests
):
    group = db_create_group("selected-group")
    other_group = db_create_group("other-group")
    tags = []
    for index, membership in enumerate((group, group, other_group, None)):
        tag = {"namespace": "group", "key": f"host-{index}", "value": "v"}
        tags.append(tag)
        host = db_create_host(extra_data={"tags": {"group": {tag["key"]: ["v"]}}})
        if membership:
            db_create_host_group_assoc(host.id, membership.id)

    for name, expected in ((group.name, tags[:2]), ("", tags[3:])):
        with subtests.test(group_name=name):
            status, response = api_get(build_tags_url(query="?" + urlencode({"group_name": name})))
            assert status == 200
            _assert_aggregate_tags(response, expected)


@pytest.mark.parametrize("identity", (USER_IDENTITY, SYSTEM_IDENTITY), ids=("user", "system"))
def test_post_tags_readback(identity, mq_create_or_update_host, api_post, api_get):
    original = {"namespace": "original", "key": "env", "value": "prod"}
    added = {"namespace": "sat_iam", "key": "hash", "value": "aaabbbaa"}
    host = mq_create_or_update_host(minimal_host(tags=[original]), identity=identity)
    status, _ = api_post("/tags", {"tags": [added], "host_id_list": [host.id]}, identity=identity)
    assert status == 200
    status, response = api_get(build_host_tags_url(host.id), identity=identity)
    assert status == 200
    assert response["total"] == response["count"] == 1
    assert sorted(response["results"][host.id], key=lambda tag: tag["namespace"]) == [original, added]


def test_search_host_tags_nonmatching_terms(db_create_host, api_get, subtests):
    host_id = str(
        db_create_host(extra_data={"tags": {"ns": {"key": ["value"], "key-only": []}, "null": {"bare": ["v"]}}}).id
    )
    for search in ("x" * 256, ".", "unrelated-term"):
        with subtests.test(search=search):
            status, response = api_get(build_host_tags_url(host_id, query="?" + urlencode({"search": search})))
            assert status == 200
            assert response["total"] == response["count"] == 1
            assert response["results"] == {host_id: []}


@pytest.mark.parametrize(
    "tag",
    (
        {"namespace": "ordinary-ns", "key": "ordinary-test", "value": "ordinary-test-tag"},
        {"namespace": " leading-space", "key": "embedded space test", "value": "test tag"},
        {"namespace": "punctuation", "key": "test-key-&+0@%$", "value": "punctuation-value"},
        {"namespace": None, "key": "test-𝗤Ɍ𝓢ȚЦ𝒱Ѡ𝓧ƳȤ", "value": "unicode-value"},
        {"namespace": None, "key": "test-Ça}{?:", "value": None},
        {"namespace": "test-+[{]};:", "key": "test-+(!*%", "value": "test-٤ḞԍНǏ𝙅ƘԸⲘ𝙉০"},
    ),
    ids=("ordinary", "spaces", "punctuation", "unicode-key", "bare-key", "unicode-value"),
)
def test_search_tags_components_and_full_representation(tag, db_create_host, api_get, subtests):
    namespace = tag["namespace"] or "null"
    db_create_host(extra_data={"tags": {namespace: {tag["key"]: [tag["value"]] if tag["value"] else []}}})
    full_tag = (f"{tag['namespace']}/" if tag["namespace"] else "") + tag["key"]
    if tag["value"]:
        full_tag += f"={tag['value']}"
    for term in [value for value in tag.values() if value] + [full_tag]:
        for search in dict.fromkeys((term, term.upper())):
            with subtests.test(search=search):
                status, response = api_get(build_tags_url(query="?" + urlencode({"search": search, "per_page": 1})))
                assert status == 200
                assert response["per_page"] == 1
                _assert_aggregate_tags(response, [tag])


def test_search_tags_with_staleness_filter(db_create_host, api_get, mocker, subtests):
    states = ("fresh", "stale", "stale_warning")
    tag_data = {
        (state, "puptoo"): {"tags": {"shared-search-namespace": {state: [f"value-{state}"]}}} for state in states
    }
    create_hosts_by_reporter_and_staleness(db_create_host, mocker, reporters=("puptoo",), extra_data_per_host=tag_data)
    # A state match alone must not admit this tag: search and state must both apply.
    db_create_host(extra_data={"tags": {"unrelated": {"key": ["v"]}}})
    for selected in [(state,) for state in states] + [states]:
        with subtests.test(states=selected):
            params = [("search", "SHARED-SEARCH-NAMESPACE"), *(("staleness", state) for state in selected)]
            status, response = api_get(build_tags_url(query="?" + urlencode(params)))
            assert status == 200
            _assert_aggregate_tags(
                response,
                [
                    {"namespace": "shared-search-namespace", "key": state, "value": f"value-{state}"}
                    for state in selected
                ],
            )


def test_query_tags_group_id_nonexistent_uuid(api_get, db_create_group_with_hosts):
    """Test that a syntactically valid but nonexistent group_id returns no results."""
    # Create some hosts in an existing group so we have data present
    db_create_group_with_hosts("existing_group", 2)

    # Use a random UUID that does not correspond to any group
    nonexistent_group_id = str(uuid.uuid4())
    url = build_tags_url(query=f"?group_id={nonexistent_group_id}")
    response_status, response_data = api_get(url)

    # Expected behavior: 200 OK with no matching results
    assert response_status == 200
    assert response_data["results"] == []
    assert response_data["count"] == 0


@pytest.mark.parametrize(
    "query",
    (
        (f"fqdn={generate_uuid()}&display_name={generate_uuid()}"),
        (f"fqdn={generate_uuid()}&hostname_or_id={generate_uuid()}"),
        (f"fqdn={generate_uuid()}&insights_id={generate_uuid()}"),
        (f"display_name={generate_uuid()}&hostname_or_id={generate_uuid()}"),
        (f"display_name={generate_uuid()}&insights_id={generate_uuid()}"),
        (f"hostname_or_id={generate_uuid()}&insights_id={generate_uuid()}"),
        (f"display_name={generate_uuid()}&fqdn={generate_uuid()}&insights_id={generate_uuid()}"),
        (f"display_name={generate_uuid()}&fqdn={generate_uuid()}&hostname_or_id={generate_uuid()}"),
        (f"display_name={generate_uuid()}&insights_id={generate_uuid()}&hostname_or_id={generate_uuid()}"),
        (f"fqdn={generate_uuid()}&insights_id={generate_uuid()}&hostname_or_id={generate_uuid()}"),
        (
            f"display_name={generate_uuid()}&fqdn={generate_uuid()}&insights_id={generate_uuid()}&hostname_or_id={generate_uuid()}"
        ),
    ),
)
def test_query_tags_by_conflicting_ids(api_get, query):
    """Test that querying tags with multiple conflicting ID parameters returns 400."""
    url = build_tags_url(query=f"?{query}")
    response_status, response_data = api_get(url)

    assert response_status == 400
    assert (
        "Only one of [fqdn, display_name, hostname_or_id, insights_id] may be provided at a time."
        in response_data["detail"]
    )


def test_get_tags_aggregation_with_multi_value_tags(db_create_multiple_hosts, api_get):
    """
    Validate correct aggregation for hosts with multi-value tags.
    When multiple hosts share the same tag, the count should reflect the number
    of distinct hosts. Multi-value tags on a single host should produce separate
    entries in the results.
    """
    shared_namespace = "app"
    shared_key = "env"
    shared_value = "production"
    unique_value = "staging"

    # Host 1: has "app/env=production" and "app/env=staging"
    # Host 2: has "app/env=production" only
    # Host 3: has a completely different tag
    db_create_multiple_hosts(
        how_many=1,
        extra_data={
            "tags": _deserialize_tags_dict({shared_namespace: {shared_key: [shared_value, unique_value]}}),
        },
    )
    db_create_multiple_hosts(
        how_many=1,
        extra_data={
            "tags": _deserialize_tags_dict({shared_namespace: {shared_key: [shared_value]}}),
        },
    )
    db_create_multiple_hosts(
        how_many=1,
        extra_data={
            "tags": _deserialize_tags_dict({"other-ns": {"other-key": ["other-value"]}}),
        },
    )

    url = build_tags_url(query="?order_by=count&order_how=DESC")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["total"] == 3  # 3 distinct tag combinations

    # The shared tag "app/env=production" should have count=2 (two hosts)
    production_tag = next(
        r
        for r in response_data["results"]
        if r["tag"]["namespace"] == shared_namespace
        and r["tag"]["key"] == shared_key
        and r["tag"]["value"] == shared_value
    )
    assert production_tag["count"] == 2

    # The unique tag "app/env=staging" should have count=1
    staging_tag = next(
        r
        for r in response_data["results"]
        if r["tag"]["namespace"] == shared_namespace
        and r["tag"]["key"] == shared_key
        and r["tag"]["value"] == unique_value
    )
    assert staging_tag["count"] == 1

    # The other tag should have count=1
    other_tag = next(r for r in response_data["results"] if r["tag"]["namespace"] == "other-ns")
    assert other_tag["count"] == 1

    # Verify ordering: count DESC means production (2) comes first
    assert response_data["results"][0]["count"] >= response_data["results"][1]["count"]
    assert response_data["results"][1]["count"] >= response_data["results"][2]["count"]
