# SystemProfileSystemPurpose

Object for system purpose information

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**usage** | **str** | The intended usage of the system | [optional]
**role** | **str** | The intended role of the system | [optional]
**sla** | **str** | The intended SLA of the system | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_system_purpose import SystemProfileSystemPurpose

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileSystemPurpose from a JSON string
system_profile_system_purpose_instance = SystemProfileSystemPurpose.from_json(json)
# print the JSON string representation of the object
print(SystemProfileSystemPurpose.to_json())

# convert the object into a dict
system_profile_system_purpose_dict = system_profile_system_purpose_instance.to_dict()
# create an instance of SystemProfileSystemPurpose from a dict
system_profile_system_purpose_from_dict = SystemProfileSystemPurpose.from_dict(system_profile_system_purpose_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
