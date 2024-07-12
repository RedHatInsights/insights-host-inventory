import csv
import json

from app.serialization import _EXPORT_SERVICE_FIELDS

EXPORT_DATA = [
    {
        "account": None,
        "ansible_host": None,
        "bios_uuid": "84353df8-b7c4-4175-9381-d5db8620256a",
        "created": "2024-07-01T14:10:07.477718+00:00",
        "culled_timestamp": "2024-07-15T14:10:07.477723+00:00",
        "display_name": "5b7809.foo.redhat.com",
        "facts": [],
        "fqdn": None,
        "groups": [],
        "id": "a4f67e55-211e-48b9-aca2-6ca75d3e7df2",
        "insights_id": None,
        "ip_addresses": None,
        "mac_addresses": None,
        "org_id": "5894300",
        "per_reporter_staleness": {
            "puptoo": {
                "check_in_succeeded": True,
                "culled_timestamp": "2024-07-15T14:10:07.471297+00:00",
                "last_check_in": "2024-07-01T14:10:07.471297+00:00",
                "stale_timestamp": "2024-07-02T19:10:07.471297+00:00",
                "stale_warning_timestamp": "2024-07-08T14:10:07.471297+00:00",
            }
        },
        "provider_id": None,
        "provider_type": None,
        "reporter": "puptoo",
        "satellite_id": None,
        "stale_timestamp": "2024-07-02T19:10:07.477723+00:00",
        "stale_warning_timestamp": "2024-07-08T14:10:07.477723+00:00",
        "subscription_manager_id": None,
        "updated": "2024-07-01T14:10:07.477723+00:00",
    },
    {
        "account": None,
        "ansible_host": None,
        "bios_uuid": "c02323d4-7c46-485b-be0c-48d9b469e9b2",
        "created": "2024-07-01T14:09:59.483978+00:00",
        "culled_timestamp": "2024-07-15T14:09:59.483983+00:00",
        "display_name": "c5f819.foo.redhat.com",
        "facts": [],
        "fqdn": None,
        "groups": [],
        "id": "31cf889d-25f8-46e2-b615-33c0e173a10b",
        "insights_id": None,
        "ip_addresses": None,
        "mac_addresses": None,
        "org_id": "5894300",
        "per_reporter_staleness": {
            "puptoo": {
                "check_in_succeeded": True,
                "culled_timestamp": "2024-07-15T14:09:59.478123+00:00",
                "last_check_in": "2024-07-01T14:09:59.478123+00:00",
                "stale_timestamp": "2024-07-02T19:09:59.478123+00:00",
                "stale_warning_timestamp": "2024-07-08T14:09:59.478123+00:00",
            }
        },
        "provider_id": None,
        "provider_type": None,
        "reporter": "puptoo",
        "satellite_id": None,
        "stale_timestamp": "2024-07-02T19:09:59.483983+00:00",
        "stale_warning_timestamp": "2024-07-08T14:09:59.483983+00:00",
        "subscription_manager_id": None,
        "updated": "2024-07-01T14:09:59.483983+00:00",
    },
]


def create_export_message_mock():
    return json.dumps(
        {
            "id": "b4228e37-8ae8-4c67-81d5-d03f39bbe309",
            "$schema": "someSchema",
            "source": "urn:redhat:source:console:app:export-service",
            "subject": "urn:redhat:subject:export-service:request:9becbc61-49a4-49be-beb1-1f0a7cbc6e36",
            "specversion": "1.0",
            "type": "com.redhat.console.export-service.request",
            "time": "2024-05-28T14:59:36Z",
            "redhatorgid": "5894300",
            "dataschema": "https://console.redhat.com/api/schemas/apps/export-service/v1/resource-request.json",
            "data": {
                "resource_request": {
                    "application": "urn:redhat:application:inventory",
                    "export_request_uuid": "9becbc61-49a4-49be-beb1-1f0a7cbc6e36",
                    "filters": {
                        "endDate": "2024-03-01T00:00:00Z",
                        "productId": "RHEL",
                        "startDate": "2024-01-01T00:00:00Z",
                    },
                    "format": "json",
                    "resource": "urn:redhat:application:inventory:export:systems",
                    "uuid": "2844f3a1-e047-45b1-b0ce-fb9812ad6a6f",
                    "x-rh-identity": (
                        "eyJpZGVudGl0eSI6IHsib3JnX2lkIjogIjU4OTQzMD"
                        "AiLCAidHlwZSI6ICJVc2VyIiwgImF1dGhfdHlwZSI6"
                        "ICJiYXNpYy1hdXRoIiwgInVzZXIiOiB7ImVtYWlsIj"
                        "ogImpyYW1vc0ByZWRoYXQuY29tIiwgImZpcnN0X25hbWUiOiAidGVzdCJ9fX0="
                    ),
                }
            },
        }
    )


def create_export_message_missing_field_mock(field_to_remove):
    message = {
        "id": "b4228e37-8ae8-4c67-81d5-d03f39bbe309",
        "$schema": "someSchema",
        "source": "urn:redhat:source:console:app:export-service",
        "subject": "urn:redhat:subject:export-service:request:9becbc61-49a4-49be-beb1-1f0a7cbc6e36",
        "specversion": "1.0",
        "type": "com.redhat.console.export-service.request",
        "time": "2024-05-28T14:59:36Z",
        "redhatorgid": "5894300",
        "dataschema": "https://console.redhat.com/api/schemas/apps/export-service/v1/resource-request.json",
        "data": {
            "resource_request": {
                "application": "urn:redhat:application:inventory",
                "export_request_uuid": "9becbc61-49a4-49be-beb1-1f0a7cbc6e36",
                "filters": {
                    "endDate": "2022-03-01T00:00:00Z",
                    "productId": "RHEL",
                    "startDate": "2022-01-01T00:00:00Z",
                },
                "format": "json",
                "resource": "urn:redhat:application:inventory:export:systems",
                "uuid": "2844f3a1-e047-45b1-b0ce-fb9812ad6a6f",
                "x-rh-identity": (
                    "eyJpZGVudGl0eSI6IHsib3JnX2lkIjogIjU4OTQzMD"
                    "AiLCAidHlwZSI6ICJVc2VyIiwgImF1dGhfdHlwZSI6"
                    "ICJiYXNpYy1hdXRoIiwgInVzZXIiOiB7ImVtYWlsIj"
                    "ogImpyYW1vc0ByZWRoYXQuY29tIiwgImZpcnN0X25hbWUiOiAidGVzdCJ9fX0="
                ),
            }
        },
    }
    message.pop(field_to_remove)
    return json.dumps(message)


def read_csv(csv_content):
    data = []
    with open(csv_content, newline="") as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            data.append(row)
    return data


def create_export_csv_mock(mocker):
    row = [mocker.ANY] * len(_EXPORT_SERVICE_FIELDS)

    return [_EXPORT_SERVICE_FIELDS, row]


def create_export_json_mock(mocker):
    return [
        {
            "id": mocker.ANY,
            "subscription_manager_id": mocker.ANY,
            "satellite_id": mocker.ANY,
            "display_name": mocker.ANY,
            "group_id": mocker.ANY,
            "group_name": mocker.ANY,
            "os_release": mocker.ANY,
            "updated": mocker.ANY,
            "state": mocker.ANY,
            "tags": mocker.ANY,
            "host_type": mocker.ANY,
        }
    ]
