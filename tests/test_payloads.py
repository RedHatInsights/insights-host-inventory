import pytest

from app.models import InputGroupSchema
from utils.payloads import build_group_payload


def test_group_payload_defaults():
    payload = build_group_payload()
    another_payload = build_group_payload()

    assert InputGroupSchema().load(payload) == payload
    assert InputGroupSchema().load(another_payload) == another_payload
    assert payload["name"] != another_payload["name"]
    assert payload["host_ids"] == []

    payload["host_ids"].append("489c5a7e-3d73-40ec-a873-a5eccebdcd6a")
    assert another_payload["host_ids"] == []


@pytest.mark.parametrize("name", ["development-group", "Production Servers_1", "a" * 255])
@pytest.mark.parametrize(
    "host_ids",
    [
        None,
        [],
        ["489c5a7e-3d73-40ec-a873-a5eccebdcd6a", "a17a21c6-a4c4-44ec-a42c-5499ad511df2"],
    ],
)
def test_group_payload_custom_values(name, host_ids):
    payload = build_group_payload(name=name, host_ids=host_ids)

    assert payload == {"name": name, "host_ids": host_ids if host_ids is not None else []}
    assert InputGroupSchema().load(payload) == payload


def test_group_payload_generated_name_with_existing_hosts():
    host_ids = ["489c5a7e-3d73-40ec-a873-a5eccebdcd6a"]

    payload = build_group_payload(host_ids=host_ids)

    assert payload["host_ids"] == host_ids
    assert InputGroupSchema().load(payload) == payload


def test_group_payload_does_not_share_host_ids():
    host_ids = ["489c5a7e-3d73-40ec-a873-a5eccebdcd6a"]
    payload = build_group_payload(host_ids=host_ids)

    payload["host_ids"].clear()
    assert host_ids == ["489c5a7e-3d73-40ec-a873-a5eccebdcd6a"]

    host_ids.append("a17a21c6-a4c4-44ec-a42c-5499ad511df2")
    assert payload["host_ids"] == []
