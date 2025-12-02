# SystemProfileConversions

Object containing information about 3rd party migration on instances

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**activity** | **bool** | Whether the conversion activity has been done or not | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_conversions import SystemProfileConversions

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileConversions from a JSON string
system_profile_conversions_instance = SystemProfileConversions.from_json(json)
# print the JSON string representation of the object
print(SystemProfileConversions.to_json())

# convert the object into a dict
system_profile_conversions_dict = system_profile_conversions_instance.to_dict()
# create an instance of SystemProfileConversions from a dict
system_profile_conversions_from_dict = SystemProfileConversions.from_dict(system_profile_conversions_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
