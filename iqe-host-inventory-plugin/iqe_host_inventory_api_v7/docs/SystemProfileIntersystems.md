# SystemProfileIntersystems

Object containing data specific to InterSystems workload

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**is_intersystems** | **bool** | Indicates if InterSystems is installed on the system | [optional]
**running_instances** | [**List[SystemProfileInterSystemsRunningInstance]**](SystemProfileInterSystemsRunningInstance.md) |  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_intersystems import SystemProfileIntersystems

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileIntersystems from a JSON string
system_profile_intersystems_instance = SystemProfileIntersystems.from_json(json)
# print the JSON string representation of the object
print(SystemProfileIntersystems.to_json())

# convert the object into a dict
system_profile_intersystems_dict = system_profile_intersystems_instance.to_dict()
# create an instance of SystemProfileIntersystems from a dict
system_profile_intersystems_from_dict = SystemProfileIntersystems.from_dict(system_profile_intersystems_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
