# SystemProfileThirdPartyServices

Object containing information about system facts of third party services

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**crowdstrike** | [**SystemProfileThirdPartyServicesCrowdstrike**](SystemProfileThirdPartyServicesCrowdstrike.md) |  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_third_party_services import SystemProfileThirdPartyServices

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileThirdPartyServices from a JSON string
system_profile_third_party_services_instance = SystemProfileThirdPartyServices.from_json(json)
# print the JSON string representation of the object
print(SystemProfileThirdPartyServices.to_json())

# convert the object into a dict
system_profile_third_party_services_dict = system_profile_third_party_services_instance.to_dict()
# create an instance of SystemProfileThirdPartyServices from a dict
system_profile_third_party_services_from_dict = SystemProfileThirdPartyServices.from_dict(system_profile_third_party_services_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
