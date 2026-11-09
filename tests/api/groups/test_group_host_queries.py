from datetime import timedelta

from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import now


def test_group_host_filters_and_paging(
    subtests, mocker, db_create_group, db_create_host, db_create_host_group_assoc, api_get_hosts_from_group
):
    group_id = db_create_group("query-group").id
    outside_group_id = db_create_group("outside-group").id
    reference_time = now()
    hosts = []
    # Two prod web hosts, three dev web hosts, and a non-web distractor. Insertion
    # order disagrees with display-name order, and all three visible states occur.
    rows = [
        ("web-prod-02", "prod", 0),
        ("web-dev-03", "dev", 10),
        ("db-dev-01", "dev", 0),
        ("web-prod-01", "prod", 3),
        ("web-dev-01", "dev", 0),
        ("web-dev-02", "dev", 0),
    ]
    for idx, (name, environment, days_old) in enumerate(rows):
        with mocker.patch(
            "app.models.utils.datetime", **{"now.return_value": reference_time - timedelta(days=days_old)}
        ):
            host = db_create_host(
                extra_data={
                    "display_name": name,
                    "fqdn": f"host-{idx}.example.com",
                    "insights_id": generate_uuid(),
                    "tags": {"app": {"env": [environment]}, "location": {"region": ["east" if idx == 0 else "west"]}},
                }
            )
        db_create_host_group_assoc(host.id, group_id)
        hosts.append(
            {"id": str(host.id), "display_name": name, "fqdn": host.fqdn, "insights_id": str(host.insights_id)}
        )

    # Same filter values outside the requested group must never leak into results.
    outside = db_create_host(
        extra_data={
            "display_name": "web-prod-00",
            "fqdn": hosts[0]["fqdn"],
            "insights_id": hosts[0]["insights_id"],
            "tags": {"app": {"env": ["prod"]}},
        }
    )
    db_create_host_group_assoc(outside.id, outside_group_id)

    for query, indexes in (
        ({"display_name": "web-prod"}, [0, 3]),
        ({"fqdn": hosts[0]["fqdn"]}, [0]),
        ({"insights_id": hosts[0]["insights_id"]}, [0]),
        ({"tags": ["app/env=prod"]}, [0, 3]),
        ({"staleness": ["fresh", "stale"]}, [0, 2, 3, 4, 5]),
    ):
        with subtests.test(query=query):
            response_status, response_data = api_get_hosts_from_group(group_id, query_parameters=query)
            assert response_status == 200
            assert response_data["total"] == response_data["count"] == len(indexes)
            assert len(response_data["results"]) == len(indexes)
            assert {host["id"] for host in response_data["results"]} == {hosts[idx]["id"] for idx in indexes}
            for host in response_data["results"]:
                expected = next(item for item in hosts if item["id"] == host["id"])
                for field in ("display_name", "fqdn", "insights_id"):
                    assert host[field] == expected[field]

    # Filter before sorting and paging: the db host would otherwise occupy the
    # first slot, and the outside web host would otherwise sort before all matches.
    expected = sorted(
        (host for host in hosts if host["display_name"].startswith("web-")), key=lambda host: host["display_name"]
    )
    found = []
    for page in (1, 2):
        with subtests.test(filtered_page=page):
            response_status, response_data = api_get_hosts_from_group(
                group_id,
                query_parameters={
                    "display_name": "web-",
                    "order_by": "display_name",
                    "order_how": "ASC",
                    "per_page": 3,
                    "page": page,
                },
            )
            assert response_status == 200
            assert response_data["page"] == page
            assert response_data["per_page"] == 3
            assert response_data["total"] == 5
            page_expected = expected[(page - 1) * 3 : page * 3]
            assert response_data["count"] == len(response_data["results"]) == len(page_expected)
            assert [host["id"] for host in response_data["results"]] == [host["id"] for host in page_expected]
            assert [host["display_name"] for host in response_data["results"]] == [
                host["display_name"] for host in page_expected
            ]
            found.extend(host["id"] for host in response_data["results"])
    assert len(found) == len(set(found)) == 5
    assert set(found) == {host["id"] for host in expected}
