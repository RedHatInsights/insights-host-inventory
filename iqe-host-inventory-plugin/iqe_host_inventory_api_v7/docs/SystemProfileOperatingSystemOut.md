# SystemProfileOperatingSystemOut


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**total** | **int** | Total number of items | [optional]
**count** | **int** | The number of items on the current page | [optional]
**results** | [**List[SystemProfileOperatingSystemOutResultsInner]**](SystemProfileOperatingSystemOutResultsInner.md) | The list of operating_system values on the account | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_operating_system_out import SystemProfileOperatingSystemOut

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileOperatingSystemOut from a JSON string
system_profile_operating_system_out_instance = SystemProfileOperatingSystemOut.from_json(json)
# print the JSON string representation of the object
print(SystemProfileOperatingSystemOut.to_json())

# convert the object into a dict
system_profile_operating_system_out_dict = system_profile_operating_system_out_instance.to_dict()
# create an instance of SystemProfileOperatingSystemOut from a dict
system_profile_operating_system_out_from_dict = SystemProfileOperatingSystemOut.from_dict(system_profile_operating_system_out_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
