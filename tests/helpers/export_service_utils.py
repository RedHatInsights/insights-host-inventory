import csv
import json

from app.serialization import _EXPORT_SERVICE_FIELDS

EXPORT_DATA = [
    {
        "display_name": "b4f637.foo.redhat.com",
        "fqdn": "b4f637.foo.redhat.com",
        "group_id": None,
        "group_name": None,
        "host_type": "conventional",
        "host_id": "80e3f012-c8e9-4435-8d84-307ff85536e4",
        "os_release": "Red Hat EL 7.0.1",
        "satellite_id": None,
        "state": "fresh",
        "subscription_manager_id": None,
        "tags": [
            {"key": "key3", "namespace": "NS1", "value": "val3"},
            {"key": "key3", "namespace": "NS3", "value": "val3"},
            {"key": "prod", "namespace": "Sat", "value": None},
            {"key": "key", "namespace": "SPECIAL", "value": "val"},
        ],
        "updated": "2024-07-23T16:24:41.159435+00:00",
    },
    {
        "display_name": "063406.foo.redhat.com",
        "fqdn": "063406.foo.redhat.com",
        "group_id": None,
        "group_name": None,
        "host_type": "conventional",
        "host_id": "c1eb8355-b00c-4b0e-af59-c691a0f88629",
        "os_release": "Red Hat EL 7.0.1",
        "satellite_id": None,
        "state": "fresh",
        "subscription_manager_id": None,
        "tags": [
            {"key": "key3", "namespace": "NS1", "value": "val3"},
            {"key": "key3", "namespace": "NS3", "value": "val3"},
            {"key": "prod", "namespace": "Sat", "value": None},
            {"key": "key", "namespace": "SPECIAL", "value": "val"},
        ],
        "updated": "2024-07-23T16:24:40.562889+00:00",
    },
    {
        "display_name": "43794f.foo.redhat.com",
        "fqdn": "43794f.foo.redhat.com",
        "group_id": None,
        "group_name": None,
        "host_type": "conventional",
        "host_id": "c0f828f6-5efe-476e-8abc-be4e93c4098c",
        "os_release": "Red Hat EL 7.0.1",
        "satellite_id": None,
        "state": "fresh",
        "subscription_manager_id": None,
        "tags": [
            {"key": "key3", "namespace": "NS1", "value": "val3"},
            {"key": "key3", "namespace": "NS3", "value": "val3"},
            {"key": "prod", "namespace": "Sat", "value": None},
            {"key": "key", "namespace": "SPECIAL", "value": "val"},
        ],
        "updated": "2024-07-23T16:24:41.167465+00:00",
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
            "host_id": mocker.ANY,
            "subscription_manager_id": mocker.ANY,
            "satellite_id": mocker.ANY,
            "display_name": mocker.ANY,
            "fqdn": mocker.ANY,
            "group_id": mocker.ANY,
            "group_name": mocker.ANY,
            "os_release": mocker.ANY,
            "updated": mocker.ANY,
            "state": mocker.ANY,
            "tags": mocker.ANY,
            "host_type": mocker.ANY,
        }
    ]
