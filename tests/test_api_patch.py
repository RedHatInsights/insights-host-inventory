#!/usr/bin/env python
import json
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from unittest import main
from unittest.mock import patch

import dateutil.parser

from .test_api_utils import generate_uuid
from .test_api_utils import HOST_URL
from .test_api_utils import PreCreatedHostsBaseTestCase


@patch("api.host.emit_event")
class PatchHostTestCase(PreCreatedHostsBaseTestCase):
    def setUp(self):
        super().setUp()
        self.now_timestamp = datetime.now(timezone.utc)

    def test_update_fields(self, emit_event):
        original_id = self.added_hosts[0].id

        patch_docs = [
            {"ansible_host": "NEW_ansible_host"},
            {"ansible_host": ""},
            {"display_name": "fred_flintstone"},
            {"display_name": "fred_flintstone", "ansible_host": "barney_rubble"},
        ]

        for patch_doc in patch_docs:
            with self.subTest(valid_patch_doc=patch_doc):
                response_data = self.patch(f"{HOST_URL}/{original_id}", patch_doc, 200)

                response_data = self.get(f"{HOST_URL}/{original_id}", 200)

                host = response_data["results"][0]

                for key in patch_doc:
                    self.assertEqual(host[key], patch_doc[key])

    def test_patch_with_branch_id_parameter(self, emit_event):
        patch_doc = {"display_name": "branch_id_test"}

        url_host_id_list = self._build_host_id_list_for_url(self.added_hosts)

        test_url = f"{HOST_URL}/{url_host_id_list}?branch_id=123"

        self.patch(test_url, patch_doc, 200)

    def test_update_fields_on_multiple_hosts(self, emit_event):
        patch_doc = {"display_name": "fred_flintstone", "ansible_host": "barney_rubble"}

        url_host_id_list = self._build_host_id_list_for_url(self.added_hosts)

        test_url = f"{HOST_URL}/{url_host_id_list}"

        self.patch(test_url, patch_doc, 200)

        response_data = self.get(test_url, 200)

        for host in response_data["results"]:
            for key in patch_doc:
                self.assertEqual(host[key], patch_doc[key])

    def test_patch_on_non_existent_host(self, emit_event):
        non_existent_id = generate_uuid()

        patch_doc = {"ansible_host": "NEW_ansible_host"}

        self.patch(f"{HOST_URL}/{non_existent_id}", patch_doc, status=404)

    def test_patch_on_multiple_hosts_with_some_non_existent(self, emit_event):
        non_existent_id = generate_uuid()
        original_id = self.added_hosts[0].id

        patch_doc = {"ansible_host": "NEW_ansible_host"}

        self.patch(f"{HOST_URL}/{non_existent_id},{original_id}", patch_doc)

    def test_invalid_data(self, emit_event):
        original_id = self.added_hosts[0].id

        invalid_data_list = [
            {"ansible_host": "a" * 256},
            {"ansible_host": None},
            {},
            {"display_name": None},
            {"display_name": ""},
        ]

        for patch_doc in invalid_data_list:
            with self.subTest(invalid_patch_doc=patch_doc):
                response = self.patch(f"{HOST_URL}/{original_id}", patch_doc, status=400)

                self.verify_error_response(response, expected_title="Bad Request", expected_status=400)

    def test_invalid_host_id(self, emit_event):
        patch_doc = {"display_name": "branch_id_test"}
        host_id_lists = ["notauuid", f"{self.added_hosts[0].id},notauuid"]
        for host_id_list in host_id_lists:
            with self.subTest(host_id_list=host_id_list):
                self.patch(f"{HOST_URL}/{host_id_list}", patch_doc, 400)

    def _base_patch_produces_update_event_test(self, emit_event, headers, expected_request_id):
        patch_doc = {"display_name": "patch_event_test"}
        host_to_patch = self.added_hosts[0].id

        with patch("app.queue.egress.datetime", **{"now.return_value": self.now_timestamp}):
            self.patch(f"{HOST_URL}/{host_to_patch}", patch_doc, 200, extra_headers=headers)

        expected_event_message = {
            "type": "updated",
            "host": {
                "account": self.added_hosts[0].account,
                "ansible_host": self.added_hosts[0].ansible_host,
                "bios_uuid": self.added_hosts[0].bios_uuid,
                "created": self.added_hosts[0].created,
                "culled_timestamp": (
                    dateutil.parser.parse(self.added_hosts[0].stale_timestamp) + timedelta(weeks=2)
                ).isoformat(),
                "display_name": "patch_event_test",
                "external_id": self.added_hosts[0].external_id,
                "fqdn": self.added_hosts[0].fqdn,
                "id": self.added_hosts[0].id,
                "insights_id": self.added_hosts[0].insights_id,
                "ip_addresses": self.added_hosts[0].ip_addresses,
                "mac_addresses": self.added_hosts[0].mac_addresses,
                "reporter": self.added_hosts[0].reporter,
                "rhel_machine_id": self.added_hosts[0].rhel_machine_id,
                "satellite_id": self.added_hosts[0].satellite_id,
                "stale_timestamp": self.added_hosts[0].stale_timestamp,
                "stale_warning_timestamp": (
                    dateutil.parser.parse(self.added_hosts[0].stale_timestamp) + timedelta(weeks=1)
                ).isoformat(),
                "subscription_manager_id": self.added_hosts[0].subscription_manager_id,
                "system_profile": {},
                "tags": [
                    {"namespace": "no", "key": "key", "value": None},
                    {"namespace": "NS1", "key": "key1", "value": "val1"},
                    {"namespace": "NS1", "key": "key2", "value": "val1"},
                    {"namespace": "SPECIAL", "key": "tag", "value": "ToFind"},
                ],
                "updated": self.added_hosts[0].updated,
            },
            "platform_metadata": None,
            "metadata": {"request_id": expected_request_id},
            "timestamp": self.now_timestamp.isoformat(),
        }

        emit_event.assert_called_once()
        emitted_event = emit_event.call_args[0]
        event_message = json.loads(emitted_event[0])

        self.assertEqual(event_message, expected_event_message)
        self.assertEqual(emitted_event[1], self.added_hosts[0].id)
        self.assertEqual(emitted_event[2], {"event_type": "updated"})

    def test_patch_produces_update_event_no_request_id(self, emit_event):
        self._base_patch_produces_update_event_test(emit_event, {}, "-1")

    def test_patch_produces_update_event_with_request_id(self, emit_event):
        request_id = generate_uuid()
        headers = {"x-rh-insights-request-id": request_id}
        self._base_patch_produces_update_event_test(emit_event, headers, request_id)


if __name__ == "__main__":
    main()
