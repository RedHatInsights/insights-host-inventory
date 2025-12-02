# SystemProfileRhsm

Object for subscription-manager details

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**version** | **str** | System release set by subscription-manager | [optional]
**environment_ids** | **List[str]** | Environments (\&quot;content templates\&quot;) the system is subscribed to. | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_rhsm import SystemProfileRhsm

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileRhsm from a JSON string
system_profile_rhsm_instance = SystemProfileRhsm.from_json(json)
# print the JSON string representation of the object
print(SystemProfileRhsm.to_json())

# convert the object into a dict
system_profile_rhsm_dict = system_profile_rhsm_instance.to_dict()
# create an instance of SystemProfileRhsm from a dict
system_profile_rhsm_from_dict = SystemProfileRhsm.from_dict(system_profile_rhsm_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
