"""Reject malformed host IDs consistently at each mutation/profile route."""

from tests.helpers.api_utils import HOST_URL
from tests.helpers.test_utils import INVALID_UUIDS
from tests.helpers.test_utils import generate_uuid


def test_invalid_uuid_request_matrix(api_get, api_delete_host, api_patch, api_put, subtests):
    valid_id = generate_uuid()
    # These are the five IQE equivalence classes; empty IDs are a different routing contract.
    for invalid_id in INVALID_UUIDS[:5]:
        single, mixed = invalid_id, f"{valid_id},{invalid_id}"
        for host_ids in (single, mixed):
            with subtests.test(method="GET profile", host_ids=host_ids):
                status, body = api_get(f"{HOST_URL}/{host_ids}/system_profile")
                assert status == 400
                assert "does not match" in body["detail"]
                assert invalid_id in body["detail"]
            with subtests.test(method="PATCH host", host_ids=host_ids):
                status, body = api_patch(f"{HOST_URL}/{host_ids}", {"ansible_host": "invalid.example.com"})
                assert status == 400
                assert "does not match" in body["detail"]
                assert invalid_id in body["detail"]
            with subtests.test(method="PATCH facts", host_ids=host_ids):
                status, body = api_patch(f"{HOST_URL}/{host_ids}/facts/account-test", {"fact": "value"})
                assert status == 400
                assert "does not match" in body["detail"]
                assert invalid_id in body["detail"]
        for host_ids in (single, f"{invalid_id},{invalid_id}"):
            with subtests.test(method="DELETE", host_ids=host_ids):
                status, body = api_delete_host(host_ids)
                assert status == 400
                assert "does not match" in body["detail"]
                assert invalid_id in body["detail"]
        with subtests.test(method="PUT facts", host_ids=single):
            status, body = api_put(f"{HOST_URL}/{single}/facts/account-test", {"fact": "value"})
            assert status == 400
            assert "does not match" in body["detail"]
            assert invalid_id in body["detail"]
