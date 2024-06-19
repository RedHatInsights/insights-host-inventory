import json


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
