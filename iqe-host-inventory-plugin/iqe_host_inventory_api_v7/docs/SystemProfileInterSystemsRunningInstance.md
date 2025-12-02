# SystemProfileInterSystemsRunningInstance

The info for an InterSystems instance running on the system

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**instance_name** | **str** | The name of the instance | [optional]
**product** | **str** | The product of the instance | [optional]
**version** | **str** | The version of the instance | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_inter_systems_running_instance import SystemProfileInterSystemsRunningInstance

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileInterSystemsRunningInstance from a JSON string
system_profile_inter_systems_running_instance_instance = SystemProfileInterSystemsRunningInstance.from_json(json)
# print the JSON string representation of the object
print(SystemProfileInterSystemsRunningInstance.to_json())

# convert the object into a dict
system_profile_inter_systems_running_instance_dict = system_profile_inter_systems_running_instance_instance.to_dict()
# create an instance of SystemProfileInterSystemsRunningInstance from a dict
system_profile_inter_systems_running_instance_from_dict = SystemProfileInterSystemsRunningInstance.from_dict(system_profile_inter_systems_running_instance_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
