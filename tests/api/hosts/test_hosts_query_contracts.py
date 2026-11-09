from datetime import UTC
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from app.models import db
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_system_profile_url
from tests.helpers.test_utils import generate_uuid


def test_identity_provider_and_legacy_registration_filters(db_create_host, api_get, subtests):
    target = db_create_host(
        extra_data={"subscription_manager_id": generate_uuid(), "provider_id": "i-abc123", "provider_type": "aws"}
    )
    azure = db_create_host(extra_data={"provider_id": "azure-other", "provider_type": "azure"})
    missing = db_create_host(extra_data={"insights_id": None, "subscription_manager_id": generate_uuid()})
    queries = [({}, {str(host.id) for host in (target, azure, missing)})]
    for field in ("insights_id", "subscription_manager_id", "provider_id"):
        original = str(getattr(target, field))
        for value in (original, original.upper()):
            queries.append(({field: value}, {str(target.id)}))
    queries.extend(
        [
            ({"insights_id": generate_uuid()}, set()),
            ({"provider_id": "invalid"}, set()),
            ({"provider_type": "aws"}, {str(target.id)}),
            ({"registered_with": "insights"}, {str(target.id), str(azure.id)}),
        ]
    )
    for query, expected_ids in queries:
        with subtests.test(query=query):
            status, data = api_get(build_hosts_url(), query_parameters=query)
            assert status == 200
            assert data["count"] == len(expected_ids)
            assert {host["id"] for host in data["results"]} == expected_ids
    status, data = api_get(build_hosts_url(), query_parameters={"provider_type": "invalid"})
    assert status == 400
    assert "invalid" in data["detail"]


def test_by_id_ignores_branch_id(db_create_host, api_get, api_patch, event_producer, mocker, subtests):
    mocker.patch.object(event_producer, "write_event")
    ids = [str(db_create_host().id) for _ in range(2)]
    for host_ids in (ids[:1], ids):
        for branch_id in (None, "some_branch", 12345, 42.1):
            with subtests.test(host_ids=host_ids, branch_id=branch_id):
                query = {} if branch_id is None else {"branch_id": branch_id}
                status, data = api_get(build_hosts_url(host_ids), query_parameters=query)
                assert status == 200
                assert data["total"] == data["count"] == len(host_ids)
                assert {host["id"] for host in data["results"]} == set(host_ids)
    for branch_id, value in ((42.1, "patched-with-branch"), (None, "patched-without-branch")):
        query = {} if branch_id is None else {"branch_id": branch_id}
        status, _ = api_patch(build_hosts_url(ids), {"ansible_host": value}, query_parameters=query)
        assert status == 200
        status, data = api_get(build_hosts_url(ids))
        assert status == 200
        assert {host["id"] for host in data["results"]} == set(ids)
        assert all(host["ansible_host"] == value for host in data["results"])


def test_filter_conjunctions(db_create_host, db_create_group, db_create_host_group_assoc, api_get, subtests):
    instant = datetime.now(UTC).replace(microsecond=0)
    group = db_create_group("query-contract")
    common = {
        "display_name": "target-name",
        "fqdn": "target.example.com",
        "insights_id": generate_uuid(),
        "subscription_manager_id": generate_uuid(),
        "provider_type": "aws",
        "tags": {"query": {"key": ["target"]}},
    }
    # Each decoy fails just one predicate, so dropping any AND term exposes it.
    changes = [
        {},
        {
            "display_name": "other",
            "fqdn": "other.example.com",
            "insights_id": generate_uuid(),
            "subscription_manager_id": generate_uuid(),
        },
        {"provider_type": "azure"},
        {"tags": {"query": {"key": ["other"]}}},
        {},  # stale
        {},  # before updated_start
        {},  # after updated_end
        {},  # different workspace
    ]
    hosts = []
    for index, change in enumerate(changes):
        host = db_create_host(extra_data={**common, **change, "provider_id": generate_uuid()})
        if index != 7:
            db_create_host_group_assoc(host.id, group.id)
        host.modified_on = instant + timedelta(hours={5: -2, 6: 2}.get(index, 0))
        host.last_check_in = instant - timedelta(days=2 if index == 4 else 0)
        hosts.append(host)
    db.session.commit()
    query = {
        "provider_type": "aws",
        "staleness": "fresh",
        "tags": "query/key=target",
        "updated_start": instant.isoformat(),
        "updated_end": instant.isoformat(),
        "workspace_name": group.name,
    }
    for field in ("display_name", "fqdn", "insights_id", "hostname_or_id", "subscription_manager_id"):
        with subtests.test(field=field):
            value = common["fqdn" if field == "hostname_or_id" else field]
            status, data = api_get(build_hosts_url(), query_parameters={**query, field: value})
            assert status == 200
            assert data["count"] == 1
            assert [host["id"] for host in data["results"]] == [str(hosts[0].id)]


