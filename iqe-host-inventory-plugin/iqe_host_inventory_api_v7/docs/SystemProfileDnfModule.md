# SystemProfileDnfModule

Representation of one DNF module

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**name** | **str** |  | [optional]
**stream** | **str** |  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_dnf_module import SystemProfileDnfModule

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileDnfModule from a JSON string
system_profile_dnf_module_instance = SystemProfileDnfModule.from_json(json)
# print the JSON string representation of the object
print(SystemProfileDnfModule.to_json())

# convert the object into a dict
system_profile_dnf_module_dict = system_profile_dnf_module_instance.to_dict()
# create an instance of SystemProfileDnfModule from a dict
system_profile_dnf_module_from_dict = SystemProfileDnfModule.from_dict(system_profile_dnf_module_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
