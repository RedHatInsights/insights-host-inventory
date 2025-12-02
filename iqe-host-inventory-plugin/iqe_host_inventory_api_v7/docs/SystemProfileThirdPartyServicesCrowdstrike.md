# SystemProfileThirdPartyServicesCrowdstrike

Object containing information about CrowdStrike system facts

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**falcon_aid** | **str** | CrowdStrike Falcon Agent ID | [optional]
**falcon_backend** | **str** | CrowdStrike Falcon Sensor backend | [optional]
**falcon_version** | **str** | CrowdStrike running Falcon Sensor version | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_third_party_services_crowdstrike import SystemProfileThirdPartyServicesCrowdstrike

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileThirdPartyServicesCrowdstrike from a JSON string
system_profile_third_party_services_crowdstrike_instance = SystemProfileThirdPartyServicesCrowdstrike.from_json(json)
# print the JSON string representation of the object
print(SystemProfileThirdPartyServicesCrowdstrike.to_json())

# convert the object into a dict
system_profile_third_party_services_crowdstrike_dict = system_profile_third_party_services_crowdstrike_instance.to_dict()
# create an instance of SystemProfileThirdPartyServicesCrowdstrike from a dict
system_profile_third_party_services_crowdstrike_from_dict = SystemProfileThirdPartyServicesCrowdstrike.from_dict(system_profile_third_party_services_crowdstrike_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