def test_updated_bounds_and_timezones(db_create_host, api_get, subtests):
    start = datetime.now(UTC).replace(microsecond=123456) - timedelta(hours=2)
    hosts = [db_create_host() for _ in range(5)]
    times = [start + timedelta(minutes=index * 10) for index in range(5)]
    for host, instant in zip(hosts, times, strict=True):
        host.modified_on = instant
    db.session.commit()
    ids = [str(host.id) for host in hosts]
    for suffix in ("", "+00:00", "Z"):
        for exact in (True, False):
            lower = times[2] if exact else times[2] - timedelta(minutes=1)
            upper = times[2] if exact else times[2] + timedelta(minutes=1)
            for field, bound, expected in (("updated_start", lower, ids[2:]), ("updated_end", upper, ids[:3])):
                with subtests.test(field=field, suffix=suffix, exact=exact):
                    value = bound.replace(tzinfo=None).isoformat() + suffix
                    status, data = api_get(build_hosts_url(), query_parameters={field: value})
                    assert status == 200
                    assert data["count"] == len(expected)
                    assert {host["id"] for host in data["results"]} == set(expected)
    ranges = [
        (times[1], times[3], ids[1:4]),
        (times[1] - timedelta(minutes=1), times[3] + timedelta(minutes=1), ids[1:4]),
        (times[2], times[2], ids[2:3]),
    ]
    for offset in (3, -3):
        zone = timezone(timedelta(hours=offset))
        ranges.append((times[1].astimezone(zone), times[3].astimezone(zone), ids[1:4]))
    for lower, upper, expected in ranges:
        with subtests.test(lower=lower, upper=upper):
            status, data = api_get(
                build_hosts_url(),
                query_parameters={"updated_start": lower.isoformat(), "updated_end": upper.isoformat()},
            )
            assert status == 200
            assert data["count"] == len(expected)
            assert {host["id"] for host in data["results"]} == set(expected)


def test_updated_filter_uses_latest_patch_not_creation(db_create_host, api_get, api_patch, event_producer, mocker):
    mocker.patch.object(event_producer, "write_event")
    start = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=2)
    hosts = [db_create_host() for _ in range(3)]
    for index, host in enumerate(hosts):
        host.created_on = start + timedelta(minutes=1 if index == 2 else -1)
        host.modified_on = host.created_on
    db.session.commit()
    clock = mocker.patch("app.models.utils.datetime")
    for host, minutes in ((hosts[1], 2), (hosts[2], 4)):
        clock.now.return_value = start + timedelta(minutes=minutes)
        status, _ = api_patch(build_hosts_url(str(host.id)), {"display_name": f"patched-{minutes}"})
        assert status == 200
    status, data = api_get(
        build_hosts_url(),
        query_parameters={
            "updated_start": start.isoformat(),
            "updated_end": (start + timedelta(minutes=3)).isoformat(),
        },
    )
    assert status == 200
    assert data["count"] == 1
    assert [host["id"] for host in data["results"]] == [str(hosts[1].id)]


def test_default_ordering_across_host_endpoints(
    db_create_host, db_create_group, db_create_host_group_assoc, api_get, subtests
):
    groups = [db_create_group("Zebra"), db_create_group("alpha"), db_create_group("ungrouped", ungrouped=True)]
    operating_systems = [
        {"name": "RHEL", "major": 9, "minor": 0},
        {"name": "CentOS", "major": 8, "minor": 0},
        {"name": "RHEL", "major": 8, "minor": 1},
        {"name": "RHEL", "major": 8, "minor": 0},
        None,
    ]
    hosts = []
    instant = datetime.now(UTC)
    for index, name in enumerate(("Zulu", "alpha", "Beta", "alpha", "delta")):
        profile = {"operating_system": operating_systems[index]} if operating_systems[index] else {}
        host = db_create_host(extra_data={"display_name": name, "system_profile_facts": profile})
        db_create_host_group_assoc(host.id, groups[index % 3].id)
        host.modified_on = instant - timedelta(minutes=index)
        host.last_check_in = instant - timedelta(minutes=(index * 3) % 5)
        hosts.append(host)
    db.session.commit()
    ids = [str(host.id) for host in hosts]
    expected_keys = {
        "updated": {ids[i]: hosts[i].modified_on for i in range(5)},
        "last_check_in": {ids[i]: hosts[i].last_check_in for i in range(5)},
        "display_name": {ids[i]: hosts[i].display_name.lower() for i in range(5)},
        "group_name": {ids[i]: "" if i % 3 == 2 else groups[i % 3].name.lower() for i in range(5)},
        "operating_system": {
            ids[i]: tuple(operating_systems[i][key] for key in ("name", "major", "minor"))
            if operating_systems[i]
            else ("", 0, 0)
            for i in range(5)
        },
    }
    for field, keys in expected_keys.items():
        with subtests.test(field=field):
            sequences = []
            for url in (build_hosts_url(), build_hosts_url(ids), build_system_profile_url(ids)):
                status, data = api_get(url, query_parameters={"order_by": field})
                assert status == 200
                assert data["count"] == len(ids)
                sequence = [host["id"] for host in data["results"]]
                assert set(sequence) == set(ids)
                actual_keys = [keys[host_id] for host_id in sequence]
                assert actual_keys == sorted(actual_keys, reverse=field not in ("display_name", "group_name"))
                sequences.append(sequence)
            assert sequences[0] == sequences[1] == sequences[2]
