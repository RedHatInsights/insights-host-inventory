# Adjust this import to match the actual location of the utility
import pytest

from app.exceptions import IdsNotFoundError
from app.utils import check_all_ids_found


def test_check_all_ids_found_with_duplicate_ids():
    """
    When the requested IDs contain duplicates, `check_all_ids_found`
    should not return duplicate entries in the not_found_ids list.
    """
    requested_ids = [
        "11111111-1111-1111-1111-111111111111",
        "11111111-1111-1111-1111-111111111111",  # duplicate
        "22222222-2222-2222-2222-222222222222",
        "33333333-3333-3333-3333-333333333333",
    ]

    # Two IDs exist, one is missing
    existing_hosts = [
        {"id": "11111111-1111-1111-1111-111111111111"},
        {"id": "22222222-2222-2222-2222-222222222222"},
    ]

    with pytest.raises(IdsNotFoundError) as e:
        check_all_ids_found(requested_ids, existing_hosts, "host")

    # Only the truly missing ID should be returned, and only once
    assert e.value.not_found_ids == ["33333333-3333-3333-3333-333333333333"]


def test_check_all_ids_found_with_dict_objects():
    """
    `check_all_ids_found` should work when the "found" collection consists
    of dict objects (e.g., SQLAlchemy row mappings or serialized models).
    """
    requested_ids = [
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "cccccccc-cccc-cccc-cccc-cccccccccccc",
    ]

    # Simulate dict-based DB rows or API objects
    found_items = [
        {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
        {"id": "cccccccc-cccc-cccc-cccc-cccccccccccc"},
    ]

    with pytest.raises(IdsNotFoundError) as e:
        check_all_ids_found(requested_ids, found_items, "group")

    # Only the ID that does not appear in the dict objects should be returned
    assert e.value.not_found_ids == ["bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"]
