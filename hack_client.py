import base64
import random
import json
import requests
import uuid

#URL = "http://localhost:8080/r/insights/platform/inventory/api/v1/hosts"
URL = "http://localhost:8080/api/inventory/v1/hosts"

#account_number = "0000101"
account_number = "0000001"

domainnames = ["domain1", "domain2", "domain3", "domain4", "domain5"]
hostnames1 = ["apple", "pear", "orange", "banana", "apricot", "grape"]
hostnames2 = ["coke", "pepsi", "drpepper", "mrpib", "sprite", "7up", "unsweettea", "sweettea"]

chunk_size = 1
bulk = False
#bulk = True

#insights_id = "4225c384324849ea9fa80e481c078a4d"
#insights_id = None
insights_id = "4225c384-3248-49ea-9fa8-0e481c078a4d"

def build_chunk():
    list_of_hosts = []
    for i in range(chunk_size):
        fqdn = random.choice(hostnames1) + "_" + random.choice(hostnames2) + "." + random.choice(domainnames) + ".com"
        #fqdn = "fred.flintstone.com"
        '''
        if len(list_of_hosts) == 0:
            account_number = "000001"
        else:
            account_number = "000002"
        '''

        payload = {
                  "account": account_number,
                  #"insights_id": str(uuid.uuid4()),
                  "insights_id": insights_id,
                  "fqdn": fqdn,
                  "display_name": fqdn,
                  #"ip_addresses": None,
                  #"ip_addresses": ["1",],
                  #"mac_addresses": None,
                  #"subscription_manager_id": "214",
                  }

        list_of_hosts.append(payload)

    return list_of_hosts


payload = build_chunk()

headers = {'Content-type': 'application/json',
           'x-rh-insights-request-id': '654321',
           'account_number': account_number,
          }

print("Bulk Upload:")
print("payload:", payload)

#headers["Authorization"] = "Bearer secret"
#headers["Authorization"] = "Bearer 023e4f11185e4c17478bb9c6750d3068eeebe85b"
identity = {'identity': {'account_number': account_number}}
headers["x-rh-identity"] = base64.b64encode(json.dumps(identity).encode())

#payload[0]["insights_id"] = "730b8126-3c85-446d-8f85-493bfdaf34d0"

#del payload[1]["insights_id"]
#del payload[1]["fqdn"]

json_payload = json.dumps(payload)

#print(json_payload)

r = requests.post(URL, data=json_payload, headers=headers)
print("response:", r.text)
print("status_code", r.status_code)
print("test:", r.headers)