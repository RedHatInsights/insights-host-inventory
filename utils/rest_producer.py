import base64
import json
from typing import Dict
from typing import Union

import payloads
import requests

# URL = "http://localhost:8080/r/insights/platform/inventory/api/v1/hosts" # LEGACY
URL = "http://localhost:8080/api/inventory/v1/hosts"
NUM_HOSTS = 1

org_id = "0000001"

bulk_insert = False

headers: Dict[str, Union[str, bytes]] = {"Content-type": "application/json", "x-rh-insights-request-id": "654321"}

# headers["Authorization"] = "Bearer secret"
# headers["Authorization"] = "Bearer 023e4f11185e4c17478bb9c6750d3068eeebe85b"

identity = {"identity": {"org_id": org_id}}
headers["x-rh-identity"] = base64.b64encode(json.dumps(identity).encode())


def main():
    all_payloads = [payloads.build_http_payload() for _ in range(NUM_HOSTS)]

    if bulk_insert:
        r = requests.post(URL, data=json.dumps(all_payloads), headers=headers)
        # print("response:", r.text)
        print("status_code", r.status_code)
        # print("test:", r.headers)
    else:
        for payload in all_payloads:
            r = requests.post(URL, data=json.dumps([payload]), headers=headers)
            # print("response:", r.text)
            print("status_code", r.status_code)
            # print("test:", r.headers)


if __name__ == "__main__":
    main()
